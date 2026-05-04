from __future__ import annotations

import hashlib
import json
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
    out["audioPreviewEnd"] = min(30000, max(0, clip_ms))

    # Scale BPM fields to reflect the actual audio speed of the clip.
    if speed != 1.0:
        for key in ("bpm_base", "baseBpm", "base_bpm"):
            if key in out and isinstance(out[key], (int, float)):
                out[key] = round(out[key] * speed, 2)
        # Scale string bpm field if it contains a plain number.
        if "bpm" in out and isinstance(out["bpm"], str):
            try:
                scaled = out["bpm"].strip()
                scaled_val = round(float(scaled) * speed, 2)
                # Preserve int-like appearance when there is no fractional part.
                out["bpm"] = str(int(scaled_val) if scaled_val == int(scaled_val) else scaled_val)
            except (ValueError, TypeError):
                pass

    return {"songs": [out]}
