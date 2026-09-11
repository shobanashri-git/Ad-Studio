"""Per-workflow patch descriptors + node mapping.

These workflows are Pixaroma-based: most content inputs (prompts, duration,
size selection, longest-side, audio filename) are NOT plain node fields — they
live inside JSON-string "state" blobs on the node's inputs. So driving them
means loading the exported workflow JSON, patching values (plain fields OR a
key inside a blob), and sending the changed nodes as a nodeInfoList of
overrides. See patcher.py.

Each workflow lists:
  file      — the exported API JSON shipped alongside the package
  patches   — logical_input -> Patch(node, field, kind, blob_key=?)

Patch.kind:
  "field"       set inputs[field] = value directly (plain field)
  "blob"        inputs[field] is a JSON string; set blob[blob_key] = value
  "image_field" like "field" but value is a RunningHub uploaded fileName
  "sizes_index" special: pick an index into SizesState.sizes by (w,h)+orient
"""

from __future__ import annotations

import os
from dataclasses import dataclass

WORKFLOW_DIR = os.path.dirname(__file__)


@dataclass
class Patch:
    node: str
    field: str
    kind: str = "field"
    blob_key: str | None = None


@dataclass
class WorkflowConfig:
    file: str
    patches: dict          # logical_name -> Patch
    optional: tuple = ()


# ── 1 · Image generation ────────────────────────────────────────────────────
# prompt (244 blob), width/height (241 plain fields), KSampler seed/steps/cfg (225).
IMAGE = WorkflowConfig(
    file="workflows_image_api.json",
    patches={
        "prompt": Patch("244", "PromptState", "blob", "text"),
        "width":  Patch("241", "width", "field"),
        "height": Patch("241", "height", "field"),
        "orient": Patch("241", "PortraitLandscapeState", "blob", "orient"),
        "seed":   Patch("225", "seed", "field"),
        "steps":  Patch("225", "steps", "field"),
        "cfg":    Patch("225", "cfg", "field"),
        # Optional reference image (LoadImage 247 -> MiniMax H3 last_frame).
        "reference": Patch("247", "image", "image_field"),
    },
    optional=("orient", "seed", "steps", "cfg", "reference"),
)

# ── 2 · Character consistency (PuLID-Flux character sheet) ──────────────────
# face image (LoadImage 626), prompt (String Literal 594), name (471),
# style+quality (608). Pose sheet 625 stays fixed.
CHARACTER = WorkflowConfig(
    file="workflows_character_api.json",
    patches={
        "character":        Patch("626", "image", "image_field"),
        "character_prompt": Patch("594", "string", "field"),
        "name":             Patch("471", "string", "field"),
        "style_quality":    Patch("608", "string", "field"),
    },
    optional=("name", "style_quality"),
)

# ── 3 · multi-image -> video ────────────────────────────────────────────────
# 5 ref-image loaders. 4 exist today (236,238,240,241); a 5th will be added in
# RunningHub — drop its nodeId into `character2` below once created.
VIDEO = WorkflowConfig(
    file="workflows_video_api.json",
    patches={
        "character":  Patch("236", "image", "image_field"),
        "outfit":     Patch("238", "image", "image_field"),
        "product":    Patch("240", "image", "image_field"),
        "background": Patch("241", "image", "image_field"),
        "character2": Patch("242", "image", "image_field"),
        "prompt":     Patch("239", "PromptState", "blob", "text"),
        "duration":   Patch("234", "DurationState", "blob", "seconds"),
        # size: choose an index into SizesState.sizes matching (w,h) + orient
        "size":       Patch("223", "SizesState", "sizes_index"),
    },
    optional=("outfit", "product", "background", "character2"),
)

# ── 4 · image + audio -> lip-synced closeup ────────────────────────────────
LIPSYNC = WorkflowConfig(
    file="workflows_lipsync_api.json",
    patches={
        "face":         Patch("236", "image", "image_field"),
        "audio":        Patch("247", "LoadAudioState", "blob", "file"),
        "prompt":       Patch("239", "PromptState", "blob", "text"),
        "duration":     Patch("234", "DurationState", "blob", "seconds"),
        "longest_side": Patch("243", "LongestSideState", "blob", "size"),
        "ratio":        Patch("243", "LongestSideState", "blob", "ratio"),
    },
    optional=("prompt", "longest_side", "ratio"),
)

WORKFLOWS = {
    "image": IMAGE,
    "character": CHARACTER,
    "video": VIDEO,
    "lipsync": LIPSYNC,
}

# Durations offered in the UI (seconds). The workflow's duration node maps
# these to frames itself, so the backend only sets `seconds`.
DURATIONS = [3, 4, 5, 6, 7, 8, 9, 10, 12, 15]

# Lip-sync longest-side options + aspect ratios (from the workflow UI).
LONGEST_SIDES = [864, 1024, 1216, 1344, 1536]
RATIOS = ["keep", "1:1", "16:9", "9:16", "2:3"]

# Video size preset list (landscape orientation, w x h). Portrait transposes.
VIDEO_SIZES_LANDSCAPE = [
    (608, 352), (736, 416), (864, 480), (960, 544), (1056, 608), (1152, 640),
    (1216, 672), (1280, 736), (1344, 768), (1376, 768), (1504, 832),
    (1664, 928), (1824, 1024), (1920, 1088),
]
VIDEO_STARRED = ["480x864", "672x1216", "768x1344"]  # recommended defaults


def load_workflow_json(key: str) -> dict:
    import json
    cfg = WORKFLOWS[key]
    with open(os.path.join(WORKFLOW_DIR, cfg.file), "r") as fh:
        return json.load(fh)
