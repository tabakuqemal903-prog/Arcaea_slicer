from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class _Timing:
    t: int
    bpm: float
    beats: float


_TIMING_RE = re.compile(r"timing\((\d+),(.*?),(.*?)\);", re.IGNORECASE)


def _extract_header_and_body(aff_text: str) -> tuple[list[str], list[str]]:
    lines = aff_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    header: list[str] = []
    body: list[str] = []
    sep_found = False
    for line in lines:
        if not sep_found and line.strip() == "-":
            sep_found = True
            header.append("-")
            continue
        if not sep_found:
            header.append(line)
        else:
            body.append(line)
    if not sep_found:
        # No separator; treat all as body but keep empty header with '-'
        return ["-"], lines
    return header, body


def _parse_timings(lines: list[str]) -> list[_Timing]:
    timings: list[_Timing] = []
    for ln in lines:
        m = _TIMING_RE.search(ln.replace(" ", ""))
        if not m:
            continue
        t = int(m.group(1))
        bpm = float(m.group(2))
        beats = float(m.group(3))
        timings.append(_Timing(t=t, bpm=bpm, beats=beats))
    timings.sort(key=lambda x: x.t)
    return timings


def _active_timing_at(timings: list[_Timing], t0: int) -> _Timing | None:
    """Return last timing with t <= t0 from a sorted timing list."""
    chosen: _Timing | None = None
    for t in timings:
        if t.t <= t0:
            chosen = t
        else:
            break
    return chosen


def _inject_t0_timing(lines: list[str], bpm: float, beats: float) -> list[str]:
    """Ensure timing(0,...) exists near the top of a block."""
    for ln in lines:
        if re.match(r"^\s*timing\s*\(\s*0\s*,", ln.replace(" ", ""), re.IGNORECASE):
            return lines
        # If we hit a non-empty, non-timing line first, still inject at very top
        if ln.strip():
            break
    return [f"timing(0,{bpm:.2f},{beats:.2f});"] + lines


def _fmt_ms(ms: float) -> int:
    # Arcaea aff uses integer ms; keep rounding stable
    return int(round(ms))


def _transform_time(t: int, start_ms: int, speed: float) -> int:
    return _fmt_ms((t - start_ms) / speed)


def _keep_point(t: int, s: int, e: int) -> bool:
    return s <= t <= e


def _overlap_range(t1: int, t2: int, s: int, e: int) -> bool:
    a, b = (t1, t2) if t1 <= t2 else (t2, t1)
    return not (b < s or a > e)


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def _slice_line_simple(line: str, s: int, e: int, start_ms: int, speed: float) -> str | None:
    stripped = line.strip()
    if not stripped:
        return ""

    # timing(t,bpm,beats);
    m = re.match(
        r"\s*timing\(\s*(\d+)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*\)\s*;\s*",
        stripped,
        re.IGNORECASE,
    )
    if m:
        t = int(m.group(1))
        if not _keep_point(t, s, e):
            return None
        bpm = float(m.group(2))
        beats = float(m.group(3))
        t2 = _transform_time(t, start_ms, speed)
        bpm2 = bpm * speed
        return f"timing({t2},{bpm2:.2f},{beats:.2f});"

    # camera(t,...);
    m = re.match(r"\s*camera\((\d+),(.*)\);\s*", stripped, re.IGNORECASE)
    if m:
        t = int(m.group(1))
        if not _keep_point(t, s, e):
            return None
        t2 = _transform_time(t, start_ms, speed)
        return re.sub(r"camera\(\d+,", f"camera({t2},", stripped, flags=re.IGNORECASE)

    # scenecontrol(t,...);
    m = re.match(r"\s*scenecontrol\((\d+),(.*)\);\s*", stripped, re.IGNORECASE)
    if m:
        t = int(m.group(1))
        if not _keep_point(t, s, e):
            return None
        t2 = _transform_time(t, start_ms, speed)
        return re.sub(r"scenecontrol\(\d+,", f"scenecontrol({t2},", stripped, flags=re.IGNORECASE)

    # tap: (t,lane);
    m = re.match(r"\s*\((\d+),(.*)\);\s*", stripped)
    if m:
        t = int(m.group(1))
        if not _keep_point(t, s, e):
            return None
        t2 = _transform_time(t, start_ms, speed)
        return re.sub(r"\(\d+,", f"({t2},", stripped)

    # hold(t1,t2,lane);
    m = re.match(r"\s*hold\((\d+),(\d+),(.*)\);\s*", stripped, re.IGNORECASE)
    if m:
        t1 = int(m.group(1))
        t2 = int(m.group(2))
        if not _overlap_range(t1, t2, s, e):
            return None
        nt1 = _clamp(t1, s, e)
        nt2 = _clamp(t2, s, e)
        ot1 = _transform_time(nt1, start_ms, speed)
        ot2 = _transform_time(nt2, start_ms, speed)
        return re.sub(r"hold\(\d+,\d+,", f"hold({ot1},{ot2},", stripped, flags=re.IGNORECASE)

    # arc(t1,t2,...)[arctap(t),...];
    m = re.match(r"\s*arc\((\d+),(\d+),(.*)\)\s*(\[(.*)\])?;\s*", stripped, re.IGNORECASE)
    if m:
        t1 = int(m.group(1))
        t2 = int(m.group(2))
        if not _overlap_range(t1, t2, s, e):
            return None
        nt1 = _clamp(t1, s, e)
        nt2 = _clamp(t2, s, e)
        ot1 = _transform_time(nt1, start_ms, speed)
        ot2 = _transform_time(nt2, start_ms, speed)

        base_inside = m.group(3)
        taps_blob = m.group(5)

        out = f"arc({ot1},{ot2},{base_inside})"
        if taps_blob is not None:
            kept: list[str] = []
            for tm in re.finditer(r"arctap\((\d+)\)", taps_blob, re.IGNORECASE):
                at = int(tm.group(1))
                if nt1 <= at <= nt2:
                    kept.append(f"arctap({_transform_time(at, start_ms, speed)})")
            out += "[" + ",".join(kept) + "]" if kept else "[]"
        out += ";"
        return out

    return stripped


