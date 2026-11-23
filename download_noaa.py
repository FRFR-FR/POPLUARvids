#!/usr/bin/env python3
"""Download only the direct NOAA MP4 URLs explicitly listed in clip_manifest.csv.

Pixabay entries are search pages, not direct file URLs. This script intentionally
does not scrape Pixabay or perform bulk Pixabay downloads.
"""
import csv
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "clip_manifest.csv"
OUT = ROOT / "assets" / "clips"
ALLOWED_HOST = "archive.oceanexplorer.noaa.gov"

def main():
    with MANIFEST.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    OUT.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    for row in rows:
        url = row["source_reference"]
        host = (urlparse(url).hostname or "").lower()
        if host != ALLOWED_HOST:
            continue
        name = row["filename"]
        dest = OUT / name
        if dest.exists() and dest.stat().st_size > 1024:
            print(f"Already downloaded: {name} ({dest.stat().st_size} bytes)")
            continue
        print(f"Downloading NOAA source: {url}")
        request = urllib.request.Request(url, headers={"User-Agent": "POPLUARvids-footage-fetcher/1.0"})
        try:
            with urllib.request.urlopen(request, timeout=90) as response, dest.open("wb") as out:
                if response.status != 200:
                    raise RuntimeError(f"HTTP {response.status}")
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    out.write(block)
            if dest.stat().st_size < 1024:
                dest.unlink(missing_ok=True)
                raise RuntimeError("Downloaded response is too small to be a video")
            downloaded += 1
            print(f"Saved {name}: {dest.stat().st_size / 1_000_000:.2f} MB")
        except Exception as exc:
            dest.unlink(missing_ok=True)
            print(f"NOAA download failed for {name}: {exc}", file=sys.stderr)
    print(f"NOAA files downloaded this run: {downloaded}")

if __name__ == "__main__":
    main()
