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

    # Scale numeric BPM fields when speed differs from 1.0.
    # Common keys: bpm_base, baseBpm, base_bpm (numeric); bpm (may be a string).
    if speed != 1.0:
        for key in ("bpm_base", "baseBpm", "base_bpm"):
            if key in out and isinstance(out[key], (int, float)):
                scaled = out[key] * speed
                # Preserve integer type when the result is a whole number.
                out[key] = int(scaled) if scaled == int(scaled) else round(scaled, 2)
        # For the display string BPM field, scale only if it is a plain number.
        if "bpm" in out and isinstance(out["bpm"], str):
            try:
                bpm_val = float(out["bpm"])
                scaled = bpm_val * speed
                # Keep as integer string if the result is whole, else 2 dp.
                out["bpm"] = str(int(scaled)) if scaled == int(scaled) else f"{scaled:.2f}"
            except ValueError:
                pass  # complex bpm string like "120-240" – leave unchanged
        elif "bpm" in out and isinstance(out["bpm"], (int, float)):
            scaled = out["bpm"] * speed
            out["bpm"] = int(scaled) if scaled == int(scaled) else round(scaled, 2)

    return {"songs": [out]}
