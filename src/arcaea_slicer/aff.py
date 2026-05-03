from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class _Timing:
    t: int
    bpm: float
    beats: float


# Strict timing regex: anchored at start, captures exactly (int, float, float).
# The ^ anchor prevents matching 'timing(' that appears mid-line (e.g. inside arc params).
_TIMING_RE = re.compile(
    r"^\s*timing\(\s*(\d+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)\s*;",
    re.IGNORECASE,
)


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
        m = _TIMING_RE.match(ln)
        if not m:
            continue
        t = int(m.group(1))
        bpm = float(m.group(2))
        beats = float(m.group(3))
        timings.append(_Timing(t=t, bpm=bpm, beats=beats))
    timings.sort(key=lambda x: x.t)
    return timings


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

    # timing(t,bpm,beats);  — strict: must be the whole line, captures exactly 3 args
    m = re.match(
        r"^\s*timing\(\s*(\d+)\s*,\s*(-?[\d.]+)\s*,\s*(-?[\d.]+)\s*\)\s*;\s*$",
        stripped,
        re.IGNORECASE,
    )
    if m:
        t = int(m.group(1))
        if not _keep_point(t, s, e):
            return None
        t2 = _transform_time(t, start_ms, speed)
        bpm = float(m.group(2))
        beats = float(m.group(3))
        return f"timing({t2},{bpm:.2f},{beats:.2f});"

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
        # replace first two ints after hold(
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
        if taps_blob:
            kept: list[str] = []
            for tm in re.finditer(r"arctap\((\d+)\)", taps_blob, re.IGNORECASE):
                at = int(tm.group(1))
                if nt1 <= at <= nt2:
                    kept.append(f"arctap({_transform_time(at, start_ms, speed)})")
            out += "[" + ",".join(kept) + "]" if kept else "[]"
        out += ";"
        return out

    # Unknown line: keep as-is (but this may contain time). We keep it for now.
    return stripped


def _slice_block(lines: list[str], s: int, e: int, start_ms: int, speed: float) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # timinggroup(...) { ... };
        # Handle both same-line brace (timinggroup(...){) and brace on next line.
        if stripped.lower().startswith("timinggroup"):
            # Collect the full header up to and including the opening '{'.
            group_header_parts = [stripped]
            j = i + 1
            while "{" not in stripped and j < len(lines):
                stripped = lines[j].strip()
                group_header_parts.append(stripped)
                j += 1

            if "{" not in "".join(group_header_parts):
                # No opening brace found – treat as unknown line
                sliced = _slice_line_simple(line, s, e, start_ms, speed)
                if sliced is not None:
                    out.append(sliced)
                i += 1
                continue

            # Use group_header_parts up to the '{' part
            full_header = " ".join(group_header_parts)
            group_header = full_header.split("{", 1)[0].rstrip()

            brace = sum(p.count("{") - p.count("}") for p in group_header_parts)
            inner: list[str] = []
            i = j
            while i < len(lines) and brace > 0:
                l2 = lines[i]
                brace += l2.count("{") - l2.count("}")
                if brace > 0:
                    inner.append(l2)
                i += 1

            # Process inner lines recursively
            inner_out = _slice_block(inner, s, e, start_ms, speed)
            out.append(group_header + "{")
            out.extend(inner_out)
            out.append("};")
            continue

        sliced = _slice_line_simple(line, s, e, start_ms, speed)
        if sliced is not None:
            out.append(sliced)
        i += 1

    # trim trailing empty lines
    while out and out[-1] == "":
        out.pop()
    return out


def slice_aff(aff_text: str, start_ms: int, end_ms: int, speed: float) -> str:
    header, body = _extract_header_and_body(aff_text)

    # Ensure timing at t=0 exists: keep the last timing <= start_ms
    timings = _parse_timings(body)
    base_timing_line: str | None = None
    if timings:
        chosen = None
        for t in timings:
            if t.t <= start_ms:
                chosen = t
            else:
                break
        if chosen is None:
            chosen = timings[0]
        base_timing_line = f"timing(0,{chosen.bpm:.2f},{chosen.beats:.2f});"

    out_body = _slice_block(body, start_ms, end_ms, start_ms, speed)

    # If we didn't keep any timing at 0, inject base timing at top
    if base_timing_line is not None:
        has_t0 = any(re.match(r"\s*timing\(0,", ln.replace(" ", ""), re.IGNORECASE) for ln in out_body)
        if not has_t0:
            out_body.insert(0, base_timing_line)

    # Join with newline; preserve header exactly as read
    out_lines = header + out_body
    return "\n".join(out_lines).rstrip() + "\n"
