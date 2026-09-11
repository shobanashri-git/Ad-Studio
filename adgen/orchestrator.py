"""Orchestration for the four workflows.

Each public method is one independent operation: upload any file inputs to
RunningHub, patch the exported workflow graph with the user's values, submit
the resulting node overrides, wait for the task, and return output URLs.

No cross-stage chaining, no WAITING_FOR_PICK, no beat-stitching — the MiniMax
duration node produces the requested length natively. The UI's asset tray is
the only thing that links panels.
"""

from __future__ import annotations

import os
import tempfile

from . import config, patcher
from .runninghub import RunningHubClient


class Orchestrator:
    def __init__(self, client: RunningHubClient | None = None, tmp_dir: str | None = None):
        self.client = client or RunningHubClient()
        self.tmp_dir = tmp_dir or tempfile.gettempdir()

    async def _upload_files(self, file_inputs: dict[str, str]) -> dict[str, str]:
        """Upload each local path, return logical_name -> RunningHub fileName."""
        out = {}
        for name, path in file_inputs.items():
            if path:
                out[name] = await self.client.upload(path)
        return out

    async def _run(self, key: str, values: dict, file_inputs: dict, on_status=None) -> list[str]:
        uploaded = await self._upload_files(file_inputs)
        overrides, graph = patcher.build_overrides(key, values, uploaded)
        workflow_id = graph.get("_workflow_id") or config.WORKFLOWS[key].file
        # The client submits by workflowId + nodeInfoList. workflowId must be
        # the RunningHub id for this workflow (set via RH_WORKFLOW_* env or the
        # id map below); the exported JSON filename is only a local reference.
        wid = _workflow_id_for(key)
        task_id = await self.client.create(wid, overrides)
        return await self.client.wait(task_id, on_status=on_status)

    # ── 1 · image ──────────────────────────────────────────────────────────
    async def image(self, prompt: str, width: int, height: int,
                    orient: str = "", seed=None, steps=None, cfg=None,
                    reference_path: str = "", on_status=None) -> list[str]:
        values = {"prompt": prompt, "width": width, "height": height}
        if orient:
            values["orient"] = orient
        if seed is not None:
            values["seed"] = seed
        if steps is not None:
            values["steps"] = steps
        if cfg is not None:
            values["cfg"] = cfg
        files = {"reference": reference_path} if reference_path else {}
        return await self._run("image", values, files, on_status)

    # ── 2 · character ────────────────────────────────────────────────────────
    async def character(self, character_path: str, character_prompt: str,
                        name: str = "", style_quality: str = "", on_status=None) -> list[str]:
        values = {"character_prompt": character_prompt}
        if name:
            values["name"] = name
        if style_quality:
            values["style_quality"] = style_quality
        return await self._run("character", values, {"character": character_path}, on_status)

    # ── 3 · video ────────────────────────────────────────────────────────────
    async def video(self, character_path: str, prompt: str, width: int, height: int,
                    orient: str, duration: int, outfit_path: str = "", product_path: str = "",
                    background_path: str = "", character2_path: str = "", on_status=None) -> list[str]:
        values = {
            "prompt": prompt,
            "duration": duration,
            "size": {"width": width, "height": height, "orient": orient},
        }
        files = {
            "character": character_path,
            "outfit": outfit_path,
            "product": product_path,
            "background": background_path,
            "character2": character2_path,
        }
        return await self._run("video", values, files, on_status)

    # ── 4 · lipsync ────────────────────────────────────────────────────────────
    async def lipsync(self, face_path: str, audio_path: str, prompt: str = "",
                      duration: int = 5, longest_side: int = 0, ratio: str = "",
                      on_status=None) -> list[str]:
        values = {"duration": duration}
        if prompt:
            values["prompt"] = prompt
        if longest_side:
            values["longest_side"] = longest_side
        if ratio:
            values["ratio"] = ratio
        return await self._run("lipsync", values, {"face": face_path, "audio": audio_path}, on_status)

    # ── download helper (RunningHub output URL -> local file) ──────────────────
    async def download(self, url: str, filename: str) -> str:
        import httpx
        dest = os.path.join(self.tmp_dir, filename)
        async with httpx.AsyncClient(timeout=180.0) as c:
            r = await c.get(url)
            r.raise_for_status()
            with open(dest, "wb") as fh:
                fh.write(r.content)
        return dest


def _workflow_id_for(key: str) -> str:
    """RunningHub workflowId per workflow. Set these via env once you have them
    (Export Workflow API gives the JSON; the workflowId is on the workflow's RH
    page/URL). Falls back to a REPLACE placeholder so misconfig is obvious."""
    env = {
        "image": "RH_WORKFLOW_IMAGE",
        "character": "RH_WORKFLOW_CHARACTER",
        "video": "RH_WORKFLOW_VIDEO",
        "lipsync": "RH_WORKFLOW_LIPSYNC",
    }[key]
    return os.environ.get(env, f"REPLACE_{env}")
