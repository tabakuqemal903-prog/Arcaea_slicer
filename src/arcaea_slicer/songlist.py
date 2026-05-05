from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


def _stable_idx(new_id: str) -> int:
    """Generate a stable positive 31-bit int from the new song id."""
    h = hashlib.sha1(new_id.encode("utf-8")).digest()
    val = int.from_bytes(h[:4], "big", signed=False)
    return val & 0x7FFFFFFF


def make_songlist_fragment(
    songlist_example_path: Path,
    new_id: str,
    start_ms: int,
    end_ms: int,
    speed: float,
) -> dict:
    example = json.loads(songlist_example_path.read_text(encoding="utf-8"))
    if not isinstance(example, dict) or "songs" not in example or not isinstance(example["songs"], list):
        raise ValueError("songlist_example.json must be B-type: { 'songs': [ ... ] }")
    if not example["songs"]:
        raise ValueError("songlist_example.json 'songs' must contain at least one entry")

    tpl = example["songs"][0]
    if not isinstance(tpl, dict):
        raise ValueError("songlist_example.json songs[0] must be an object")

    out = json.loads(json.dumps(tpl, ensure_ascii=False))  # deep copy

    out["id"] = new_id
    out["idx"] = _stable_idx(new_id)

    # Localized title: keep only en; append segment hint
    title_en = ""
    tl = out.get("title_localized")
    if isinstance(tl, dict):
        title_en = str(tl.get("en", ""))
    out["title_localized"] = {"en": f"{title_en} [{start_ms}-{end_ms}]".strip()}

    # Remove other language/search fields if present
    out.pop("search_title", None)
    out.pop("search_artist", None)

    # Preview times (ms in songlist). Clip duration after speed.
    clip_ms = int(round((end_ms - start_ms) / speed))
    out["audioPreview"] = 0
    out["audioPreviewEnd"] = min(10000, max(0, clip_ms))

    # Scale bpm fields according to speed
    # (time axis scaled by 1/speed => bpm scaled by *speed)
    if isinstance(out.get("bpm_base"), (int, float)):
        out["bpm_base"] = round(float(out["bpm_base"]) * speed, 2)

    bpm_val = out.get("bpm")
    if isinstance(bpm_val, (int, float)):
        out["bpm"] = f"{(float(bpm_val) * speed):g}"
    elif isinstance(bpm_val, str):
        s = bpm_val.strip()

        # "240" or "240.0"
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", s):
            out["bpm"] = f"{(float(s) * speed):g}"
        else:
            # "120-240" (allow spaces)
            m = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*-\s*([0-9]+(?:\.[0-9]+)?)", s)
            if m:
                a = float(m.group(1)) * speed
                b = float(m.group(2)) * speed
                out["bpm"] = f"{a:g}-{b:g}"

    return {"songs": [out]}
