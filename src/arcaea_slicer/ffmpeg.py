from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def require_ffmpeg() -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise SystemExit("ffmpeg not found in PATH. Please install ffmpeg and try again.")


def _ms_to_ts(ms: int) -> str:
    # seconds with milliseconds
    return f"{ms/1000:.3f}"


def _atempo_filter(speed: float) -> str:
    # ffmpeg atempo supports 0.5-2.0 per filter; chain if needed.
    if speed <= 0:
        raise ValueError("speed must be > 0")
    parts: list[float] = []
    remaining = speed
    # Bring remaining into [0.5,2.0] by multiplying/dividing by 2.
    while remaining > 2.0:
        parts.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        parts.append(0.5)
        remaining /= 0.5
    parts.append(remaining)
    return ",".join(f"atempo={p:.6f}" for p in parts)


def slice_ogg(in_path: Path, out_path: Path, start_ms: int, end_ms: int, speed: float) -> None:
    duration_ms = end_ms - start_ms
    if duration_ms <= 0:
        raise ValueError("end_ms must be > start_ms")

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        _ms_to_ts(start_ms),
        "-t",
        _ms_to_ts(duration_ms),
        "-i",
        str(in_path),
    ]

    # Re-encode to get accurate cut and allow tempo changes.
    if abs(speed - 1.0) > 1e-9:
        cmd += [
            "-filter:a",
            _atempo_filter(speed),
        ]

    cmd += [
        "-c:a",
        "libvorbis",
        "-q:a",
        "6",
        str(out_path),
    ]

    subprocess.run(cmd, check=True)
