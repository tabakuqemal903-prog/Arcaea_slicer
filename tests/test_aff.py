"""Regression tests for aff.py slice_aff."""
from __future__ import annotations

import re
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from arcaea_slicer.aff import slice_aff, _parse_timings, _TIMING_RE


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _extract_timing_lines(aff_out: str) -> list[str]:
    """Return all timing(...); lines from an aff output string."""
    return [
        ln.strip()
        for ln in aff_out.splitlines()
        if re.match(r"\s*timing\(", ln, re.IGNORECASE)
    ]


def _bpm_values(aff_out: str) -> list[float]:
    """Parse BPM values from all timing lines in the output."""
    bpms = []
    for ln in _extract_timing_lines(aff_out):
        m = _TIMING_RE.match(ln)
        if m:
            bpms.append(float(m.group(2)))
    return bpms


# ---------------------------------------------------------------------------
# Simple AFF fixture
# ---------------------------------------------------------------------------

SIMPLE_AFF = """\
AudioOffset:0
-
timing(0,175.00,4.00);
(1000,1);
(3000,2);
timing(5000,180.00,4.00);
(6000,3);
"""

NEGATIVE_TIMESTAMP_AFF = """\
AudioOffset:0
-
timing(-100,175.00,4.00);
timing(0,175.00,4.00);
(1000,1);
(3000,2);
"""

TIMINGGROUP_AFF = """\
AudioOffset:0
-
timing(0,175.00,4.00);
timinggroup(noinput){
    timing(0,175.00,4.00);
    (500,1);
    arc(0,1000,0.00,1.00,s,0.00,0.00,0,none,false);
};
(2000,2);
"""

TIMINGGROUP_BRACE_NEXT_LINE_AFF = """\
AudioOffset:0
-
timing(0,175.00,4.00);
timinggroup(noinput)
{
    timing(0,175.00,4.00);
    (500,1);
};
(2000,2);
"""

NEGATIVE_BPM_AFF = """\
AudioOffset:0
-
timing(0,-175.00,4.00);
(1000,1);
"""


# ---------------------------------------------------------------------------
# Tests: no negative BPM introduced
# ---------------------------------------------------------------------------

def test_no_negative_bpm_introduced_speed1():
    """Output should not contain negative BPM when input has positive BPM only."""
    out = slice_aff(SIMPLE_AFF, start_ms=0, end_ms=4000, speed=1.0)
    bpms = _bpm_values(out)
    assert bpms, "Expected at least one timing line in output"
    assert all(b > 0 for b in bpms), f"Unexpected negative BPM values: {bpms}"


def test_no_negative_bpm_introduced_speed2():
    """At speed=2.0, BPM values should remain positive."""
    out = slice_aff(SIMPLE_AFF, start_ms=0, end_ms=4000, speed=2.0)
    bpms = _bpm_values(out)
    assert bpms, "Expected at least one timing line in output"
    assert all(b > 0 for b in bpms), f"Unexpected negative BPM values: {bpms}"


def test_no_negative_bpm_introduced_mid_slice():
    """Slicing from mid-chart should not introduce negative BPM."""
    out = slice_aff(SIMPLE_AFF, start_ms=3000, end_ms=7000, speed=1.0)
    bpms = _bpm_values(out)
    assert bpms, "Expected at least one timing line in output"
    assert all(b > 0 for b in bpms), f"Unexpected negative BPM values: {bpms}"


def test_negative_bpm_in_input_preserved():
    """A legitimate negative BPM in the source should be preserved as-is."""
    out = slice_aff(NEGATIVE_BPM_AFF, start_ms=0, end_ms=2000, speed=1.0)
    bpms = _bpm_values(out)
    assert bpms, "Expected at least one timing line in output"
    assert bpms[0] == -175.0, f"Expected -175.0 to be preserved, got {bpms[0]}"


