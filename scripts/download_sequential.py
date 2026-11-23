#!/usr/bin/env python3
import csv, re, subprocess, sys
from pathlib import Path
from urllib.parse import urlparse

queue = Path("approved_download_queue.csv")
out = Path("output")
out.mkdir(exist_ok=True)
allowed_hosts = {"oceanexplorer.noaa.gov", "archive.oceanexplorer.noaa.gov", "commons.wikimedia.org"}
rows = list(csv.DictReader(queue.open(newline="", encoding="utf-8")))
if not rows:
    print("Queue empty: no approved source URLs are waiting.")
    sys.exit(0)

failed = []
for index, row in enumerate(rows, 1):
    name, animal = row["filename"], row["animal"]
    urls = [u.strip() for u in [row.get("source_url", "")] + row.get("fallback_urls", "").split(";") if u.strip()]
    if not re.fullmatch(r"[A-Za-z0-9._-]+\.mp4", name):
        print(f"Skipping unsafe filename: {name}")
        failed.append(name)
        continue
    if not urls:
        print(f"No source candidates queued for {name}; moving to next clip.")
        failed.append(name)
        continue

    saved = False
    for attempt, url in enumerate(urls, 1):
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or host not in allowed_hosts:
            print(f"  Candidate {attempt}/{len(urls)} blocked: unapproved host {host}; trying next.")
            continue

        print(f"[{index}/{len(rows)}] {animal}: candidate {attempt}/{len(urls)}")
        src = Path("/tmp") / (name + f".{attempt}.source")
        dest = out / name
        src.unlink(missing_ok=True)
        dest.unlink(missing_ok=True)

        download = subprocess.run(
            ["curl", "-fL", "--retry", "1", "--retry-delay", "2",
             "--connect-timeout", "20", "--max-time", "240", url, "-o", str(src)],
            stdout=subprocess.DEVNULL
        )
        if download.returncode != 0 or not src.exists() or src.stat().st_size < 100_000:
            print(f"  Candidate {attempt} failed to download; trying the next source.")
            src.unlink(missing_ok=True)
            continue

        convert = subprocess.run(
            ["ffmpeg", "-nostdin", "-y", "-i", str(src), "-an", "-c:v", "libx264",
             "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", str(dest)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        if convert.returncode != 0 or not dest.exists() or dest.stat().st_size < 100_000:
            print(f"  Candidate {attempt} could not be converted; trying the next source.")
            src.unlink(missing_ok=True)
            dest.unlink(missing_ok=True)
            continue

        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name,width,height", "-of", "csv=p=0", str(dest)],
            capture_output=True, text=True
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            print(f"  Candidate {attempt} failed video verification; trying the next source.")
            src.unlink(missing_ok=True)
            dest.unlink(missing_ok=True)
            continue

        with (out / "ATTRIBUTION.txt").open("a", encoding="utf-8") as f:
            f.write(f"File: {name}\nAnimal label: {animal}\nSource: {url}\n"
                    f"Source page: {row['source_page']}\nCreator: {row['creator']}\n"
                    f"License: {row['license']}\n"
                    "Changes: converted to MP4; audio removed.\n\n")
        print(f"SUCCESS {name}: {dest.stat().st_size} bytes; {probe.stdout.strip()}")
        src.unlink(missing_ok=True)
        saved = True
        break

    if not saved:
        print(f"All {len(urls)} source candidates failed for {name}; continuing to next queued clip.")
        failed.append(name)

print(f"Queue processed: {len(rows) - len(failed)}/{len(rows)} clips saved.")
if failed:
    print("Unresolved clips: " + ", ".join(failed))
    sys.exit(1)