def _read_timinggroup_block(lines: list[str], i: int) -> tuple[str, list[str], int] | None:
    """
    If lines[i] starts a timinggroup, return (header_without_inner, inner_lines, next_index_after_block).
    Supports '{' on same line or on a following line.
    """
    if i >= len(lines):
        return None
    first = lines[i].strip()
    if not first.lower().startswith("timinggroup"):
        return None

    header = first

    brace = header.count("{") - header.count("}")
    j = i + 1

    if "{" not in header:
        # Look ahead for the '{' line (often it's just "{")
        while j < len(lines):
            header2 = lines[j].strip()
            header = header + " " + header2
            brace += header2.count("{") - header2.count("}")
            j += 1
            if "{" in header2:
                break

    if "{" not in header:
        return None

    inner: list[str] = []
    while j < len(lines) and brace > 0:
        l2 = lines[j]
        brace += l2.count("{") - l2.count("}")
        if brace > 0:
            inner.append(l2)
        j += 1

    header_out = header.split("{", 1)[0].rstrip() + "{"
    return header_out, inner, j


def _slice_block(
    lines: list[str],
    s: int,
    e: int,
    start_ms: int,
    speed: float,
    inherited_t0: _Timing | None,
) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.lower().startswith("timinggroup"):
            parsed = _read_timinggroup_block(lines, i)
            if parsed is not None:
                group_header, inner, next_i = parsed

                group_timings = _parse_timings(inner)
                active = _active_timing_at(group_timings, s) or inherited_t0

                inner_out = _slice_block(inner, s, e, start_ms, speed, active)

                if inner_out:
                    if active is not None:
                        inner_out = _inject_t0_timing(inner_out, active.bpm * speed, active.beats)
                    out.append(group_header)
                    out.extend(inner_out)
                    out.append("};")

                i = next_i
                continue

        sliced = _slice_line_simple(line, s, e, start_ms, speed)
        if sliced is not None:
            out.append(sliced)
        i += 1

    while out and out[-1] == "":
        out.pop()
    return out


def slice_aff(aff_text: str, start_ms: int, end_ms: int, speed: float) -> str:
    header, body = _extract_header_and_body(aff_text)

    timings = _parse_timings(body)
    inherited = _active_timing_at(timings, start_ms)
    if inherited is None and timings:
        inherited = timings[0]

    base_timing_line: str | None = None
    if inherited is not None:
        base_timing_line = f"timing(0,{(inherited.bpm * speed):.2f},{inherited.beats:.2f});"

    out_body = _slice_block(body, start_ms, end_ms, start_ms, speed, inherited)

    # Inject GLOBAL timing(0,...) if missing before the first timinggroup.
    if base_timing_line is not None:
        has_global_t0 = False
        for ln in out_body:
            s2 = ln.strip()
            if s2.lower().startswith("timinggroup"):
                break
            if re.match(r"\s*timing\(0,", ln.replace(" ", ""), re.IGNORECASE):
                has_global_t0 = True
                break

        if not has_global_t0:
            out_body.insert(0, base_timing_line)

    out_lines = header + out_body
    return "\n".join(out_lines).rstrip() + "\n"
