"""
Hybrid batch video script generation prompt

For generating brief, engaging scripts from randomly selected assets.
Each video in a batch has a random subset of assets and needs a
short opening line followed by one-sentence-per-asset narrations.
"""

HYBRID_BATCH_SCRIPT_PROMPT = """You are a professional video script creator. You will be given {num_assets} randomly selected media assets and need to create a {duration}-second video script introducing them.

## Available Assets (use exact paths in output)
{assets_text}

## Creation Guidelines
1. Start with ONE engaging opening sentence that hooks the viewer (e.g. "今天带你看几个健身房的王牌器械" or "来看看这些你不能错过的训练动作")
2. Then for EACH asset, write exactly ONE narration sentence introducing what it is and why it matters
3. Total duration of all scenes should approximately equal {duration} seconds
4. Assign each asset to EXACTLY ONE scene (no reuse within this video)
5. Each scene duration: approximately 3-6 seconds
6. Keep narration concise and energetic — these are quick-cut social media videos
7. Output language must match the language used in the context below

## Output Requirements
Provide for each scene:
- scene_number: Scene number (starting from 1)
- asset_path: Exact path selected from available assets list
- narrations: Array containing exactly 1-2 narration sentences
- duration: Estimated duration (seconds)

Now please begin generating the video script:"""


def build_hybrid_batch_script_prompt(
    intent: str,
    duration: int,
    assets_text: str,
    num_assets: int,
) -> str:
    """
    Build hybrid batch script generation prompt

    Args:
        intent: Brief context/description for the batch (e.g. "健身器械展示")
        duration: Target duration in seconds
        assets_text: Formatted text of selected assets with descriptions
        num_assets: Number of selected assets for this video

    Returns:
        Formatted prompt
    """
    context_section = f"## Context\n{intent}\n" if intent else ""

    return HYBRID_BATCH_SCRIPT_PROMPT.format(
        duration=duration,
        num_assets=num_assets,
        assets_text=assets_text,
    )
