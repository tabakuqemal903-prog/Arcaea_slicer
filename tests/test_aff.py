"""Regression tests for aff.py timing-line handling.

Verifies that:
- Output timing BPM values never change sign relative to the source.
- Arc lines with negative x/y coordinates do not corrupt timing lines.
- timinggroup blocks (same-line and split-line braces) are handled correctly.
- Songlist BPM fields are scaled proportionally when speed != 1.0.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

# Allow running as a standalone script without installing the package.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from arcaea_slicer.aff import slice_aff
from arcaea_slicer.songlist import make_songlist_fragment


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _timing_bpms(aff_text: str) -> list[float]:
    """Return all BPM values from timing() lines in the AFF text.

    The ``-?`` in the pattern is intentional: we want to *capture* negative
    values so that downstream assertions (``b > 0``) can detect and report them.
    Omitting it would silently skip negative BPMs and cause the tests to pass
    even when the bug is present.
    """
    return [
        float(m.group(1))
        for m in re.finditer(r"timing\(\s*\d+\s*,\s*(-?[\d.]+)", aff_text, re.IGNORECASE)
    ]


# ---------------------------------------------------------------------------
# Sample AFF fixture: positive BPM + arcs with negative coords
# ---------------------------------------------------------------------------

_SAMPLE_AFF = """\
AudioOffset:0
-
timing(0,293.33,4.00);
arc(0,1000,-0.50,0.00,si,-0.50,0.00,0,false,0);
arc(0,500,-0.50,1.00,si,-0.50,1.00,1,false,0)[arctap(250)];
(1000,1);
hold(1000,2000,2);
timing(2000,146.67,4.00);
arc(2000,3000,-0.50,0.00,b,-0.50,0.00,0,false,0);
"""

_SAMPLE_AFF_TIMINGGROUP = """\
AudioOffset:0
-
timing(0,293.33,4.00);
arc(0,1000,-0.50,0.00,si,-0.50,0.00,0,false,0);
timinggroup(noinput){
timing(0,293.33,4.00);
arc(500,1000,-0.50,0.50,si,-0.50,0.50,0,false,0);
};
"""

_SAMPLE_AFF_SPLIT_BRACE = """\
AudioOffset:0
-
timing(0,200.00,4.00);
timinggroup(noinput)
{
timing(0,200.00,4.00);
arc(0,500,-0.25,0.25,si,-0.25,0.25,0,false,0);
};
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_no_negative_bpm_speed_1():
    result = slice_aff(_SAMPLE_AFF, start_ms=0, end_ms=3000, speed=1.0)
    bpms = _timing_bpms(result)
    assert bpms, "Expected at least one timing line in output"
    for b in bpms:
        assert b > 0, f"Negative BPM {b} in output (speed=1.0)"


def test_no_negative_bpm_speed_0_9():
    """Main regression: speed=0.9 must not produce negative BPM values."""
    result = slice_aff(_SAMPLE_AFF, start_ms=0, end_ms=3000, speed=0.9)
    bpms = _timing_bpms(result)
    assert bpms, "Expected at least one timing line in output"
    for b in bpms:
        assert b > 0, f"Negative BPM {b} found in output (speed=0.9)"


def test_bpm_value_preserved():
    """BPM values must not be altered by slicing (speed does not scale BPM)."""
    result = slice_aff(_SAMPLE_AFF, start_ms=0, end_ms=3000, speed=0.9)
    bpms = _timing_bpms(result)
    assert 293.33 in bpms, f"Expected 293.33 in output BPMs, got {bpms}"


def test_arc_negative_coords_do_not_corrupt_timing():
    """Arc lines with negative x/y must not be mistaken for timing lines."""
    result = slice_aff(_SAMPLE_AFF, start_ms=0, end_ms=1000, speed=1.0)
    # Count timing lines – should only be the real ones
    timing_lines = [ln for ln in result.splitlines() if re.match(r"\s*timing\(", ln, re.IGNORECASE)]
    for ln in timing_lines:
        # The -? intentionally captures negative values so the assertion can detect them.
        m = re.match(r"\s*timing\(\s*\d+\s*,\s*(-?[\d.]+)", ln, re.IGNORECASE)
        assert m and float(m.group(1)) > 0, f"Bad timing line: {ln!r}"


