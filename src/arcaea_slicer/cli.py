from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from .ffmpeg import require_ffmpeg, slice_ogg
from .aff import slice_aff
from .songlist import make_songlist_fragment


@dataclass(frozen=True)
class Segment:
    start_ms: int
    end_ms: int


def _load_slides(path: Path) -> tuple[str | None, list[Segment], float | None]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    song_id = obj.get("song_id")
    speed = obj.get("speed")
    segments_raw = obj.get("segments")
    if not isinstance(segments_raw, list):
        raise ValueError("slides.json: 'segments' must be a list")

    segments: list[Segment] = []
    for i, seg in enumerate(segments_raw):
        if not isinstance(seg, dict):
            raise ValueError(f"slides.json: segments[{i}] must be an object")
        if "s" not in seg or "e" not in seg:
            raise ValueError(f"slides.json: segments[{i}] must contain 's' and 'e'")
        s = int(seg["s"])
        e = int(seg["e"])
        if s < 0 or e < 0 or s >= e:
            raise ValueError(f"slides.json: invalid segment at index {i}: s={s} e={e}")
        segments.append(Segment(start_ms=s, end_ms=e))

    return song_id, segments, (float(speed) if speed is not None else None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arcaea-slicer",
        description="Slice an Arcaea song folder (2.aff + base.ogg + base.jpg) into clip songs.",
    )
    parser.add_argument("--songs-dir", required=True, type=Path, help="Root containing songs/<song_id>/")
    parser.add_argument("--song-id", required=True, help="Input song id (directory name under songs)")
    parser.add_argument("--slides", required=True, type=Path, help="Path to slides.json")
    parser.add_argument("--songlist-example", required=True, type=Path, help="Path to songlist_example.json")
    parser.add_argument("--out", type=Path, default=Path("./out"), help="Output root directory")
    parser.add_argument(
        "--speed",
        type=float,
        default=None,
        help="Override speed (if omitted, use slides.json speed if present else 1.0)",
    )
    args = parser.parse_args(argv)

    require_ffmpeg()

    slides_song_id, segments, slides_speed = _load_slides(args.slides)
    speed = args.speed if args.speed is not None else (slides_speed if slides_speed is not None else 1.0)
    if speed <= 0:
        raise SystemExit("speed must be > 0")

    if slides_song_id and slides_song_id != args.song_id:
        # Non-fatal, just warn.
        print(f"[warn] slides.json song_id={slides_song_id!r} does not match --song-id={args.song_id!r}")

    in_song_dir = args.songs_dir / args.song_id
    in_aff = in_song_dir / "2.aff"
    in_ogg = in_song_dir / "base.ogg"
    in_jpg = in_song_dir / "base.jpg"

    for p in (in_aff, in_ogg, in_jpg):
        if not p.exists():
            raise SystemExit(f"Missing input file: {p}")

    out_songs_root = args.out / "songs"
    out_songs_root.mkdir(parents=True, exist_ok=True)

    for seg in segments:
        new_id = f"{args.song_id}_{seg.start_ms}_{seg.end_ms}"
        out_song_dir = out_songs_root / new_id
        out_song_dir.mkdir(parents=True, exist_ok=True)

        # Copy jacket
        shutil.copy2(in_jpg, out_song_dir / "base.jpg")

        # Slice audio
        slice_ogg(
            in_path=in_ogg,
            out_path=out_song_dir / "base.ogg",
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            speed=speed,
        )

        # Slice chart
        aff_text = in_aff.read_text(encoding="utf-8", errors="replace")
        new_aff = slice_aff(
            aff_text=aff_text,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            speed=speed,
        )
        (out_song_dir / "2.aff").write_text(new_aff, encoding="utf-8")

        # Songlist fragment
        frag = make_songlist_fragment(
            songlist_example_path=args.songlist_example,
            new_id=new_id,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            speed=speed,
        )
        (out_song_dir / "songlist_fragment.json").write_text(
            json.dumps(frag, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print(f"[ok] wrote {out_song_dir}")

    return 0
