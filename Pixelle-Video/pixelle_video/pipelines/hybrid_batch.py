"""
Hybrid Batch Pipeline

Randomly selects a subset of assets for each video in a batch,
generating N distinct videos with random templates and BGM each time.

Workflow:
1. Analyze all uploaded assets (done once, results cached)
2. For each video in the batch:
   a. Randomly select a subset of assets
   b. Pick random template + random BGM
   c. Generate script via LLM for selected assets
   d. Produce the video
3. Return all results

Designed for the "hybrid batch" tab in the web UI.
"""

import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from loguru import logger

from pixelle_video.pipelines.linear import PipelineContext
from pixelle_video.models.progress import ProgressEvent
from pixelle_video.utils.os_util import (
    create_task_output_dir,
    get_task_final_video_path,
    list_resource_files,
)

# Type alias for progress callback
ProgressCallback = Optional[Callable[[ProgressEvent], None]]

# Pool of fitness-oriented templates — same as AssetBasedPipeline
FITNESS_TEMPLATE_POOL = [
    "1080x1920/asset_default.html",
    "1080x1920/asset_fitness_heavy.html",
    "1080x1920/asset_fitness_clean.html",
    "1080x1920/asset_fitness_dynamic.html",
    "1080x1920/asset_fitness_cinematic.html",
    "1080x1920/asset_fitness_impact.html",
    "1080x1920/asset_fitness_edge.html",
]

# Default avg scene duration estimate (seconds per asset-scene)
DEFAULT_SCENE_DURATION = 4.5