# ---------------------------------------------------------------------------
# Tests: canonical timing output format
# ---------------------------------------------------------------------------

def test_timing_canonical_format():
    """Timing lines should be emitted as timing(t,B.BB,B.BB); with two decimal places."""
    out = slice_aff(SIMPLE_AFF, start_ms=0, end_ms=4000, speed=1.0)
    for ln in _extract_timing_lines(out):
        assert re.match(r"timing\(-?\d+,-?\d+\.\d{2},-?\d+\.\d{2}\);$", ln), (
            f"Timing line not in canonical format: {ln!r}"
        )


def test_timing_t0_injected_when_slice_starts_mid_chart():
    """When slicing from a non-zero start, a timing at t=0 must be injected."""
    out = slice_aff(SIMPLE_AFF, start_ms=2000, end_ms=4000, speed=1.0)
    lines = _extract_timing_lines(out)
    assert any(ln.startswith("timing(0,") for ln in lines), (
        f"Expected a timing at t=0, got: {lines}"
    )


# ---------------------------------------------------------------------------
# Tests: timinggroup handling
# ---------------------------------------------------------------------------

def test_timinggroup_preserved():
    """timinggroup blocks should appear in output when they contain in-range notes."""
    out = slice_aff(TIMINGGROUP_AFF, start_ms=0, end_ms=3000, speed=1.0)
    assert "timinggroup" in out.lower(), "timinggroup missing from output"
    assert "};" in out, "timinggroup closing }; missing"


def test_timinggroup_brace_on_next_line():
    """timinggroup with opening brace on the next line must be handled correctly."""
    out = slice_aff(TIMINGGROUP_BRACE_NEXT_LINE_AFF, start_ms=0, end_ms=3000, speed=1.0)
    assert "timinggroup" in out.lower(), "timinggroup missing from output"
    assert "};" in out, "timinggroup closing }; missing"


# ---------------------------------------------------------------------------
# Tests: strict _TIMING_RE does not match inside other lines
# ---------------------------------------------------------------------------

def test_timing_re_does_not_match_arc_line():
    """_TIMING_RE must not match a line that is not a pure timing(...); statement."""
    fake_arc = "arc(0,1000,0.50,0.50,s,0.00,0.00,0,none,false);"
    # stripped & spaces removed shouldn't match
    assert _TIMING_RE.match(fake_arc.replace(" ", "")) is None


def test_timing_re_matches_valid_line():
    """_TIMING_RE should match a valid timing line."""
    assert _TIMING_RE.match("timing(0,175.00,4.00);") is not None
    assert _TIMING_RE.match("timing(1000,180.00,4.00);") is not None
    assert _TIMING_RE.match("timing(0,-175.00,4.00);") is not None


def test_parse_timings_ignores_non_timing_lines():
    """_parse_timings must not create spurious entries for non-timing lines."""
    lines = [
        "timing(0,175.00,4.00);",
        "arc(0,1000,0.50,0.50,s,0.00,0.00,0,none,false);",
        "(500,1);",
        "timing(2000,180.00,4.00);",
    ]
    result = _parse_timings(lines)
    assert len(result) == 2, f"Expected 2 timings, got {len(result)}: {result}"
    assert result[0].bpm == 175.0
    assert result[1].bpm == 180.0


# ---------------------------------------------------------------------------
# Tests: timing at negative timestamp in source is handled
# ---------------------------------------------------------------------------

def test_negative_timestamp_timing_excluded_from_slice():
    """A timing at t<0 that is outside the slice range should not appear in output."""
    out = slice_aff(NEGATIVE_TIMESTAMP_AFF, start_ms=0, end_ms=2000, speed=1.0)
    timing_lines = _extract_timing_lines(out)
    for ln in timing_lines:
        m = re.match(r"timing\((-?\d+),", ln)
        assert m is not None
        assert int(m.group(1)) >= 0, f"Unexpected negative timestamp in output: {ln!r}"
