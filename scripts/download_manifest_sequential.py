#!/usr/bin/env python3
"""Download the 42-shot ocean-creature manifest sequentially, with automatic Pixabay fallbacks.

A candidate is accepted only when its tags identify the requested species, the download
succeeds, FFmpeg creates a silent H.264 MP4, and ffprobe confirms at least 1280x720.
One clip is completed before the next manifest row is attempted. This script never renders.
"""
import csv
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "clip_manifest.csv"
OUT = ROOT / "output" / "clips"
API = "https://pixabay.com/api/videos/"
KEY = os.environ.get("PIXABAY_API_KEY", "").strip()
USER_AGENT = "POPLUARvids-ocean-footage-downloader/2.0"
MAX_PAGES = 4
MIN_BYTES = 100_000
MIN_WIDTH = 1280
MIN_HEIGHT = 720

SPECIES = {
    "box jellyfish": ("box jellyfish", ["box jellyfish", "sea wasp"]),
    "saltwater (estuarine) crocodile": ("saltwater crocodile", ["saltwater crocodile", "estuarine crocodile"]),
    "great white shark": ("great white shark", ["great white shark", "white shark"]),
    "bull shark": ("bull shark", ["bull shark"]),
    "tiger shark": ("tiger shark", ["tiger shark"]),
    "blue-ringed octopus": ("blue-ringed octopus", ["blue-ringed octopus", "blue ringed octopus"]),
    "reef stonefish": ("reef stonefish", ["reef stonefish", "stonefish"]),
}

def normalize(value):
    value = re.sub(r"[^a-z0-9 ]", " ", (value or "").lower())
    return " ".join(value.split())

def tag_matches(tags, aliases):
    normalized_tags = normalize(tags)
    return any(normalize(alias) in normalized_tags for alias in aliases)

def shot_terms(shot):
    s = shot.lower()
    if "opening" in s:
        return "underwater wildlife wide shot"
    if "close" in s or "details" in s:
        return "underwater close up"
    if "movement" in s or "cruising" in s:
        return "underwater swimming movement"
    if "camouflage" in s or "habitat" in s:
        return "ocean habitat reef seafloor"
    if "behaviour" in s:
        return "underwater natural behaviour"
    if "wide" in s:
        return "underwater wide view"
    return "underwater wildlife"

def api_search(query, page):
    params = {
        "key": KEY,
        "q": query,
        "per_page": "20",
        "page": str(page),
        "safesearch": "true",
        "video_type": "all",
        "min_width": str(MIN_WIDTH),
        "order": "popular",
    }
    req = urllib.request.Request(
        API + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"Pixabay API HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))

def rendition_for(hit):
    videos = hit.get("videos") or {}
    options = sorted(
        videos.items(),
        key=lambda kv: (kv[1].get("width", 0), kv[1].get("height", 0), kv[1].get("size", 0)),
        reverse=True,
    )
    for _, item in options:
        url = item.get("url", "")
        width = int(item.get("width") or 0)
        height = int(item.get("height") or 0)
        if (url and width >= MIN_WIDTH and height >= MIN_HEIGHT
                and urllib.parse.urlparse(url).hostname == "cdn.pixabay.com"):
            return item
    return None

def download_candidate(hit, destination):
    rendition = rendition_for(hit)
    if not rendition:
        return False, "No allowed rendition at 1280x720 or higher"

    source_url = rendition["url"]
    temp = Path("/tmp") / f"pixabay-{hit.get('id')}.source"
    temp.unlink(missing_ok=True)
    req = urllib.request.Request(source_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as response, temp.open("wb") as f:
            if response.status != 200:
                return False, f"download HTTP {response.status}"
            while True:
                block = response.read(1024 * 1024)
                if not block:
                    break
                f.write(block)
    except Exception as exc:
        temp.unlink(missing_ok=True)
        return False, f"download failed: {type(exc).__name__}: {exc}"

    if not temp.exists() or temp.stat().st_size < MIN_BYTES:
        temp.unlink(missing_ok=True)
        return False, "downloaded file too small"

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.unlink(missing_ok=True)
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(temp), "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "21", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(destination),
    ]
    converted = subprocess.run(cmd, capture_output=True, text=True)
    temp.unlink(missing_ok=True)
    if (converted.returncode != 0 or not destination.exists()
            or destination.stat().st_size < MIN_BYTES):
        destination.unlink(missing_ok=True)
        return False, "FFmpeg conversion failed"

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,width,height",
         "-of", "json", str(destination)],
        capture_output=True, text=True,
    )
    try:
        streams = json.loads(probe.stdout).get("streams", [])
    except Exception:
        streams = []
    if probe.returncode != 0 or not streams:
        destination.unlink(missing_ok=True)
        return False, "ffprobe verification failed"

    info = streams[0]
    if (info.get("codec_name") != "h264"
            or int(info.get("width", 0)) < MIN_WIDTH
            or int(info.get("height", 0)) < MIN_HEIGHT):
        destination.unlink(missing_ok=True)
        return False, "output did not meet H.264 / 1280x720 requirement"

    return True, f"{destination.stat().st_size} bytes; H.264 {info['width']}x{info['height']}"

