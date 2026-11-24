#!/usr/bin/env python3
"""Render the 15-minute, silent seven-dangerous-ocean-creatures edit."""
from __future__ import annotations
import csv, json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "clip_manifest.csv"
CLIPS = ROOT / "assets" / "clips"
WORK = ROOT / "build"
OUT = ROOT / "output" / "7-most-dangerous-ocean-creatures-15min.mp4"
FPS = 30
WIDTH, HEIGHT = 1920, 1080

def run(cmd):
    subprocess.run(cmd, check=True)

def probe(path: Path) -> float:
    p = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], check=True, capture_output=True, text=True)
    return float(p.stdout.strip())

def main():
    if not MANIFEST.exists():
        sys.exit("Missing clip_manifest.csv")
    with MANIFEST.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    missing = [r["filename"] for r in rows if not (CLIPS / r["filename"]).is_file()]
    if len(rows) != 42:
        sys.exit(f"Expected 42 manifest entries; found {len(rows)}.")
    if missing:
        print("Cannot render: required ocean-creature footage is missing:", file=sys.stderr)
        for name in missing:
            print(f" - assets/clips/{name}", file=sys.stderr)
        sys.exit(2)

    WORK.mkdir(parents=True, exist_ok=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    rendered = []
    for i, row in enumerate(rows, 1):
        src = CLIPS / row["filename"]
        duration = float(row["duration_seconds"])
        if probe(src) < 0.25:
            sys.exit(f"Invalid/too-short video: {src}")
        dst = WORK / f"shot_{i:02d}.mp4"
        vf = (
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},fps={FPS},setsar=1"
        )
        run([
            "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(src),
            "-t", str(duration), "-an", "-vf", vf,
            "-c:v", "libx264", "-preset", "medium", "-crf", "19",
            "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart",
            str(dst)
        ])
        rendered.append(dst)

    concat = WORK / "concat.txt"
    concat.write_text("".join(f"file '{p.as_posix()}'\n" for p in rendered), encoding="utf-8")
    run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-an", "-c:v", "copy", "-movflags", "+faststart", str(OUT)
    ])
    actual = probe(OUT)
    if abs(actual - 900.0) > 1.0:
        sys.exit(f"Runtime check failed: expected 900s, got {actual:.2f}s")
    streams = subprocess.run([
        "ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
        "-of", "json", str(OUT)
    ], check=True, capture_output=True, text=True)
    types = [s["codec_type"] for s in json.loads(streams.stdout).get("streams", [])]
    if "audio" in types:
        sys.exit("Audio stream detected; refusing to publish.")
    print(f"Rendered: {OUT} ({OUT.stat().st_size / 1_000_000:.1f} MB; {actual:.2f}s; silent)")

if __name__ == "__main__":
    main()
