"""
Hybrid Batch Pipeline UI

Two-step flow:
1. Upload assets → click "分析素材" → system analyzes all
2. Configure batch params (num_videos, duration range) → "开始批量生成"

Differs from the existing asset-based batch mode:
- Randomly SUBSETS assets per video (instead of using all assets)
- Random template + random BGM per video
- No predefined topics — LLM generates intro per video
"""

import os
import time
from pathlib import Path
from typing import Any

import streamlit as st
from loguru import logger

from web.i18n import tr, get_language
from web.pipelines.base import PipelineUI, register_pipeline_ui
from web.components.content_input import render_version_info
from web.utils.async_helpers import run_async
from pixelle_video.models.progress import ProgressEvent


class HybridBatchPipelineUI(PipelineUI):
    """UI for the Hybrid Batch Pipeline (random subset + batch generation)."""
    name = "hybrid_batch"
    icon = "🎲"

    @property
    def display_name(self):
        return "混合批量"

    @property
    def description(self):
        return "上传≥15个素材，系统随机抽取子集批量生成N条视频，每次随机模板+BGM"

    def render(self, pixelle_video: Any):
        left_col, middle_col, right_col = st.columns([1, 1, 1])

        with left_col:
            asset_params = self._render_asset_input()
            render_version_info()

        with middle_col:
            self._render_analysis_and_config(pixelle_video, asset_params)

        with right_col:
            self._render_generate_section(pixelle_video, asset_params)

    # ==================== Step 1: Asset Upload ====================

    def _render_asset_input(self) -> dict:
        """Render asset upload section (same layout as asset_based)."""
        with st.container(border=True):
            st.markdown("**📁 上传素材**")

            with st.expander("💡 什么是混合批量模式？", expanded=False):
                st.markdown(
                    "上传大量视频/图片素材（建议≥15个），系统会为每条视频**随机抽取**"
                    "其中几个素材拼接，搭配**随机模板 + 随机BGM**，批量产出 N 条风格各异的视频。"
                )
                st.markdown("**适用场景**: 健身房展示、产品合集、活动花絮等")

            uploaded_files = st.file_uploader(
                "选择素材文件",
                type=["jpg", "jpeg", "png", "gif", "webp", "mp4", "mov", "avi", "mkv", "webm"],
                accept_multiple_files=True,
                help="支持图片和视频混传",
                key="hb_files"
            )

            asset_paths = []
            asset_descriptions = {}
            session_id = None

            if uploaded_files:
                import uuid
                session_id = str(uuid.uuid4()).replace('-', '')[:12]
                temp_dir = Path(f"temp/hybrid_batch_{session_id}")
                temp_dir.mkdir(parents=True, exist_ok=True)

                for uploaded_file in uploaded_files:
                    file_path = temp_dir / uploaded_file.name
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    asset_paths.append(str(file_path.absolute()))

                n = len(asset_paths)
                st.success(f"已上传 {n} 个素材 {'✅ 满足批量条件' if n >= 15 else f'(还需 {15-n} 个达到15个)'}")

                # Preview (collapsed by default)
                with st.expander("👁️ 预览素材", expanded=False):
                    cols = st.columns(3)
                    for i, (file, path) in enumerate(zip(uploaded_files, asset_paths)):
                        with cols[i % 3]:
                            ext = Path(path).suffix.lower()
                            if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                                st.image(file, use_container_width=True)
                            else:
                                st.video(file)
                            st.caption(file.name)

                # Optional descriptions
                with st.expander("✏️ 添加素材描述（可选）", expanded=False):
                    st.caption("为每个素材写一句描述，让AI更准确理解内容")
                    for i, (file, path) in enumerate(zip(uploaded_files, asset_paths)):
                        desc = st.text_input(
                            f"素材 {i+1}: {file.name}",
                            value=file.name.rsplit(".", 1)[0],
                            key=f"hb_desc_{i}_{session_id}"
                        )
                        asset_descriptions[path] = desc
            else:
                st.info("上传至少15个素材即可使用混合批量模式")

            # Store session_id for later use in analysis
            return {
                "assets": asset_paths,
                "asset_descriptions": asset_descriptions,
                "session_id": session_id,
                "uploaded_count": len(asset_paths),
            }

    # ==================== Step 2: Analysis + Config ====================

    def _render_analysis_and_config(self, pixelle_video: Any, asset_params: dict):
        """Render analysis trigger and batch configuration."""
        st.markdown("### 📊 素材分析")

        assets = asset_params["assets"]
        count = asset_params["uploaded_count"]

        if count < 15:
            with st.container(border=True):
                st.warning(f"当前 {count}/15 个素材，上传更多素材后启用混合批量模式")
            return

        # Show analysis state
        analysis_key = "hb_analysis_done"
        analysis_result_key = "hb_analysis_result"

        st.caption(f"已上传 {count} 个素材，准备分析")

        # Analyze button
        analyze_clicked = st.button(
            "🔍 分析所有素材",
            type="primary",
            use_container_width=True,
            key="hb_analyze_btn",
            disabled=st.session_state.get(analysis_key, False),
        )

        if analyze_clicked and not st.session_state.get(analysis_key, False):
            self._run_analysis(pixelle_video, asset_params, analysis_key, analysis_result_key)

        # Show analysis status
        if st.session_state.get(analysis_key, False):
            asset_index = st.session_state.get(analysis_result_key, {})
            st.success(f"✅ {len(asset_index)} 个素材已分析就绪")

            # Batch configuration
            st.markdown("---")
            st.markdown("### ⚙️ 批量配置")

            with st.container(border=True):
                num_videos = st.number_input(
                    "生成视频数量",
                    min_value=1,
                    max_value=50,
                    value=5,
                    step=1,
                    key="hb_num_videos"
                )

                col1, col2 = st.columns(2)
                with col1:
                    min_dur = st.slider(
                        "最小时长（秒）",
                        min_value=10,
                        max_value=60,
                        value=15,
                        step=5,
                        key="hb_min_dur"
                    )
                with col2:
                    max_dur = st.slider(
                        "最大时长（秒）",
                        min_value=10,
                        max_value=60,
                        value=30,
                        step=5,
                        key="hb_max_dur"
                    )

                # Context/intent for the batch
                intent = st.text_area(
                    "批量上下文（可选）",
                    placeholder="例：健身器械展示，以新手教练口吻介绍每个器材的功能和好处",
                    height=80,
                    key="hb_intent"
                )

                st.caption(f"📦 将生成 {num_videos} 条视频，每条 {min_dur}-{max_dur} 秒")
        else:
            st.info("点击「分析所有素材」开始分析")

    def _run_analysis(self, pixelle_video: Any, asset_params: dict,
                      analysis_key: str, analysis_result_key: str):
        """Run asset analysis and store results in session state."""
        assets = asset_params["assets"]
        descriptions = asset_params["asset_descriptions"]

        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            from pixelle_video.pipelines.hybrid_batch import HybridBatchPipeline

            pipeline = HybridBatchPipeline(pixelle_video)

            def update_progress(event: ProgressEvent):
                if event.event_type == "analyzing_assets":
                    if event.extra_info == "start":
                        msg = f"开始分析 {event.frame_total} 个素材..."
                    elif event.extra_info == "complete":
                        msg = f"分析完成！共 {event.frame_total} 个素材"
                    else:
                        msg = f"分析素材中..."
                elif event.event_type == "analyzing_asset":
                    msg = f"正在分析 ({event.frame_current}/{event.frame_total}): {event.extra_info}"
                else:
                    msg = event.event_type
                status_text.text(msg)
                progress_bar.progress(min(int(event.progress * 100), 99))

            asset_index = run_async(pipeline.analyze_assets(
                assets=assets,
                asset_descriptions=descriptions,
                source="runninghub",
                progress_callback=update_progress,
            ))

            progress_bar.progress(100)
            status_text.text(f"✅ 分析完成！共 {len(asset_index)} 个素材")

            # Store in session state
            st.session_state[analysis_key] = True
            st.session_state[analysis_result_key] = asset_index

            st.rerun()

        except Exception as e:
            status_text.text("")
            progress_bar.empty()
            st.error(f"分析失败: {e}")
            logger.exception(e)
            st.stop()

    # ==================== Step 3: Generate ====================

    def _render_generate_section(self, pixelle_video: Any, asset_params: dict):
        """Render generate button and results display."""
        analysis_key = "hb_analysis_done"
        analysis_result_key = "hb_analysis_result"

        st.markdown("### 🚀 批量生成")

        if not st.session_state.get(analysis_key, False):
            st.info("先在「素材分析」栏完成分析后开始生成")
            return

        asset_index = st.session_state[analysis_result_key]
        count = len(asset_index)

        if count < 15:
            st.warning(f"素材不足15个（当前{count}个），无法批量生成")
            return

        with st.container(border=True):
            st.success(f"🎯 {count} 个素材已就绪")
            st.caption(f"每条视频将随机抽取素材 + 随机模板 + 随机BGM")

        # TTS config
        with st.container(border=True):
            st.markdown("**🎙️ 配音设置**")

            from pixelle_video.tts_voices import EDGE_TTS_VOICES, get_voice_display_name
            from pixelle_video.config import config_manager

            comfyui_config = config_manager.get_comfyui_config()
            tts_config = comfyui_config.get("tts", {})
            local_config = tts_config.get("local", {})
            saved_voice = local_config.get("voice", "zh-CN-YunjianNeural")
            saved_speed = local_config.get("speed", 1.2)

            voice_options = []
            voice_ids = []
            default_voice_index = 0
            for idx, voice_config in enumerate(EDGE_TTS_VOICES):
                voice_id = voice_config["id"]
                display_name = get_voice_display_name(voice_id, tr, get_language())
                voice_options.append(display_name)
                voice_ids.append(voice_id)
                if voice_id == saved_voice:
                    default_voice_index = idx

            voice_col, speed_col = st.columns(2)
            with voice_col:
                selected_display = st.selectbox(
                    "配音音色",
                    voice_options,
                    index=default_voice_index,
                    key="hb_tts_voice"
                )
                selected_idx = voice_options.index(selected_display)
                voice_id = voice_ids[selected_idx]
            with speed_col:
                tts_speed = st.slider(
                    "语速",
                    min_value=0.5, max_value=2.0,
                    value=saved_speed, step=0.1, format="%.1fx",
                    key="hb_tts_speed"
                )

        # Intro toggle
        with st.container(border=True):
            st.markdown("**📺 片头设置**")
            intro_enabled = st.checkbox(
                "添加片头标题",
                value=True,
                key="hb_intro_enabled"
            )
            if intro_enabled:
                intro_duration = st.slider(
                    "片头时长（秒）",
                    min_value=0.5, max_value=3.0,
                    value=1.5, step=0.5, format="%.1f",
                    key="hb_intro_duration"
                )
            else:
                intro_duration = 1.5

        # Generate button
        num_videos = st.session_state.get("hb_num_videos", 5)
        generate_label = f"🎬 开始生成 {num_videos} 条视频"

        if st.button(generate_label, type="primary", use_container_width=True, key="hb_generate_btn"):
            if not pixelle_video:
                st.error("系统未就绪")
                st.stop()

            self._run_batch_generation(
                pixelle_video=pixelle_video,
                asset_index=asset_index,
                num_videos=num_videos,
                min_duration=st.session_state.get("hb_min_dur", 15),
                max_duration=st.session_state.get("hb_max_dur", 30),
                intent=st.session_state.get("hb_intent", ""),
                voice_id=voice_id,
                tts_speed=tts_speed,
                intro_enabled=intro_enabled,
                intro_duration=intro_duration,
                font_name="",
                text_color="#ffffff",
                text_size=48,
                text_bg=False,
                text_stroke=True,
            )

    def _run_batch_generation(
        self,
        pixelle_video: Any,
        asset_index: dict,
        num_videos: int,
        min_duration: int,
        max_duration: int,
        intent: str,
        voice_id: str,
        tts_speed: float,
        intro_enabled: bool,
        intro_duration: float,
        font_name: str,
        text_color: str,
        text_size: int,
        text_bg: bool,
        text_stroke: bool,
    ):
        """Run the hybrid batch generation."""
        import io
        import zipfile

        from pixelle_video.pipelines.hybrid_batch import HybridBatchPipeline

        pipeline = HybridBatchPipeline(pixelle_video)
        pipeline.asset_index = asset_index

        # Progress display
        overall_progress = st.progress(0)
        status_text = st.empty()
        detail_container = st.container()

        start_time = time.time()

        try:
            def update_progress(event: ProgressEvent):
                pct = min(int(event.progress * 100), 99)
                overall_progress.progress(pct)

                if event.event_type == "batch_video":
                    status_text.text(f"🎬 {event.extra_info}")
                elif event.event_type == "completed" and event.extra_info == "complete":
                    status_text.text("✅ 全部生成完成！")
                    overall_progress.progress(100)
                else:
                    prefix = event.extra_info or ""
                    status_text.text(f"{prefix} {event.event_type}...")

            ctx_list = run_async(pipeline.generate_batch(
                num_videos=num_videos,
                min_duration=min_duration,
                max_duration=max_duration,
                intent=intent if intent.strip() else None,
                source="runninghub",
                voice_id=voice_id,
                tts_speed=tts_speed,
                intro_enabled=intro_enabled,
                intro_duration=intro_duration,
                font_name=font_name,
                text_color=text_color,
                text_size=text_size,
                text_bg=text_bg,
                text_stroke=text_stroke,
                progress_callback=update_progress,
            ))

            total_time = time.time() - start_time
            overall_progress.progress(100)
            status_text.text("✅ 全部生成完成！")

            st.success(f"✅ 成功生成 {len(ctx_list)}/{num_videos} 条视频，用时 {total_time:.1f}s")

            # Show results
            with detail_container:
                st.markdown("---")
                st.markdown(f"### 📊 生成结果 ({len(ctx_list)}/{num_videos})")

                if ctx_list:
                    # Collect results
                    results = []
                    for ctx in ctx_list:
                        if ctx.final_video_path and os.path.exists(ctx.final_video_path):
                            results.append(ctx)

                    # ZIP download
                    if len(results) > 1:
                        zip_buffer = io.BytesIO()
                        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                            for ctx in results:
                                fname = os.path.basename(ctx.final_video_path)
                                zf.write(ctx.final_video_path, fname)

                        st.download_button(
                            label=f"📦 一键下载全部 {len(results)} 个视频 (ZIP)",
                            data=zip_buffer.getvalue(),
                            file_name=f"混合批量_{len(results)}个.zip",
                            mime="application/zip",
                            use_container_width=True,
                        )

                    # Individual previews
                    for ctx in results:
                        fname = os.path.basename(ctx.final_video_path)
                        with st.expander(f"📹 {fname}", expanded=False):
                            st.video(ctx.final_video_path)
                            if ctx.storyboard:
                                n_scenes = len(ctx.storyboard.frames)
                                dur = ctx.storyboard.total_duration or 0
                                st.caption(f"🎬 {n_scenes} 场景 | ⏱️ {dur:.1f}s")
                            with open(ctx.final_video_path, "rb") as vf:
                                st.download_button(
                                    label=f"⬇️ 下载 {fname}",
                                    data=vf.read(),
                                    file_name=fname,
                                    mime="video/mp4",
                                    use_container_width=True,
                                )

        except Exception as e:
            status_text.text("")
            overall_progress.empty()
            st.error(f"批量生成失败: {e}")
            logger.exception(e)
            st.stop()


# Register self
register_pipeline_ui(HybridBatchPipelineUI)