def test_timinggroup_same_line_brace():
    result = slice_aff(_SAMPLE_AFF_TIMINGGROUP, start_ms=0, end_ms=1000, speed=1.0)
    # Ensure timinggroup block is closed
    assert "};" in result, "Missing closing '}' for timinggroup"
    bpms = _timing_bpms(result)
    for b in bpms:
        assert b > 0, f"Negative BPM {b} in timinggroup output"


def test_timinggroup_split_brace():
    """timinggroup with '{' on a separate line should be handled without errors."""
    result = slice_aff(_SAMPLE_AFF_SPLIT_BRACE, start_ms=0, end_ms=500, speed=1.0)
    assert "};" in result, "Missing closing '}' for split-brace timinggroup"
    bpms = _timing_bpms(result)
    for b in bpms:
        assert b > 0, f"Negative BPM {b} in split-brace timinggroup output"


def test_segment_mid_song():
    """Slicing a mid-song segment must still inject a timing(0,...) line."""
    result = slice_aff(_SAMPLE_AFF, start_ms=1000, end_ms=3000, speed=1.0)
    lines = result.splitlines()
    timing0 = [ln for ln in lines if re.match(r"\s*timing\(\s*0\s*,", ln, re.IGNORECASE)]
    assert timing0, "Expected a timing(0,...) line at start of sliced segment"
    for ln in timing0:
        # The -? intentionally captures negative values so the assertion can detect them.
        m = re.match(r"\s*timing\(\s*0\s*,\s*(-?[\d.]+)", ln, re.IGNORECASE)
        assert m and float(m.group(1)) > 0, f"Bad BPM in timing(0,...): {ln!r}"


# ---------------------------------------------------------------------------
# Songlist BPM scaling tests
# ---------------------------------------------------------------------------

_SONGLIST_EXAMPLE = {
    "songs": [
        {
            "idx": 1,
            "id": "test",
            "title_localized": {"en": "Test Song"},
            "artist": "Test",
            "bpm": "240",
            "bpm_base": 240,
            "set": "base",
            "purchase": "",
            "audioPreview": 0,
            "audioPreviewEnd": 30000,
            "side": 0,
            "bg": "bg_light",
            "date": 0,
            "version": "1.0",
            "difficulties": [],
        }
    ]
}


def _make_fragment(speed: float) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(_SONGLIST_EXAMPLE, f, ensure_ascii=False)
        tmp_path = Path(f.name)
    try:
        return make_songlist_fragment(tmp_path, "test_0_3000", 0, 3000, speed)
    finally:
        tmp_path.unlink()


def test_songlist_bpm_unchanged_speed_1():
    frag = _make_fragment(1.0)
    song = frag["songs"][0]
    assert song["bpm_base"] == 240
    assert song["bpm"] == "240"


def test_songlist_bpm_scaled_speed_0_9():
    frag = _make_fragment(0.9)
    song = frag["songs"][0]
    assert abs(song["bpm_base"] - 216.0) < 0.01, f"bpm_base={song['bpm_base']}"
    # bpm string "240" * 0.9 = 216 (integer)
    assert song["bpm"] == "216", f"bpm={song['bpm']!r}"


def test_songlist_bpm_scaled_speed_1_25():
    frag = _make_fragment(1.25)
    song = frag["songs"][0]
    assert abs(song["bpm_base"] - 300.0) < 0.01, f"bpm_base={song['bpm_base']}"
    assert song["bpm"] == "300", f"bpm={song['bpm']!r}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except Exception as exc:
            print(f"  FAIL  {fn.__name__}: {exc}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
