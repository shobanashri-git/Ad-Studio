"""FastAPI app — four workflow endpoints over the orchestrator.

Each endpoint accepts a multipart form (uploads + fields), starts a background
job, returns {job_id}. UI polls GET /jobs/{id} until DONE (result payload) or
FAILED (error). Inputs can be uploaded files OR tray references (`<name>_ref`
= a prior job's asset id, resolved server-side to a local path).

In-memory job + asset store (single-user tool). For production move to Redis/DB
and push outputs to real storage.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from typing import Optional

import httpx
from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .orchestrator import Orchestrator

app = FastAPI(title="Ad Studio API")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

WORK_DIR = os.path.join(tempfile.gettempdir(), "adgen")
os.makedirs(WORK_DIR, exist_ok=True)

# Where "saved" assets are kept permanently (survives restarts). Configurable
# via ADGEN_SAVE_DIR; defaults to a 'saved' folder next to the working dir.
SAVE_DIR = os.environ.get("ADGEN_SAVE_DIR") or os.path.join(os.getcwd(), "saved")
os.makedirs(SAVE_DIR, exist_ok=True)
SAVE_INDEX = os.path.join(SAVE_DIR, "index.json")

JOBS: dict[str, dict] = {}      # job_id -> {status, result, error}
ASSETS: dict[str, str] = {}     # asset_id -> local path

_orch: Optional[Orchestrator] = None


def orch() -> Orchestrator:
    global _orch
    if _orch is None:
        _orch = Orchestrator(tmp_dir=WORK_DIR)
    return _orch


# ── helpers ─────────────────────────────────────────────────────────────────
def _new_job() -> str:
    jid = uuid.uuid4().hex[:12]
    JOBS[jid] = {"status": "QUEUED", "result": None, "error": None}
    return jid


def _set_status(jid: str, status: str):
    if jid in JOBS:
        JOBS[jid]["status"] = status


def _register_asset(path: str) -> str:
    aid = uuid.uuid4().hex[:12]
    ASSETS[aid] = path
    return aid


def _ascii(name: Optional[str]) -> str:
    # RunningHub rejects non-ASCII filenames — sanitise on the way in.
    name = name or "input.bin"
    return "".join(ch if ord(ch) < 128 and ch not in ' "\'' else "_" for ch in name)


async def _save_upload(f: UploadFile) -> str:
    dest = os.path.join(WORK_DIR, f"up_{uuid.uuid4().hex[:8]}_{_ascii(f.filename)}")
    with open(dest, "wb") as fh:
        fh.write(await f.read())
    return dest


async def _resolve_url(url: str) -> str:
    dest = os.path.join(WORK_DIR, f"ref_{uuid.uuid4().hex[:8]}.bin")
    async with httpx.AsyncClient(timeout=180.0) as c:
        r = await c.get(url)
        r.raise_for_status()
        with open(dest, "wb") as fh:
            fh.write(r.content)
    return dest


async def _resolve_input(upload, ref, url) -> Optional[str]:
    if upload is not None:
        return await _save_upload(upload)
    if ref:
        if ref not in ASSETS:
            raise HTTPException(400, f"unknown asset reference '{ref}'")
        return ASSETS[ref]
    if url:
        return await _resolve_url(url)
    return None


def _run_bg(jid: str, coro_factory):
    async def runner():
        try:
            _set_status(jid, "RUNNING")
            JOBS[jid]["result"] = await coro_factory(lambda s: _set_status(jid, s))
            JOBS[jid]["status"] = "DONE"
        except Exception as e:  # noqa: BLE001
            JOBS[jid]["error"] = str(e)
            JOBS[jid]["status"] = "FAILED"
    asyncio.create_task(runner())


async def _localize_outputs(urls: list[str], prefix: str) -> list[dict]:
    """Download RunningHub output URLs into WORK_DIR, register as assets, and
    return [{url: /files/.., asset_id: ..}] the UI can show and re-reference."""
    out = []
    for i, u in enumerate(urls):
        ext = os.path.splitext(u.split("?")[0])[1] or ".bin"
        local = await orch().download(u, f"{prefix}_{uuid.uuid4().hex[:6]}{ext}")
        aid = _register_asset(local)
        out.append({"url": f"/files/{os.path.basename(local)}", "asset_id": aid})
    return out


# ── 1 · image ─────────────────────────────────────────────────────────────
@app.post("/image")
async def image(
    prompt: str = Form(...),
    width: int = Form(1024),
    height: int = Form(1024),
    orient: str = Form(""),
    seed: Optional[int] = Form(None),
    steps: Optional[int] = Form(None),
    cfg: Optional[float] = Form(None),
    reference: Optional[UploadFile] = File(None),
    reference_ref: Optional[str] = Form(None),
    reference_url: Optional[str] = Form(None),
):
    ref_path = await _resolve_input(reference, reference_ref, reference_url) or ""
    jid = _new_job()

    async def factory(on_status):
        urls = await orch().image(prompt, width, height, orient, seed, steps, cfg,
                                  reference_path=ref_path, on_status=on_status)
        items = await _localize_outputs(urls, "image")
        return {"images": items}

    _run_bg(jid, factory)
    return {"job_id": jid}


# ── 2 · character ──────────────────────────────────────────────────────────
@app.post("/character")
async def character(
    character: Optional[UploadFile] = File(None),
    character_ref: Optional[str] = Form(None),
    character_url: Optional[str] = Form(None),
    character_prompt: str = Form(...),
    name: str = Form(""),
    style_quality: str = Form(""),
):
    path = await _resolve_input(character, character_ref, character_url)
    if not path:
        raise HTTPException(400, "character reference image is required")
    jid = _new_job()

    async def factory(on_status):
        urls = await orch().character(path, character_prompt, name, style_quality, on_status=on_status)
        items = await _localize_outputs(urls, "char")
        return {"character_set": items}

    _run_bg(jid, factory)
    return {"job_id": jid}


# ── 3 · video ────────────────────────────────────────────────────────────────
@app.post("/video")
async def video(
    character: Optional[UploadFile] = File(None),
    character_ref: Optional[str] = Form(None),
    character_url: Optional[str] = Form(None),
    outfit: Optional[UploadFile] = File(None),
    outfit_ref: Optional[str] = Form(None),
    outfit_url: Optional[str] = Form(None),
    product: Optional[UploadFile] = File(None),
    product_ref: Optional[str] = Form(None),
    product_url: Optional[str] = Form(None),
    background: Optional[UploadFile] = File(None),
    background_ref: Optional[str] = Form(None),
    background_url: Optional[str] = Form(None),
    character2: Optional[UploadFile] = File(None),
    character2_ref: Optional[str] = Form(None),
    character2_url: Optional[str] = Form(None),
    prompt: str = Form(""),
    width: int = Form(928),
    height: int = Form(1664),
    orient: str = Form("portrait"),
    duration: int = Form(5),
):
    char_path = await _resolve_input(character, character_ref, character_url)
    if not char_path:
        raise HTTPException(400, "character image is required")
    outfit_path = await _resolve_input(outfit, outfit_ref, outfit_url) or ""
    product_path = await _resolve_input(product, product_ref, product_url) or ""
    background_path = await _resolve_input(background, background_ref, background_url) or ""
    character2_path = await _resolve_input(character2, character2_ref, character2_url) or ""
    jid = _new_job()

    async def factory(on_status):
        urls = await orch().video(
            char_path, prompt, width, height, orient, duration,
            outfit_path, product_path, background_path, character2_path,
            on_status=on_status,
        )
        items = await _localize_outputs(urls, "video")
        first = items[0] if items else {}
        return {"video": first.get("url"), "asset_id": first.get("asset_id"), "outputs": items}

    _run_bg(jid, factory)
    return {"job_id": jid}


# ── 4 · lipsync ──────────────────────────────────────────────────────────────
@app.post("/lipsync")
async def lipsync(
    face: Optional[UploadFile] = File(None),
    face_ref: Optional[str] = Form(None),
    face_url: Optional[str] = Form(None),
    audio: Optional[UploadFile] = File(None),
    audio_ref: Optional[str] = Form(None),
    audio_url: Optional[str] = Form(None),
    prompt: str = Form(""),
    duration: int = Form(5),
    longest_side: int = Form(0),
    ratio: str = Form(""),
):
    face_path = await _resolve_input(face, face_ref, face_url)
    audio_path = await _resolve_input(audio, audio_ref, audio_url)
    if not face_path:
        raise HTTPException(400, "face image is required")
    if not audio_path:
        raise HTTPException(400, "audio file is required")
    jid = _new_job()

    async def factory(on_status):
        urls = await orch().lipsync(face_path, audio_path, prompt, duration, longest_side, ratio, on_status=on_status)
        items = await _localize_outputs(urls, "talk")
        first = items[0] if items else {}
        return {"talking_clip": first.get("url"), "asset_id": first.get("asset_id"), "outputs": items}

    _run_bg(jid, factory)
    return {"job_id": jid}


# ── job status + file serving ─────────────────────────────────────────────
@app.get("/jobs/{job_id}")
async def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "unknown job")
    payload = {"status": job["status"]}
    if job["status"] == "DONE":
        payload.update(job["result"] or {})
    if job["status"] == "FAILED":
        payload["error"] = job["error"]
    return JSONResponse(payload)


@app.get("/files/{name}")
async def get_file(name: str):
    path = os.path.join(WORK_DIR, os.path.basename(name))
    if not os.path.exists(path):
        raise HTTPException(404, "file not found")
    return FileResponse(path)


@app.post("/save")
async def save_asset(
    asset_id: str = Form(...),
    tool: str = Form(""),
    prompt: str = Form(""),
    save_dir: str = Form(""),
):
    """Copy a generated asset out of the temp dir into a permanent folder, and
    record its metadata (tool, prompt, date) in an index.json manifest.

    save_dir (optional) overrides the default SAVE_DIR for this save, so the UI
    can let the user choose where assets land."""
    src = ASSETS.get(asset_id)
    if not src or not os.path.exists(src):
        raise HTTPException(404, "asset not found or already cleaned up")

    target_dir = save_dir.strip() or SAVE_DIR
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception as e:
        raise HTTPException(400, f"cannot use folder '{target_dir}': {e}")

    import shutil
    from datetime import datetime, timezone
    ext = os.path.splitext(src)[1] or ".bin"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    base = f"{tool or 'asset'}_{stamp}_{asset_id[:6]}{ext}"
    dest = os.path.join(target_dir, base)
    shutil.copy2(src, dest)

    # Append to the manifest (per target dir).
    index_path = os.path.join(target_dir, "index.json")
    try:
        with open(index_path, "r") as fh:
            index = json.load(fh)
    except Exception:
        index = []
    entry = {
        "file": base,
        "tool": tool,
        "prompt": prompt,
        "asset_id": asset_id,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    index.insert(0, entry)
    with open(index_path, "w") as fh:
        json.dump(index, fh, indent=2)

    return {"saved": True, "path": dest, "file": base, "folder": target_dir}


@app.get("/saved")
async def list_saved(save_dir: str = ""):
    """Return the saved-assets manifest for a folder (default SAVE_DIR)."""
    target_dir = save_dir.strip() or SAVE_DIR
    index_path = os.path.join(target_dir, "index.json")
    try:
        with open(index_path, "r") as fh:
            return {"folder": target_dir, "items": json.load(fh)}
    except Exception:
        return {"folder": target_dir, "items": []}


@app.get("/health")
async def health():
    return {"ok": True, "jobs": len(JOBS), "assets": len(ASSETS)}


@app.get("/balance")
async def balance():
    """Remaining RH coins + running task count, for the UI. Best-effort."""
    try:
        status = await orch().client.account_status()
    except Exception:
        status = {}
    return {
        "remain_coins": status.get("remainCoins") or status.get("remain_coins"),
        "current_tasks": status.get("currentTaskCounts") or status.get("current_task_counts"),
        "raw": status,
    }