def queries_for(species, aliases, shot):
    terms = shot_terms(shot)
    queries = [f"{species} {terms}", species]
    queries.extend(aliases)
    return list(dict.fromkeys(queries))

def main():
    if not KEY:
        raise SystemExit("Missing PIXABAY_API_KEY GitHub Actions secret; key value was not printed.")
    with MANIFEST.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 42:
        raise SystemExit(f"Expected 42 ocean-creature clips; found {len(rows)}.")

    OUT.mkdir(parents=True, exist_ok=True)
    used_ids = set()
    results = []
    total = len(rows)

    for index, row in enumerate(rows, 1):
        filename = row["filename"]
        animal = row["animal"]
        destination = OUT / filename
        species_entry = SPECIES.get(animal.lower())
        if not species_entry:
            raise SystemExit(f"No strict species match rule for manifest animal: {animal}")
        species, aliases = species_entry

        accepted = False
        last_error = "No matching, verified candidate found"

        if destination.exists():
            destination.unlink()

        for query in queries_for(species, aliases, row["shot"]):
            for page in range(1, MAX_PAGES + 1):
                try:
                    data = api_search(query, page)
                except Exception as exc:
                    last_error = f"Pixabay search failed: {type(exc).__name__}: {exc}"
                    print(f"  Search issue for {query!r}, page {page}: {last_error}", flush=True)
                    continue

                for hit in data.get("hits", []):
                    pid = str(hit.get("id", ""))
                    if not pid or pid in used_ids:
                        continue
                    if not tag_matches(hit.get("tags", ""), aliases):
                        continue

                    used_ids.add(pid)
                    print(f"[{index}/{total}] {filename}: trying {species} candidate {pid}", flush=True)
                    ok, detail = download_candidate(hit, destination)
                    if not ok:
                        last_error = detail
                        print(f"  Candidate {pid} rejected: {detail}; trying the next candidate.", flush=True)
                        continue

                    source_page = hit.get("pageURL", "")
                    contributor = hit.get("user", "")
                    attribution = OUT / "ATTRIBUTION.txt"
                    with attribution.open("a", encoding="utf-8") as f:
                        f.write(
                            f"File: {filename}\n"
                            f"Animal: {animal}\n"
                            f"Shot: {row['shot']}\n"
                            f"Pixabay page: {source_page}\n"
                            f"Contributor: {contributor}\n"
                            f"Pixabay ID: {pid}\n"
                            "License: Pixabay Content License; verify the item page before reuse\n"
                            "Changes: converted to silent H.264 MP4.\n\n"
                        )
                    results.append({
                        "filename": filename, "animal": animal, "status": "downloaded",
                        "source": source_page, "pixabay_id": pid, "details": detail,
                    })
                    print(f"  VERIFIED {filename}: {detail}. Advancing to the next clip.", flush=True)
                    accepted = True
                    break

                if accepted:
                    break
                time.sleep(0.5)
            if accepted:
                break

        if not accepted:
            print(f"[{index}/{total}] UNRESOLVED {filename}: {last_error}. Continuing.", flush=True)
            results.append({
                "filename": filename, "animal": animal, "status": "unresolved",
                "source": "", "pixabay_id": "", "details": last_error,
            })

    report_path = OUT / "download_report.csv"
    with report_path.open("w", newline="", encoding="utf-8") as f:
        fields = ["filename", "animal", "status", "source", "pixabay_id", "details"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    downloaded = sum(r["status"] == "downloaded" for r in results)
    unresolved = sum(r["status"] == "unresolved" for r in results)
    print(
        f"FINAL: {downloaded} verified downloads, {unresolved} unresolved, "
        f"of {total} ocean-creature clips.",
        flush=True,
    )
    if unresolved:
        print("Successful files are retained in the artifact; unresolved clips need new sources.", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
