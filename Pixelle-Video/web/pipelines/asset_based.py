# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Asset-Based Pipeline UI

Implements the UI for generating videos from user-provided assets.
"""

import os
import time
from pathlib import Path
from typing import Any

import streamlit as st
from loguru import logger

from web.i18n import tr, get_language
from web.pipelines.base import PipelineUI, register_pipeline_ui
from web.components.content_input import render_bgm_section, render_version_info
from web.utils.async_helpers import run_async
from web.utils.streamlit_helpers import check_and_warn_selfhost_workflow
from pixelle_video.config import config_manager
from pixelle_video.models.progress import ProgressEvent


class AssetBasedPipelineUI(PipelineUI):
    """
    UI for the Asset-Based Video Generation Pipeline.
    Generates videos from user-provided assets (images/videos).
    """
    name = "custom_media"
    icon = "🎨"
    
    @property
    def display_name(self):
        return tr("pipeline.custom_media.name")
    
    @property
    def description(self):
        return tr("pipeline.custom_media.description")
    
    def render(self, pixelle_video: Any):
        # Three-column layout
        left_col, middle_col, right_col = st.columns([1, 1, 1])
        
        # ====================================================================
        # Left Column: Asset Upload & Video Info
        # ====================================================================
        with left_col:
            asset_params = self._render_asset_input()
            bgm_params = render_bgm_section(key_prefix="asset_")
            render_version_info()
        
        # ====================================================================
        # Middle Column: Video Configuration
        # ====================================================================
        with middle_col:
            config_params = self._render_video_config(pixelle_video)
        
        # ====================================================================
        # Right Column: Output Preview
        # ====================================================================
        with right_col:
            # Combine all parameters
            video_params = {
                "pipeline": self.name,
                **asset_params,
                **bgm_params,
                **config_params
            }
            
            self._render_output_preview(pixelle_video, video_params)
    
    def _render_asset_input(self) -> dict:
        """Render asset upload section"""
        with st.container(border=True):
            st.markdown(f"**{tr('asset_based.section.assets')}**")
            
            with st.expander(tr("help.feature_description"), expanded=False):
                st.markdown(f"**{tr('help.what')}**")
                st.markdown(tr("asset_based.assets.what"))
                st.markdown(f"**{tr('help.how')}**")
                st.markdown(tr("asset_based.assets.how"))
            
            # File uploader for multiple files
            uploaded_files = st.file_uploader(
                tr("asset_based.assets.upload"),
                type=["jpg", "jpeg", "png", "gif", "webp", "mp4", "mov", "avi", "mkv", "webm"],
                accept_multiple_files=True,
                help=tr("asset_based.assets.upload_help"),
                key="asset_files"
            )
            
            # Save uploaded files to temp directory with unique session ID
            asset_paths = []
            asset_descriptions = {}
            if uploaded_files:
                import uuid
                session_id = str(uuid.uuid4()).replace('-', '')[:12]
                temp_dir = Path(f"temp/assets_{session_id}")
                temp_dir.mkdir(parents=True, exist_ok=True)

                for uploaded_file in uploaded_files:
                    file_path = temp_dir / uploaded_file.name
                    with open(file_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    asset_paths.append(str(file_path.absolute()))

                st.success(tr("asset_based.assets.count", count=len(asset_paths)))

                # Preview uploaded assets
                with st.expander(tr("asset_based.assets.preview"), expanded=True):
                    # Show in a grid (3 columns)
                    cols = st.columns(3)
                    for i, (file, path) in enumerate(zip(uploaded_files, asset_paths)):
                        with cols[i % 3]:
                            # Check if image or video
                            ext = Path(path).suffix.lower()
                            if ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
                                st.image(file, caption=file.name, use_container_width=True)
                            elif ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
                                st.video(file)
                                st.caption(file.name)

                # Manual descriptions for each asset
                st.markdown("---")
                st.caption(
                    "✏️ 为每个素材写一句描述，告诉AI里面拍的是什么（如：龙门架高位下拉、史密斯机深蹲）。"
                    "描述越准确，生成的文案越能对齐素材。"
                )
                for i, (file, path) in enumerate(zip(uploaded_files, asset_paths)):
                    default_desc = file.name.rsplit(".", 1)[0]  # Use filename without extension as default
                    desc = st.text_input(
                        f"素材 {i+1}: {file.name}",
                        value=default_desc,
                        placeholder=f"描述这个素材的内容...",
                        key=f"asset_desc_{i}_{session_id}"
                    )
                    asset_descriptions[path] = desc
            else:
                st.info(tr("asset_based.assets.empty_hint"))
        
        # Batch mode toggle
        batch_mode = st.checkbox(
            "📦 批量生成（同一批素材，多个标题）",
            value=False,
            key="asset_batch_mode"
        )

        # Video title & intent
        with st.container(border=True):
            st.markdown(f"**{tr('asset_based.section.video_info')}**")

            if batch_mode:
                st.caption("每行一个视频标题，同一批素材会为每个标题生成一个视频")
                topics_text = st.text_area(
                    "批量标题",
                    placeholder="例如：\n新手必练的5个器材\n健身房30天打卡挑战\n最受欢迎器械TOP5",
                    height=120,
                    key="asset_batch_topics"
                )
                topics = [t.strip() for t in topics_text.strip().split('\n') if t.strip()] if topics_text else []
                if topics:
                    st.info(f"共 {len(topics)} 个视频待生成")

                batch_intent = st.text_area(
                    "共用意图（可选，为所有视频设定统一的风格和方向）",
                    placeholder="例如：以新手教练的口吻，展示健身房的王牌器材，消除新人恐惧感，吸引周边潜在客户到店体验",
                    height=80,
                    key="asset_batch_intent"
                )
                intent = batch_intent if batch_intent.strip() else None
                video_title = ""
            else:
                topics = []
                video_title = st.text_input(
                    tr("asset_based.video_title"),
                    placeholder=tr("asset_based.video_title_placeholder"),
                    help=tr("asset_based.video_title_help"),
                    key="asset_video_title"
                )

                intent = st.text_area(
                    tr("asset_based.intent"),
                    placeholder=tr("asset_based.intent_placeholder"),
                    help=tr("asset_based.intent_help"),
                    height=100,
                    key="asset_intent"
                )

        return {
            "assets": asset_paths,
            "asset_descriptions": asset_descriptions,
            "video_title": video_title,
            "intent": intent if intent else None,
            "batch_mode": batch_mode,
            "topics": topics
        }
    
    def _render_video_config(self, pixelle_video: Any) -> dict:
        """Render video configuration section"""
        # Duration configuration
        with st.container(border=True):
            st.markdown(f"**{tr('video.title')}**")
            
            # Duration slider
            duration = st.slider(
                tr("asset_based.duration"),
                min_value=15,
                max_value=120,
                value=30,
                step=5,
                help=tr("asset_based.duration_help"),
                key="asset_duration"
            )
            st.caption(tr("asset_based.duration_label", seconds=duration))
        
        # Workflow source selection
        with st.container(border=True):
            st.markdown(f"**{tr('asset_based.section.source')}**")
            
            with st.expander(tr("help.feature_description"), expanded=False):
                st.markdown(f"**{tr('help.what')}**")
                st.markdown(tr("asset_based.source.what"))
                st.markdown(f"**{tr('help.how')}**")
                st.markdown(tr("asset_based.source.how"))
            
            source_options = {
                "runninghub": tr("asset_based.source.runninghub"),
                "selfhost": tr("asset_based.source.selfhost")
            }
            
            # Check if RunningHub API key is configured
            comfyui_config = config_manager.get_comfyui_config()
            has_runninghub = bool(comfyui_config.get("runninghub_api_key"))
            has_selfhost = bool(comfyui_config.get("comfyui_url"))
            
            # Default to available source
            if has_runninghub:
                default_source_index = 0
            elif has_selfhost:
                default_source_index = 1
            else:
                default_source_index = 0
            
            source = st.radio(
                tr("asset_based.source.select"),
                options=list(source_options.keys()),
                format_func=lambda x: source_options[x],
                index=default_source_index,
                horizontal=True,
                key="asset_source",
                label_visibility="collapsed"
            )
            
            # Show hint based on selection
            if source == "runninghub":
                if not has_runninghub:
                    st.warning(tr("asset_based.source.runninghub_not_configured"))
                else:
                    st.info(tr("asset_based.source.runninghub_hint"))
            else:
                if not has_selfhost:
                    st.warning(tr("asset_based.source.selfhost_not_configured"))
                else:
                    st.info(tr("asset_based.source.selfhost_hint"))
                    # Check and warn for selfhost mode (auto popup if not confirmed)
                    # Use analyse_image.json as representative workflow
                    check_and_warn_selfhost_workflow("selfhost/analyse_image.json")
        
        # TTS configuration
        with st.container(border=True):
            st.markdown(f"**{tr('section.tts')}**")
            
            # Import voice configuration
            from pixelle_video.tts_voices import EDGE_TTS_VOICES, get_voice_display_name
            
            # Get saved voice from config
            comfyui_config = config_manager.get_comfyui_config()
            tts_config = comfyui_config.get("tts", {})
            local_config = tts_config.get("local", {})
            saved_voice = local_config.get("voice", "zh-CN-YunjianNeural")
            saved_speed = local_config.get("speed", 1.2)
            
            # Build voice options with i18n
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
            
            # Two-column layout
            voice_col, speed_col = st.columns([1, 1])
            
            with voice_col:
                selected_voice_display = st.selectbox(
                    tr("tts.voice_selector"),
                    voice_options,
                    index=default_voice_index,
                    key="asset_tts_voice"
                )
                selected_voice_index = voice_options.index(selected_voice_display)
                voice_id = voice_ids[selected_voice_index]
            
            with speed_col:
                tts_speed = st.slider(
                    tr("tts.speed"),
                    min_value=0.5,
                    max_value=2.0,
                    value=saved_speed,
                    step=0.1,
                    format="%.1fx",
                    key="asset_tts_speed"
                )
                st.caption(tr("tts.speed_label", speed=f"{tts_speed:.1f}"))
        
        # Intro configuration
        with st.container(border=True):
            st.markdown("**📺 片头设置**")
            intro_enabled = st.checkbox(
                "添加片头标题（BGM先起，再出语音，避免抽离感）",
                value=True,
                key="asset_intro_enabled"
            )
            if intro_enabled:
                intro_duration = st.slider(
                    "片头时长",
                    min_value=0.5,
                    max_value=3.0,
                    value=1.5,
                    step=0.5,
                    format="%.1f秒",
                    key="asset_intro_duration"
                )
            else:
                intro_duration = 1.5

        # Subtitle style configuration
        with st.container(border=True):
            st.markdown("**🎨 字幕样式**")

            transition = st.selectbox(
                "场景转场",
                options=["none", "fade"],
                format_func=lambda x: "无转场" if x == "none" else "交叉淡入淡出",
                index=1,
                key="asset_transition"
            )

            col1, col2 = st.columns(2)
            with col1:
                text_color = st.color_picker(
                    "字幕颜色",
                    value="#ffffff",
                    key="asset_text_color"
                )
            with col2:
                text_size = st.slider(
                    "字号",
                    min_value=32,
                    max_value=72,
                    value=48,
                    step=2,
                    key="asset_text_size"
                )

            font_name = st.text_input(
                "字体名称（留空=系统默认，输入Google Fonts名称如 Noto Sans SC）",
                value="",
                placeholder="例如: Noto Sans SC, ZCOOL QingKe HuangYou",
                key="asset_font_name"
            )

            col3, col4 = st.columns(2)
            with col3:
                text_stroke = st.checkbox(
                    "文字描边（增强可读性）",
                    value=True,
                    key="asset_text_stroke"
                )
            with col4:
                text_bg = st.checkbox(
                    "半透明背景框",
                    value=False,
                    key="asset_text_bg"
                )

        return {
            "duration": duration,
            "source": source,
            "voice_id": voice_id,
            "tts_speed": tts_speed,
            "intro_enabled": intro_enabled,
            "intro_duration": intro_duration,
            "transition": transition,
            "font_name": font_name,
            "text_color": text_color,
            "text_size": text_size,
            "text_bg": text_bg,
            "text_stroke": text_stroke
        }
    
    def _render_output_preview(self, pixelle_video: Any, video_params: dict):
        """Render output preview section"""
        with st.container(border=True):
            st.markdown(f"**{tr('section.video_generation')}**")

            # Check configuration
            if not config_manager.validate():
                st.warning(tr("settings.not_configured"))

            # Check if assets are provided
            assets = video_params.get("assets", [])
            if not assets:
                st.info(tr("asset_based.output.no_assets"))
                st.button(
                    tr("btn.generate"),
                    type="primary",
                    use_container_width=True,
                    disabled=True,
                    key="asset_generate_disabled"
                )
                return

            # Show asset summary
            st.info(tr("asset_based.output.ready", count=len(assets)))

            batch_mode = video_params.get("batch_mode", False)
            topics = video_params.get("topics", [])

            # Validate batch input
            if batch_mode and not topics:
                st.warning("请在左侧输入至少一个视频标题")
                st.button(
                    tr("btn.generate"),
                    type="primary",
                    use_container_width=True,
                    disabled=True,
                    key="asset_generate_disabled_batch"
                )
                return

            # Generate button
            btn_label = f"🚀 批量生成 {len(topics)} 个视频" if batch_mode and topics else tr("btn.generate")
            if st.button(btn_label, type="primary", use_container_width=True, key="asset_generate"):
                # Validate
                if not config_manager.validate():
                    st.error(tr("settings.not_configured"))
                    st.stop()

                if batch_mode and topics:
                    self._run_batch_generation(pixelle_video, video_params, topics)
                else:
                    self._run_single_generation(pixelle_video, video_params)

    def _run_single_generation(self, pixelle_video: Any, video_params: dict):
        """Generate a single video"""
        progress_bar = st.progress(0)
        status_text = st.empty()
        start_time = time.time()

        try:
            from pixelle_video.pipelines.asset_based import AssetBasedPipeline
            pipeline = AssetBasedPipeline(pixelle_video)

            def update_progress(event: ProgressEvent):
                if event.event_type == "analyzing_assets":
                    if event.extra_info == "start":
                        message = tr("asset_based.progress.analyzing_start", total=event.frame_total)
                    else:
                        message = tr("asset_based.progress.analyzing_complete", count=event.frame_total)
                elif event.event_type == "analyzing_asset":
                    message = tr(
                        "asset_based.progress.analyzing_asset",
                        current=event.frame_current, total=event.frame_total,
                        name=event.extra_info or ""
                    )
                elif event.event_type == "generating_script":
                    message = tr("asset_based.progress.script_complete") if event.extra_info == "complete" else tr("asset_based.progress.generating_script")
                elif event.event_type == "frame_step":
                    message = tr("progress.frame_step", current=event.frame_current, total=event.frame_total, step=event.step, action=tr(f"progress.step_{event.action}"))
                elif event.event_type == "processing_frame":
                    message = tr("progress.frame", current=event.frame_current, total=event.frame_total)
                elif event.event_type == "concatenating":
                    message = tr("asset_based.progress.concat_complete") if event.extra_info == "complete" else tr("progress.concatenating")
                elif event.event_type == "completed":
                    message = tr("progress.completed")
                else:
                    message = tr(f"progress.{event.event_type}")
                status_text.text(message)
                progress_bar.progress(min(int(event.progress * 100), 99))

            ctx = run_async(pipeline(
                assets=video_params["assets"],
                asset_descriptions=video_params.get("asset_descriptions", {}),
                video_title=video_params.get("video_title", ""),
                intent=video_params.get("intent"),
                duration=video_params.get("duration", 30),
                source=video_params.get("source", "runninghub"),
                bgm_path=video_params.get("bgm_path"),
                bgm_volume=video_params.get("bgm_volume", 0.2),
                bgm_mode=video_params.get("bgm_mode", "loop"),
                voice_id=video_params.get("voice_id", "zh-CN-YunjianNeural"),
                tts_speed=video_params.get("tts_speed", 1.2),
                transition=video_params.get("transition", "none"),
                intro_enabled=video_params.get("intro_enabled", True),
                intro_duration=video_params.get("intro_duration", 1.5),
                font_name=video_params.get("font_name", ""),
                text_color=video_params.get("text_color", "#ffffff"),
                text_size=video_params.get("text_size", 48),
                text_bg=video_params.get("text_bg", False),
                text_stroke=video_params.get("text_stroke", True),
                progress_callback=update_progress
            ))

            total_time = time.time() - start_time
            progress_bar.progress(100)
            status_text.text(tr("status.success"))

            st.success(tr("status.video_generated", path=ctx.final_video_path))
            st.markdown("---")

            if os.path.exists(ctx.final_video_path):
                file_size_mb = os.path.getsize(ctx.final_video_path) / (1024 * 1024)
                n_scenes = len(ctx.storyboard.frames) if ctx.storyboard else 0
                st.caption(f"⏱️ {tr('info.generation_time')} {total_time:.1f}s   📦 {file_size_mb:.2f}MB   🎬 {n_scenes}{tr('info.scenes_unit')}")
                st.markdown("---")
                st.video(ctx.final_video_path)
                with open(ctx.final_video_path, "rb") as video_file:
                    st.download_button(
                        label="⬇️ 下载视频" if get_language() == "zh_CN" else "⬇️ Download Video",
                        data=video_file.read(),
                        file_name=os.path.basename(ctx.final_video_path),
                        mime="video/mp4",
                        use_container_width=True
                    )
            else:
                st.error(tr("status.video_not_found", path=ctx.final_video_path))

        except Exception as e:
            status_text.text("")
            progress_bar.empty()
            st.error(tr("status.error", error=str(e)))
            logger.exception(e)
            st.stop()

    def _run_batch_generation(self, pixelle_video: Any, video_params: dict, topics: list):
        """Generate multiple videos from a list of topics"""
        import io
        import zipfile

        results = []
        total = len(topics)
        overall_progress = st.progress(0)
        overall_status = st.empty()
        summary_container = st.container()

        from pixelle_video.pipelines.asset_based import AssetBasedPipeline

        for idx, topic in enumerate(topics):
            overall_progress.progress(int(idx / total * 100))
            overall_status.text(f"🎬 正在生成第 {idx+1}/{total} 个视频: {topic}")

            # Generate single video for this topic
            try:
                pipeline = AssetBasedPipeline(pixelle_video)

                status_text = st.empty()
                progress_bar = st.progress(0)

                def update_progress(event: ProgressEvent):
                    if event.event_type == "completed":
                        status_text.text("")
                    else:
                        status_text.text(f"[{idx+1}/{total}] {event.event_type}...")
                    progress_bar.progress(min(int(event.progress * 100), 99))

                ctx = run_async(pipeline(
                    assets=video_params["assets"],
                    asset_descriptions=video_params.get("asset_descriptions", {}),
                    video_title=topic,
                    intent=video_params.get("intent") or topic,
                    duration=video_params.get("duration", 30),
                    source=video_params.get("source", "runninghub"),
                    bgm_path=video_params.get("bgm_path"),
                    bgm_volume=video_params.get("bgm_volume", 0.2),
                    bgm_mode=video_params.get("bgm_mode", "loop"),
                    voice_id=video_params.get("voice_id", "zh-CN-YunjianNeural"),
                    tts_speed=video_params.get("tts_speed", 1.2),
                    transition=video_params.get("transition", "none"),
                    intro_enabled=video_params.get("intro_enabled", True),
                    intro_duration=video_params.get("intro_duration", 1.5),
                    font_name=video_params.get("font_name", ""),
                    text_color=video_params.get("text_color", "#ffffff"),
                    text_size=video_params.get("text_size", 48),
                    text_bg=video_params.get("text_bg", False),
                    text_stroke=video_params.get("text_stroke", True),
                    progress_callback=update_progress
                ))

                progress_bar.progress(100)
                status_text.text("")

                if os.path.exists(ctx.final_video_path):
                    results.append((topic, ctx.final_video_path))
                    st.success(f"✅ [{idx+1}/{total}] {topic} — 完成")
                else:
                    st.error(f"❌ [{idx+1}/{total}] {topic} — 视频文件未找到")

            except Exception as e:
                st.error(f"❌ [{idx+1}/{total}] {topic} — 失败: {str(e)}")
                logger.exception(e)

        overall_progress.progress(100)
        overall_status.text(f"✅ 批量生成完成！共 {len(results)}/{total} 个视频成功")

        # Show results summary
        with summary_container:
            st.markdown("---")
            st.markdown(f"## 📊 批量生成结果 ({len(results)}/{total})")

            if results:
                # Create a ZIP with all videos
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for topic, path in results:
                        zf.write(path, f"{topic}.mp4")

                st.download_button(
                    label=f"📦 一键下载全部 {len(results)} 个视频 (ZIP)",
                    data=zip_buffer.getvalue(),
                    file_name=f"批量视频_{len(results)}个.zip",
                    mime="application/zip",
                    use_container_width=True
                )

                # Individual previews
                for topic, path in results:
                    with st.expander(f"📹 {topic}", expanded=False):
                        st.video(path)
                        with open(path, "rb") as f:
                            st.download_button(
                                label=f"⬇️ 下载: {topic}.mp4",
                                data=f.read(),
                                file_name=f"{topic}.mp4",
                                mime="video/mp4",
                                use_container_width=True
                            )


# Register self
register_pipeline_ui(AssetBasedPipelineUI)

