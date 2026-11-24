#!/usr/bin/env python3
"""Download the 60-shot manifest one clip at a time, with Pixabay candidate fallback.

A clip is accepted only after its candidate tags match the requested animal,
the file downloads, FFmpeg converts it to silent H.264 MP4, and ffprobe verifies it.
Failed candidates are skipped automatically; the script then advances to the next
manifest row. No rendering/assembly happens here.
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
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "clip_manifest.csv"
OUT = ROOT / "output" / "clips"
API = "https://pixabay.com/api/videos/"
KEY = os.environ.get("PIXABAY_API_KEY", "").strip()
USER_AGENT = "POPLUARvids-sequential-footage-downloader/1.0"
MAX_PAGES = 3
MIN_BYTES = 100_000
MIN_WIDTH = 1280

def species_for(filename, animal):
    name = filename.lower()
    if "jellyfish-squid" in name:
        if "_3" in name or "_6" in name:
            return [("jellyfish", ["jellyfish"])]
        if "_4" in name:
            return [("giant squid", ["giant squid"])]
        if "_5" in name:
            return [("glass squid", ["glass squid", "squid"])]
        return [("box jellyfish", ["box jellyfish", "box jelly"]), ("giant squid", ["giant squid"])]
    if "komodo" in name:
        return [("Komodo dragon", ["komodo dragon", "komodo"])]
    if "grizzly" in name:
        return [("grizzly bear", ["grizzly", "brown bear"])]
    if "african-lion" in name:
        return [("African lion", ["lion"])]
    if "bengal-tiger" in name:
        return [("Bengal tiger", ["bengal tiger", "tiger"])]
    if "spinosaurus" in name:
        return [("Spinosaurus", ["spinosaurus"])]
    if "t-rex" in name:
        return [("T. rex", ["tyrannosaurus rex", "t rex", "tyrannosaurus"])]
    if "megalodon" in name:
        return [("Megalodon", ["megalodon"])]
    if "great-white" in name:
        return [("Great white shark", ["great white", "white shark"])]
    if "saltwater-crocodile" in name:
        return [("Saltwater crocodile", ["saltwater crocodile", "estuarine crocodile"])]
    return [(animal, [animal.lower()])]

def shot_terms(shot):
    s = shot.lower()
    if "hook" in s:
        return "wildlife close up wide shot"
    if "eyes" in s or "stealth" in s:
        return "wildlife close up"
    if "lunge" in s or "movement" in s:
        return "wildlife moving walking swimming"
    if "jaws" in s or "teeth" in s:
        return "animal mouth close up"
    if "swimming" in s or "approach" in s:
        return "animal swimming underwater"
    if "feeding" in s or "prey" in s:
        return "wildlife feeding natural behaviour"
    if "tentacles" in s:
        return "tentacles underwater"
    if "deep-water" in s:
        return "deep sea underwater"
    return "wildlife natural behaviour"

def api_search(query, page):
    params = {
        "key": KEY, "q": query, "per_page": "20", "page": str(page),
        "safesearch": "true", "video_type": "all", "min_width": str(MIN_WIDTH),
        "order": "popular"
    }
    req = urllib.request.Request(
        API + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"Pixabay API HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))

def tag_matches(tags, aliases):
    normalized = re.sub(r"[^a-z0-9 ]", " ", (tags or "").lower())
    normalized = " ".join(normalized.split())
    return any(" ".join(a.lower().split()) in normalized for a in aliases)

def rendition_for(hit):
    videos = hit.get("videos") or {}
    options = sorted(videos.items(), key=lambda kv: (kv[1].get("width", 0), kv[1].get("size", 0)), reverse=True)
    for _, item in options:
        url = item.get("url", "")
        width = int(item.get("width") or 0)
        if url and width >= MIN_WIDTH and urllib.parse.urlparse(url).hostname == "cdn.pixabay.com":
            return item
    return None

def download_candidate(hit, row, destination):
    rendition = rendition_for(hit)
    if not rendition:
        return False, "No allowed rendition at required resolution"
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
        str(destination)
    ]
    converted = subprocess.run(cmd, capture_output=True, text=True)
    temp.unlink(missing_ok=True)
    if converted.returncode != 0 or not destination.exists() or destination.stat().st_size < MIN_BYTES:
        destination.unlink(missing_ok=True)
        return False, "FFmpeg conversion failed"

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_name,width,height",
         "-of", "json", str(destination)],
        capture_output=True, text=True
    )
    try:
        streams = json.loads(probe.stdout).get("streams", [])
    except Exception:
        streams = []
    if probe.returncode != 0 or not streams:
        destination.unlink(missing_ok=True)
        return False, "ffprobe verification failed"
    info = streams[0]
    if info.get("codec_name") != "h264" or int(info.get("width", 0)) < MIN_WIDTH:
        destination.unlink(missing_ok=True)
        return False, "verified output did not meet H.264/resolution requirement"

    return True, f"{destination.stat().st_size} bytes; {info['codec_name']} {info['width']}x{info['height']}"

def main():
    if not KEY:
        raise SystemExit("Missing PIXABAY_API_KEY GitHub Actions secret; key value was not printed.")
    with MANIFEST.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    OUT.mkdir(parents=True, exist_ok=True)
    used_ids = set()
    results = []
    total = len(rows)

    for index, row in enumerate(rows, 1):
        filename = row["filename"]
        destination = OUT / filename
        if destination.exists() and destination.stat().st_size >= MIN_BYTES:
            print(f"[{index}/{total}] Already present and retained: {filename}", flush=True)
            results.append({"filename": filename, "animal": row["animal"], "status": "already-present", "source": "", "pixabay_id": "", "details": f"{destination.stat().st_size} bytes"})
            continue

        accepted = False
        last_error = "No suitable candidate found"
        for species, aliases in species_for(filename, row["animal"]):
            queries = list(dict.fromkeys([f"{species} {shot_terms(row['shot'])}", species] + aliases))
            for query in queries:
                for page in range(1, MAX_PAGES + 1):
                    try:
                        data = api_search(query, page)
                    except Exception as exc:
                        last_error = f"Pixabay search failed: {type(exc).__name__}: {exc}"
                        print(f"  Search issue for {query} page {page}: {last_error}", flush=True)
                        continue
                    candidates = data.get("hits", [])
                    for hit in candidates:
                        pid = str(hit.get("id", ""))
                        if not pid or pid in used_ids:
                            continue
                        if not tag_matches(hit.get("tags", ""), aliases):
                            continue
                        used_ids.add(pid)
                        print(f"[{index}/{total}] {filename}: trying {species} candidate {pid}", flush=True)
                        ok, detail = download_candidate(hit, row, destination)
                        if not ok:
                            last_error = detail
                            print(f"  Candidate {pid} rejected: {detail}; trying next candidate.", flush=True)
                            continue

                        source_page = hit.get("pageURL", "")
                        contributor = hit.get("user", "")
                        with (OUT / "ATTRIBUTION.txt").open("a", encoding="utf-8") as f:
                            f.write(
                                f"File: {filename}\\nRequested animal: {row['animal']}\\n"
                                f"Shot: {row['shot']}\\nPixabay page: {source_page}\\n"
                                f"Contributor: {contributor}\\nPixabay ID: {pid}\\n"
                                f"License: Pixabay Content License (check the linked item page)\\n"
                                "Changes: converted to silent H.264 MP4.\\n\\n"
                            )
                        results.append({"filename": filename, "animal": row["animal"], "status": "downloaded", "source": source_page, "pixabay_id": pid, "details": detail})
                        print(f"  VERIFIED {filename}: {detail}. Moving to the next manifest item.", flush=True)
                        accepted = True
                        break
                    if accepted:
                        break
                    time.sleep(1)
                if accepted:
                    break
            if accepted:
                break
        if not accepted:
            print(f"[{index}/{total}] UNRESOLVED {filename}: {last_error}. Continuing to next clip.", flush=True)
            results.append({"filename": filename, "animal": row["animal"], "status": "unresolved", "source": "", "pixabay_id": "", "details": last_error})

    report_path = OUT / "download_report.csv"
    with report_path.open("w", newline="", encoding="utf-8") as f:
        fields = ["filename", "animal", "status", "source", "pixabay_id", "details"]
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(results)

    downloaded = sum(r["status"] == "downloaded" for r in results)
    present = sum(r["status"] == "already-present" for r in results)
    unresolved = sum(r["status"] == "unresolved" for r in results)
    print(f"FINAL: {downloaded} newly downloaded, {present} already present, {unresolved} unresolved, of {total} manifest clips.", flush=True)
    if unresolved:
        print("Some clips need new candidate sources; all successful downloads are retained in the artifact.", flush=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
