#!/usr/bin/env python3
"""Search Pixabay's video API for the animal footage shortlist.
This script searches only; it does not bulk-download media.
"""
import csv, json, os, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
CACHE = ROOT / ".pixabay_cache"
API = "https://pixabay.com/api/videos/"
KEY = os.environ.get("PIXABAY_API_KEY", "").strip()
QUERIES = [
    ("box jellyfish", "Box jellyfish"), ("giant squid", "Giant squid"),
    ("Komodo dragon", "Komodo dragon"), ("grizzly bear", "Grizzly bear"),
    ("African lion", "African lion"), ("Bengal tiger", "Bengal tiger"),
    ("Spinosaurus", "Spinosaurus (CGI only)"), ("T rex dinosaur", "T. rex (CGI/skeleton only)"),
    ("Megalodon", "Megalodon (CGI/fossil only)"), ("great white shark", "Great white shark"),
    ("saltwater crocodile", "Saltwater crocodile"),
]

def fetch(query):
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE / (urllib.parse.quote(query, safe="") + ".json")
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            if 0 <= time.time() - float(cached["cached_at"]) < 86400:
                print(f"Using cached Pixabay search: {query}")
                return cached["data"]
        except Exception:
            pass
    params = {"key": KEY, "q": query, "per_page": "20", "page": "1",
              "safesearch": "true", "video_type": "film", "category": "animals",
              "min_width": "1280", "order": "popular"}
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "POPLUARvids-footage-shortlist/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=45) as response:
        if response.status != 200:
            raise RuntimeError(f"Pixabay returned HTTP {response.status} for {query}")
        data = json.loads(response.read().decode("utf-8"))
    cache_file.write_text(json.dumps({"cached_at": time.time(), "data": data}), encoding="utf-8")
    return data

def main():
    if not KEY:
        sys.exit("Missing PIXABAY_API_KEY repository secret. No key value was printed.")
    OUT.mkdir(parents=True, exist_ok=True)
    rows, errors = [], []
    for query, animal in QUERIES:
        try:
            data = fetch(query)
            hits = data.get("hits", [])
            print(f"{query}: {len(hits)} candidates returned")
            for hit in hits:
                renditions = hit.get("videos") or {}
                rendition = renditions.get("medium") or renditions.get("small") or {}
                url = rendition.get("url", "")
                if not url:
                    continue
                rows.append({
                    "search_query": query, "animal_section": animal,
                    "pixabay_id": hit.get("id", ""), "tags": hit.get("tags", ""),
                    "duration_seconds": hit.get("duration", ""),
                    "width": rendition.get("width", ""), "height": rendition.get("height", ""),
                    "estimated_size_mb": round((rendition.get("size", 0) or 0) / 1000000, 2),
                    "contributor": hit.get("user", ""), "source_page": hit.get("pageURL", ""),
                    "preview_video_url": url, "match_review_required": "YES",
                })
            time.sleep(1)
        except Exception as exc:
            errors.append(f"{query}: {type(exc).__name__}: {exc}")
            print(f"Search failed for {query}: {type(exc).__name__}: {exc}", file=sys.stderr)
    fields = ["search_query","animal_section","pixabay_id","tags","duration_seconds",
              "width","height","estimated_size_mb","contributor","source_page",
              "preview_video_url","match_review_required"]
    with (OUT / "pixabay_candidates.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    report = {"searched_at_utc": datetime.now(timezone.utc).isoformat(),
              "queries": len(QUERIES), "candidate_count": len(rows), "downloaded": 0,
              "errors": errors, "policy_note": "Shortlist only; no bulk media downloads performed."}
    (OUT / "pixabay_search_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Saved {len(rows)} candidates.")
    if errors:
        sys.exit(1)

if __name__ == "__main__":
    main()
