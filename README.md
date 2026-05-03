# Arcaea_slicer

A small offline tool to slice an Arcaea song folder into multiple clip-songs.

## What it does
Given an input folder:

```
songs/<song_id>/
  2.aff
  base.ogg
  base.jpg
```

and a `slides.json` describing segments (in milliseconds), this tool will create multiple new song folders:

```
<out>/songs/<song_id>_<s>_<e>/
  2.aff
  base.ogg
  base.jpg
  songlist_fragment.json
```

It also generates a `songlist_fragment.json` for each clip based on a template `songlist_example.json` (B-type: `{ "songs": [ ... ] }`).

## Requirements
- Python 3.10+
- `ffmpeg` available in PATH

## slides.json format
Keys:
- `s`: start_ms
- `e`: end_ms
- optional top-level `speed`: default speed multiplier (e.g. `1.25`). If CLI `--speed` is provided, it overrides this.

Example:

```json
{
  "speed": 1.0,
  "segments": [
    {"s": 30000, "e": 60000},
    {"s": 90000, "e": 120000}
  ]
}
```

## Usage

```bash
python -m arcaea_slicer \
  --songs-dir ./songs \
  --song-id mySong \
  --slides ./slides.json \
  --songlist-example ./songlist_example.json \
  --out ./out
```

Optional:
- `--speed 1.25` override speed from slides.json.

## Notes
- Speed change is **tempo only** (pitch preserved) using `ffmpeg` `atempo`.
- `.aff` slicing is best-effort and supports common commands (timing, tap, hold, arc/arctap, scenecontrol, camera, timinggroup).

