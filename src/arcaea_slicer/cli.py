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


def _do_slice(
    *,
    songs_dir: Path,
    song_id: str,
    slides_path: Path,
    songlist_example_path: Path,
    out_root: Path,
    speed_override: float | None,
) -> int:
    require_ffmpeg()

    slides_song_id, segments, slides_speed = _load_slides(slides_path)
    speed = speed_override if speed_override is not None else (slides_speed if slides_speed is not None else 1.0)
    if speed <= 0:
        raise SystemExit("speed must be > 0")

    if slides_song_id and slides_song_id != song_id:
        print(f"[warn] slides.json song_id={slides_song_id!r} does not match input song_id={song_id!r}")

    in_song_dir = songs_dir / song_id
    in_aff = in_song_dir / "2.aff"
    in_ogg = in_song_dir / "base.ogg"
    in_jpg = in_song_dir / "base.jpg"

    for p in (in_aff, in_ogg, in_jpg):
        if not p.exists():
            raise SystemExit(f"Missing input file: {p}")

    out_songs_root = out_root / "songs"
    out_songs_root.mkdir(parents=True, exist_ok=True)

    for seg in segments:
        new_id = f"{song_id}_{seg.start_ms}_{seg.end_ms}"
        out_song_dir = out_songs_root / new_id
        out_song_dir.mkdir(parents=True, exist_ok=True)

        shutil.copy2(in_jpg, out_song_dir / "base.jpg")

        slice_ogg(
            in_path=in_ogg,
            out_path=out_song_dir / "base.ogg",
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            speed=speed,
        )

        aff_text = in_aff.read_text(encoding="utf-8", errors="replace")
        new_aff = slice_aff(
            aff_text=aff_text,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            speed=speed,
        )
        (out_song_dir / "2.aff").write_text(new_aff, encoding="utf-8")

        frag = make_songlist_fragment(
            songlist_example_path=songlist_example_path,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="arcaea-slicer",
        description="Slice an Arcaea song folder (2.aff + base.ogg + base.jpg) into clip songs.",
    )

    # Simplified mode
    parser.add_argument(
        "--slice",
        metavar="SONG_ID",
        help=(
            "Simplified mode: only provide song id. Assumes ./songs/<id>/ and reads ./slides.json and "
            "./songlist_example.json. Outputs to ./out/songs/<new_id>/"
        ),
    )

    # Advanced mode
    parser.add_argument("--songs-dir", type=Path, default=Path("./songs"), help="Path to the songs/ folder (default: ./songs)")
    parser.add_argument("--song-id", help="Input song id (directory name under songs)")
    parser.add_argument("--slides", type=Path, default=Path("./slides.json"), help="Path to slides.json (default: ./slides.json)")
    parser.add_argument(
        "--songlist-example",
        type=Path,
        default=Path("./songlist_example.json"),
        help="Path to songlist_example.json (default: ./songlist_example.json)",
    )
    parser.add_argument("--out", type=Path, default=Path("./out"), help="Output root directory (default: ./out)")
    parser.add_argument(
        "--speed",
        type=float,
        default=None,
        help="Override speed (if omitted, use slides.json speed if present else 1.0)",
    )

    args = parser.parse_args(argv)

    if args.slice:
        # Fully simplified: all paths are defaults
        return _do_slice(
            songs_dir=Path("./songs"),
            song_id=args.slice,
            slides_path=Path("./slides.json"),
            songlist_example_path=Path("./songlist_example.json"),
            out_root=Path("./out"),
            speed_override=None,
        )

    # Advanced mode still supported
    if not args.song_id:
        raise SystemExit("Provide either --slice <song_id> or --song-id <song_id>")

    return _do_slice(
        songs_dir=args.songs_dir,
        song_id=args.song_id,
        slides_path=args.slides,
        songlist_example_path=args.songlist_example,
        out_root=args.out,
        speed_override=args.speed,
    )
