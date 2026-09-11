"""Turn logical inputs into RunningHub node overrides by patching the exported
workflow JSON.

Most Pixaroma inputs live inside JSON-string state blobs, so an override's
fieldValue is often the ENTIRE rewritten blob string, not a scalar. We load the
real exported graph, apply each patch to a copy, then emit one override entry
per changed node: {nodeId, fieldName, fieldValue}. For blob fields the
fieldValue is the re-serialised blob; for plain fields it's the scalar.

This keeps every pinned model/sampler/scheduler setting exactly as exported,
and only the inputs the user actually set get overridden.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from . import config
from .config import Patch, WorkflowConfig


@dataclass
class Override:
    node_id: str
    field_name: str
    field_value: object

    def to_json(self) -> dict:
        return {"nodeId": self.node_id, "fieldName": self.field_name, "fieldValue": self.field_value}


def _size_index(w: int, h: int, orient: str) -> int:
    """Index into SizesState.sizes for a landscape (w,h); portrait transposes."""
    sizes = config.VIDEO_SIZES_LANDSCAPE
    target = (w, h) if orient == "landscape" else (h, w)
    # match against landscape list in the orientation's terms
    for i, (lw, lh) in enumerate(sizes):
        cand = (lw, lh) if orient == "landscape" else (lh, lw)
        if cand == (w, h):
            return i
    # fallback: nearest by longest side
    longest = max(w, h)
    best, bi = 1 << 30, 0
    for i, (lw, lh) in enumerate(sizes):
        d = abs(max(lw, lh) - longest)
        if d < best:
            best, bi = d, i
    return bi


def build_overrides(key: str, values: dict, uploaded: dict) -> list[Override]:
    """values: logical_name -> scalar (prompt/duration/size dict/etc.)
       uploaded: logical_name -> RunningHub fileName (for image/audio inputs)

    For 'size' pass values['size'] = {'width':W,'height':H,'orient':'portrait'|'landscape'}.
    """
    cfg: WorkflowConfig = config.WORKFLOWS[key]
    graph = config.load_workflow_json(key)

    # Group patches by node so multiple blob-key edits on one node merge into
    # a single rewritten blob (and one override).
    touched_nodes: dict[str, set] = {}

    def has_value(name: str) -> bool:
        if name in uploaded and uploaded[name]:
            return True
        return name in values and values[name] not in (None, "")

    for name, patch in cfg.patches.items():
        if not has_value(name):
            if name in cfg.optional:
                continue
            # size is provided via values['size']; handle its presence separately
            if patch.kind == "sizes_index" and "size" in values and values["size"]:
                pass
            else:
                raise ValueError(f"[{key}] missing required input '{name}'")

        node = graph.get(patch.node)
        if node is None:
            raise ValueError(f"[{key}] node {patch.node} not in workflow (placeholder not replaced?)")
        inputs = node["inputs"]

        # A value can come from an upload (fileName) or from a plain value.
        src_value = uploaded[name] if (name in uploaded and uploaded[name]) else values.get(name)

        if patch.kind == "field":
            inputs[patch.field] = src_value
        elif patch.kind == "image_field":
            inputs[patch.field] = uploaded[name]
        elif patch.kind == "blob":
            blob = json.loads(inputs[patch.field]) if isinstance(inputs[patch.field], str) else dict(inputs[patch.field])
            blob[patch.blob_key] = src_value
            inputs[patch.field] = json.dumps(blob)
        elif patch.kind == "sizes_index":
            size = values["size"]
            blob = json.loads(inputs[patch.field])
            idx = _size_index(size["width"], size["height"], size.get("orient", "portrait"))
            blob["selected"] = idx
            blob["orientation"] = size.get("orient", blob.get("orientation", "portrait"))
            blob["w"], blob["h"] = size["width"], size["height"]
            inputs[patch.field] = json.dumps(blob)
        else:
            raise ValueError(f"unknown patch kind {patch.kind}")

        touched_nodes.setdefault(patch.node, set()).add(patch.field)

    overrides: list[Override] = []
    for node_id, fields in touched_nodes.items():
        for field in fields:
            overrides.append(Override(node_id, field, graph[node_id]["inputs"][field]))
    return overrides, graph