class HybridBatchPipeline:
    """
    Hybrid batch video generation pipeline.

    Analyzes assets once, then generates N videos each using a random
    subset of assets, random template, and random BGM.
    """

    def __init__(self, core):
        self.core = core
        self.asset_index: Dict[str, Any] = {}
        self._progress_callback: ProgressCallback = None
        self._bgm_list: List[str] = []
        self._available_templates = list(FITNESS_TEMPLATE_POOL)

    # ==================== Public API ====================

    async def analyze_assets(
        self,
        assets: List[str],
        asset_descriptions: Optional[Dict[str, str]] = None,
        source: str = "runninghub",
        progress_callback: ProgressCallback = None,
    ) -> Dict[str, Any]:
        """
        Analyze all uploaded assets and build asset index.

        This is Step 1 of the two-step flow. Results are cached in
        self.asset_index and also returned.

        Args:
            assets: List of asset file paths
            asset_descriptions: Optional user-provided descriptions
            source: Analysis source ("runninghub" or "selfhost")
            progress_callback: Optional progress callback

        Returns:
            asset_index dict
        """
        self._progress_callback = progress_callback
        total_assets = len(assets)
        logger.info(f"HybridBatch: analyzing {total_assets} assets...")

        self._emit_progress(ProgressEvent(
            event_type="analyzing_assets",
            progress=0.01,
            frame_current=0,
            frame_total=total_assets,
            extra_info="start"
        ))

        self.asset_index = {}
        user_descriptions = asset_descriptions or {}

        for i, asset_path in enumerate(assets, 1):
            asset_path_obj = Path(asset_path)

            if not asset_path_obj.exists():
                logger.warning(f"Asset not found: {asset_path}")
                continue

            asset_type = self._get_asset_type(asset_path_obj)

            # Check user-provided description
            if asset_path in user_descriptions and user_descriptions[asset_path].strip():
                description = user_descriptions[asset_path].strip()
                logger.info(f"Using user description for {asset_path_obj.name}")
            else:
                # AI analysis
                progress = 0.01 + (i - 1) / total_assets * 0.14
                self._emit_progress(ProgressEvent(
                    event_type="analyzing_asset",
                    progress=progress,
                    frame_current=i,
                    frame_total=total_assets,
                    extra_info=asset_path_obj.name
                ))

                try:
                    if asset_type == "image":
                        description = await self.core.image_analysis(asset_path, source=source)
                    elif asset_type == "video":
                        description = await self.core.video_analysis(asset_path, source=source)
                    else:
                        description = f"Media file: {asset_path_obj.name}"
                except Exception as e:
                    logger.warning(f"Analysis failed for {asset_path_obj.name}: {e}, using fallback")
                    description = f"{asset_type.capitalize()} file: {asset_path_obj.name}"

            self.asset_index[asset_path] = {
                "path": asset_path,
                "type": asset_type,
                "name": asset_path_obj.name,
                "description": description,
            }

        logger.success(f"HybridBatch: {len(self.asset_index)} assets analyzed")
        self._emit_progress(ProgressEvent(
            event_type="analyzing_assets",
            progress=0.15,
            frame_current=total_assets,
            frame_total=total_assets,
            extra_info="complete"
        ))

        return self.asset_index

    async def generate_batch(
        self,
        num_videos: int,
        min_duration: int = 15,
        max_duration: int = 30,
        intent: Optional[str] = None,
        source: str = "runninghub",
        voice_id: str = "zh-CN-YunjianNeural",
        tts_speed: float = 1.2,
        intro_enabled: bool = True,
        intro_duration: float = 1.5,
        font_name: str = "",
        text_color: str = "#ffffff",
        text_size: int = 48,
        text_bg: bool = False,
        text_stroke: bool = True,
        progress_callback: ProgressCallback = None,
    ) -> List[PipelineContext]:
        """
        Generate N videos using random subsets of analyzed assets.

        This is Step 2 of the two-step flow. analyze_assets() must be
        called first to populate self.asset_index.

        Args:
            num_videos: Number of videos to generate
            min_duration: Minimum target duration per video
            max_duration: Maximum target duration per video
            intent: Brief context description for the batch
            source: Media analysis source
            voice_id: TTS voice ID
            tts_speed: TTS speed multiplier
            intro_enabled: Whether to add an intro title frame
            intro_duration: Intro frame duration
            font_name: Google Font name
            text_color: Subtitle hex color
            text_size: Subtitle font size
            text_bg: Show semi-transparent background behind text
            text_stroke: Show text stroke for readability
            progress_callback: Optional progress callback

        Returns:
            List of PipelineContext objects (one per video)
        """
        self._progress_callback = progress_callback

        if not self.asset_index:
            raise ValueError(
                "No analyzed assets. Call analyze_assets() first."
            )

        if len(self.asset_index) < 3:
            raise ValueError(
                f"Need at least 3 assets for hybrid batch, got {len(self.asset_index)}"
            )

        # Discover available BGM files
        self._refresh_bgm_list()

        results = []
        asset_keys = list(self.asset_index.keys())

        for video_idx in range(num_videos):
            # Emit overall progress for this video
            batch_progress = video_idx / num_videos
            self._emit_progress(ProgressEvent(
                event_type="batch_video",
                progress=batch_progress,
                frame_current=video_idx + 1,
                frame_total=num_videos,
                extra_info=f"Generating video {video_idx + 1}/{num_videos}"
            ))

            logger.info(f"HybridBatch: generating video {video_idx + 1}/{num_videos}")

            # 1. Select random asset subset
            selected_paths = self._select_assets_for_video(
                asset_keys, min_duration, max_duration
            )

            # 2. Pick random template
            template = random.choice(self._available_templates)
            logger.info(f"  Template: {template}")

            # 3. Pick random BGM
            bgm_path = self._pick_random_bgm()

            # 4. Build per-video asset descriptions from pre-analyzed index
            descriptions = {}
            selected_index = {}
            for p in selected_paths:
                meta = self.asset_index[p]
                descriptions[p] = meta["description"]
                selected_index[p] = meta

            # 5. Generate video via AssetBasedPipeline (with pre-analyzed data)
            from pixelle_video.pipelines.asset_based import AssetBasedPipeline

            # Determine target duration for this video (random within range)
            target_duration = random.randint(min_duration, max_duration)

            # Build intent: tells LLM to generate a hook + one sentence per asset
            n_assets = len(selected_paths)
            if intent and intent.strip():
                video_intent = (
                    f"{intent.strip()}. "
                    f"Select {n_assets} assets and create a {target_duration}-second script. "
                    f"Start with ONE engaging hook sentence, then exactly ONE sentence per asset."
                )
            else:
                video_intent = (
                    f"Quickly introduce these {n_assets} fitness/media items in ~{target_duration}s. "
                    f"Start with ONE catchy hook sentence, then exactly ONE sentence per item."
                )
            logger.info(f"  Assets: {n_assets}, duration: {target_duration}s")

            pipeline = AssetBasedPipeline(self.core)

            ctx = await pipeline(
                assets=selected_paths,
                asset_descriptions=descriptions,
                video_title="",  # Let LLM generate content; intro skipped for hybrid
                intent=video_intent,
                duration=target_duration,
                source=source,
                bgm_path=bgm_path,
                bgm_volume=0.2,
                bgm_mode="loop",
                transition="auto",
                intro_enabled=intro_enabled,
                intro_duration=intro_duration,
                font_name=font_name,
                text_color=text_color,
                text_size=text_size,
                text_bg=text_bg,
                text_stroke=text_stroke,
                voice_id=voice_id,
                tts_speed=tts_speed,
                progress_callback=self._make_video_progress_callback(
                    video_idx, num_videos
                ),
                pre_analyzed_asset_index=selected_index,
            )

            results.append(ctx)
            logger.success(f"  Done: {ctx.final_video_path}")

        # Final progress
        self._emit_progress(ProgressEvent(
            event_type="completed",
            progress=1.0,
            frame_current=num_videos,
            frame_total=num_videos,
            extra_info="complete"
        ))

        return results

    # ==================== Internal helpers ====================

    def _select_assets_for_video(
        self,
        asset_keys: List[str],
        min_duration: int,
        max_duration: int,
    ) -> List[str]:
        """
        Randomly select a subset of assets for one video.

        Picks enough assets to roughly fill the target duration,
        each asset contributing ~DEFAULT_SCENE_DURATION seconds.
        """
        target = random.uniform(min_duration, max_duration)
        min_scenes = max(3, int(min_duration / DEFAULT_SCENE_DURATION))
        max_scenes = min(
            len(asset_keys),
            int(max_duration / DEFAULT_SCENE_DURATION) + 2,
        )
        if max_scenes < min_scenes:
            max_scenes = min_scenes

        num_scenes = random.randint(min_scenes, max_scenes)
        # No repeats within a single video
        num_scenes = min(num_scenes, len(asset_keys))
        selected = random.sample(asset_keys, k=num_scenes)
        # Shuffle for variety
        random.shuffle(selected)
        return selected

    def _refresh_bgm_list(self):
        """Scan available BGM files from resource directories."""
        try:
            audio_extensions = (".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg")
            all_files = list_resource_files("bgm")
            self._bgm_list = sorted(
                [f for f in all_files if f.lower().endswith(audio_extensions)]
            )
        except Exception as e:
            logger.warning(f"Failed to scan BGM files: {e}")
            self._bgm_list = []

    def _pick_random_bgm(self) -> Optional[str]:
        """Pick a random BGM filename (e.g. 'default.mp3'), or None."""
        if not self._bgm_list:
            return None
        return random.choice(self._bgm_list)

    def _make_video_progress_callback(
        self, video_idx: int, total_videos: int
    ) -> ProgressCallback:
        """Wrap per-video progress events with batch context."""
        def callback(event: ProgressEvent):
            # Scale progress: each video occupies (1/total) of overall progress
            if self._progress_callback:
                # Prepend batch info to progress events
                event.extra_info = f"[{video_idx + 1}/{total_videos}] {event.extra_info or ''}"
                self._progress_callback(event)
        return callback

    def _emit_progress(self, event: ProgressEvent):
        """Emit progress event to callback if available."""
        if self._progress_callback:
            self._progress_callback(event)

    def _get_asset_type(self, path: Path) -> str:
        """Determine asset type from file extension."""
        image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
        video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
        ext = path.suffix.lower()
        if ext in image_exts:
            return "image"
        elif ext in video_exts:
            return "video"
        return "unknown"
