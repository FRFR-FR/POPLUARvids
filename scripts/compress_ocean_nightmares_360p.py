#!/usr/bin/env python3
"""Create an ultra-compressed 360p copy and a readable narration script."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INPUTS = ROOT / "downloads" / "720p"
OUT = ROOT / "production_output_360p"
SOURCE_NAME = "15-minute-visual-edit-silent-preview.mp4"
OUTPUT_NAME = "ocean-nightmares-360p-ultra-compressed.mp4"


def run(args):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError("Command failed:\n" + result.stderr[-3000:])
    return result.stdout


def probe(path):
    data = json.loads(run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,size:stream=codec_type,codec_name,width,height",
        "-of", "json", path
    ]))
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return float(data.get("format", {}).get("duration", 0)), int(data.get("format", {}).get("size", 0)), video, data.get("streams", [])


def make_narration_script():
    sections = json.loads((ROOT / "narration.json").read_text(encoding="utf-8"))
    total = sum(int(s.get("target_seconds", 0)) for s in sections)
    if total != 900:
        raise RuntimeError(f"Narration timing is {total}s, expected 900s.")
    lines = [
        "7 MOST DANGEROUS CREATURES IN THE OCEAN",
        "FULL NARRATION SCRIPT",
        "Planned total duration: 15:00",
        "Note: this is the written voiceover script. The supplied video render is a silent visual edit.",
        ""
    ]
    for section in sections:
        title = section.get("title", section.get("id", "Section"))
        duration = int(section.get("target_seconds", 0))
        text = (section.get("text") or "").strip()
        if not text:
            raise RuntimeError(f"Narration section is empty: {title}")
        lines.extend([
            title.upper(),
            f"Planned section duration: {duration // 60}:{duration % 60:02d}",
            "",
            text,
            "",
            "-" * 68,
            ""
        ])
    (OUT / "narration_script.txt").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return len(sections), total


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    candidates = list(INPUTS.rglob(SOURCE_NAME)) if INPUTS.exists() else []
    if not candidates:
        raise RuntimeError(f"Could not find {SOURCE_NAME} under {INPUTS}")
    source = candidates[0]
    in_duration, in_size, _, _ = probe(source)
    if abs(in_duration - 900) > 1.0:
        raise RuntimeError(f"Source duration is {in_duration:.2f}s, expected 900s.")

    target = OUT / OUTPUT_NAME
    # Low-bitrate 640x360 H.264 at 24 fps. The source is intentionally silent.
    run([
        "ffmpeg", "-nostdin", "-hide_banner", "-y", "-i", source,
        "-vf", "scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=24,format=yuv420p",
        "-an", "-c:v", "libx264", "-preset", "slow", "-profile:v", "main",
        "-level:v", "3.0", "-b:v", "180k", "-maxrate", "200k", "-bufsize", "360k",
        "-movflags", "+faststart", "-sn", "-dn", target
    ])
    out_duration, out_size, video, streams = probe(target)
    if abs(out_duration - 900) > 1.0:
        raise RuntimeError(f"Compressed video duration is {out_duration:.2f}s, expected 900s.")
    if (video.get("width"), video.get("height")) != (640, 360):
        raise RuntimeError(f"Unexpected output dimensions: {video.get('width')}x{video.get('height')}.")
    if video.get("codec_name") != "h264":
        raise RuntimeError("Output is not H.264.")
    if any(s.get("codec_type") == "audio" for s in streams):
        raise RuntimeError("Expected silent visual preview, but an audio stream was found.")
    if out_size >= in_size:
        raise RuntimeError("Compressed file is not smaller than the 720p source.")

    section_count, script_seconds = make_narration_script()
    source_credits = ROOT / "downloads" / "720p" / "sources.txt"
    if source_credits.exists():
        (OUT / "sources.txt").write_bytes(source_credits.read_bytes())

    reduction = (1 - out_size / in_size) * 100
    report = (
        "SUCCESS — ULTRA-COMPRESSED 360p COPY\n"
        f"Video: {target.name}\n"
        "Resolution: 640x360 (360p)\n"
        "Frame rate: 24 fps\n"
        "Video codec: H.264\n"
        "Average video bitrate target: 180 kbps\n"
        "Audio: none (silent visual edit)\n"
        f"Runtime: {out_duration:.2f} seconds (15:00)\n"
        f"Compressed MP4 size: {out_size:,} bytes ({out_size / 1_000_000:.2f} MB)\n"
        f"720p source MP4 size: {in_size:,} bytes ({in_size / 1_000_000:.2f} MB)\n"
        f"Reduction against source MP4: {reduction:.1f}%\n"
        f"Narration script: narration_script.txt ({section_count} sections, {script_seconds}s planned)\n"
        "Original 720p and 1080p artifacts were not modified.\n"
    )
    (OUT / "compression_report.txt").write_text(report, encoding="utf-8")
    print(report, flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "build_error.txt").write_text(
            "BUILD NOT COMPLETED\n" + type(exc).__name__ + ": " + str(exc) + "\n",
            encoding="utf-8"
        )
        print("BUILD NOT COMPLETED:", type(exc).__name__, str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
