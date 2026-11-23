#!/usr/bin/env python3
import csv, os, re, subprocess, sys
from pathlib import Path
from urllib.parse import urlparse

queue = Path("approved_download_queue.csv")
out = Path("output")
out.mkdir(exist_ok=True)
allowed_hosts = {"archive.oceanexplorer.noaa.gov", "oceanexplorer.noaa.gov", "commons.wikimedia.org"}
rows = list(csv.DictReader(queue.open(newline="", encoding="utf-8")))
if not rows:
    print("Queue empty: no approved source URLs are waiting.")
    sys.exit(0)

for index, row in enumerate(rows, 1):
    name = row["filename"]
    animal = row["animal"]
    url = row["source_url"]
    host = urlparse(url).hostname or ""
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.mp4", name):
        raise SystemExit(f"Unsafe filename in queue: {name}")
    if urlparse(url).scheme != "https" or host not in allowed_hosts:
        raise SystemExit(f"Blocked unapproved host/source for {name}: {host}")
    print(f"[{index}/{len(rows)}] Downloading {name} ({animal})")
    src = Path("/tmp") / (name + ".source")
    subprocess.run(["curl", "-fL", "--retry", "3", "--retry-delay", "3",
                    "--connect-timeout", "20", url, "-o", str(src)], check=True)
    if src.stat().st_size < 100_000:
        raise SystemExit(f"Source too small; refusing to accept {name}")
    dest = out / name
    subprocess.run(["ffmpeg", "-y", "-i", str(src), "-an", "-c:v", "libx264",
                    "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(dest)], check=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=codec_name,width,height",
                            "-of", "csv=p=0", str(dest)], check=True,
                           capture_output=True, text=True).stdout.strip()
    if not dest.exists() or dest.stat().st_size < 100_000 or not probe:
        raise SystemExit(f"Verification failed for {name}")
    with (out / "ATTRIBUTION.txt").open("a", encoding="utf-8") as f:
        f.write(f"Title: {name}\nAnimal label: {animal}\nSource: {url}\n"
                f"Source page: {row['source_page']}\nCreator: {row['creator']}\n"
                f"License: {row['license']}\nChanges: converted to MP4; audio removed.\n\n")
    print(f"Saved and verified {name}: {dest.stat().st_size} bytes; {probe}")
    src.unlink(missing_ok=True)

print(f"Finished sequential queue: {len(rows)} clip(s) processed.")
