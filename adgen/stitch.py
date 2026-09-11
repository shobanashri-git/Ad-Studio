"""ffmpeg helpers for joining 5s beats into 10s/15s videos.

Two join modes (both built, switchable per job):
  cut   (chain=False) — beats edited together; each beat rendered independently.
                        Safest, zero drift. Default.
  chain (chain=True)  — beat B starts from beat A's extracted last frame, for one
                        unbroken motion. Better continuity, inherits A's flaws.

concat_copy is a stream copy (fast, no re-encode) and needs identical codecs.
concat_reencode re-encodes to a common format (safe when sources differ).
"""

from __future__ import annotations

import asyncio
import os
import tempfile


async def _run(*args: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}): {err.decode()[:500]}")


async def concat_reencode(inputs: list[str], out_path: str) -> str:
    """Concatenate clips by re-encoding to a common format. Robust default."""
    if not inputs:
        raise ValueError("no inputs to concat")
    listfile = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    try:
        for p in inputs:
            listfile.write(f"file '{os.path.abspath(p)}'\n")
        listfile.close()
        await _run(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile.name,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-movflags", "+faststart", out_path,
        )
    finally:
        os.unlink(listfile.name)
    return out_path


async def concat_copy(inputs: list[str], out_path: str) -> str:
    """Concatenate by stream copy — fast, requires identical codecs/params."""
    if not inputs:
        raise ValueError("no inputs to concat")
    listfile = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
    try:
        for p in inputs:
            listfile.write(f"file '{os.path.abspath(p)}'\n")
        listfile.close()
        await _run(
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile.name,
            "-c", "copy", "-movflags", "+faststart", out_path,
        )
    finally:
        os.unlink(listfile.name)
    return out_path


async def trim(video_path: str, seconds: float, out_path: str) -> str:
    """Trim a video to exactly `seconds` (re-encode for a clean cut point)."""
    await _run(
        "ffmpeg", "-y", "-i", video_path, "-t", f"{seconds:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-movflags", "+faststart", out_path,
    )
    return out_path


async def last_frame(video_path: str, out_png: str) -> str:
    """Extract the final frame as a PNG — the seed image for a chained beat."""
    await _run(
        "ffmpeg", "-y", "-sseof", "-0.1", "-i", video_path,
        "-frames:v", "1", "-q:v", "2", out_png,
    )
    return out_png
