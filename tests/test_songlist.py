"""Regression tests for songlist.py make_songlist_fragment BPM scaling."""
from __future__ import annotations

import json
import sys
import os
import tempfile
from pathlib import Path
from contextlib import contextmanager

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from arcaea_slicer.songlist import make_songlist_fragment


@contextmanager
def _write_example(d: dict):
    """Write *d* to a temp JSON file and yield its Path; delete on exit."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(d, tmp)
        path = Path(tmp.name)
    try:
        yield path
    finally:
        path.unlink(missing_ok=True)


EXAMPLE_WITH_BPM = {
    "songs": [
        {
            "id": "example",
            "idx": 1,
            "title_localized": {"en": "Example"},
            "artist": "Artist",
            "bpm": "240",
            "bpm_base": 240.0,
            "set": "base",
            "purchase": "",
            "audioPreview": 0,
            "audioPreviewEnd": 30000,
            "side": 0,
            "date": 0,
            "version": "1.0",
            "difficulties": [],
        }
    ]
}

EXAMPLE_WITH_BASEBPM = {
    "songs": [
        {
            "id": "example",
            "idx": 1,
            "title_localized": {"en": "Example"},
            "artist": "Artist",
            "bpm": "175",
            "baseBpm": 175.0,
            "set": "base",
            "purchase": "",
            "audioPreview": 0,
            "audioPreviewEnd": 30000,
            "side": 0,
            "date": 0,
            "version": "1.0",
            "difficulties": [],
        }
    ]
}

EXAMPLE_NO_BPM = {
    "songs": [
        {
            "id": "example",
            "idx": 1,
            "title_localized": {"en": "Example"},
            "artist": "Artist",
            "set": "base",
            "purchase": "",
            "audioPreview": 0,
            "audioPreviewEnd": 30000,
            "side": 0,
            "date": 0,
            "version": "1.0",
            "difficulties": [],
        }
    ]
}


# ---------------------------------------------------------------------------
# Tests: speed=1.0 leaves BPM unchanged
# ---------------------------------------------------------------------------

def test_bpm_unchanged_at_speed_1():
    with _write_example(EXAMPLE_WITH_BPM) as p:
        frag = make_songlist_fragment(p, "new_song", 0, 30000, 1.0)
    song = frag["songs"][0]
    assert song["bpm"] == "240", f"bpm should be unchanged: {song['bpm']!r}"
    assert song["bpm_base"] == 240.0, f"bpm_base should be unchanged: {song['bpm_base']!r}"


# ---------------------------------------------------------------------------
# Tests: speed=2.0 doubles BPM fields
# ---------------------------------------------------------------------------

def test_bpm_base_scaled_at_speed_2():
    with _write_example(EXAMPLE_WITH_BPM) as p:
        frag = make_songlist_fragment(p, "new_song", 0, 30000, 2.0)
    song = frag["songs"][0]
    assert song["bpm_base"] == 480.0, f"bpm_base should be 480.0 at speed=2.0: {song['bpm_base']!r}"


def test_bpm_string_scaled_at_speed_2():
    with _write_example(EXAMPLE_WITH_BPM) as p:
        frag = make_songlist_fragment(p, "new_song", 0, 30000, 2.0)
    song = frag["songs"][0]
    assert song["bpm"] == "480", f"bpm string should be '480' at speed=2.0: {song['bpm']!r}"


def test_basebpm_scaled_at_speed_2():
    with _write_example(EXAMPLE_WITH_BASEBPM) as p:
        frag = make_songlist_fragment(p, "new_song", 0, 30000, 2.0)
    song = frag["songs"][0]
    assert song["baseBpm"] == 350.0, f"baseBpm should be 350.0 at speed=2.0: {song['baseBpm']!r}"


def test_bpm_string_scaled_fractional():
    with _write_example(EXAMPLE_WITH_BASEBPM) as p:
        frag = make_songlist_fragment(p, "new_song", 0, 30000, 1.25)
    song = frag["songs"][0]
    # 175 * 1.25 = 218.75
    assert float(song["bpm"]) == 218.75, f"bpm string should scale correctly: {song['bpm']!r}"


# ---------------------------------------------------------------------------
# Tests: speed=0.5 halves BPM fields
# ---------------------------------------------------------------------------

def test_bpm_base_scaled_at_speed_half():
    with _write_example(EXAMPLE_WITH_BPM) as p:
        frag = make_songlist_fragment(p, "new_song", 0, 30000, 0.5)
    song = frag["songs"][0]
    assert song["bpm_base"] == 120.0, f"bpm_base should be 120.0 at speed=0.5: {song['bpm_base']!r}"


# ---------------------------------------------------------------------------
# Tests: no BPM keys — no crash
# ---------------------------------------------------------------------------

def test_no_bpm_fields_no_crash():
    with _write_example(EXAMPLE_NO_BPM) as p:
        frag = make_songlist_fragment(p, "new_song", 0, 30000, 2.0)
    assert "songs" in frag  # just verifying it didn't raise


# ---------------------------------------------------------------------------
# Tests: non-numeric bpm string is left unchanged
# ---------------------------------------------------------------------------

def test_non_numeric_bpm_string_unchanged():
    example = {
        "songs": [
            dict(EXAMPLE_WITH_BPM["songs"][0], bpm="120-240"),
        ]
    }
    with _write_example(example) as p:
        frag = make_songlist_fragment(p, "new_song", 0, 30000, 2.0)
    song = frag["songs"][0]
    assert song["bpm"] == "120-240", f"Non-numeric bpm should not be changed: {song['bpm']!r}"
