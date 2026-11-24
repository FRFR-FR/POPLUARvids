#!/usr/bin/env python3
"""Download verified NOAA jellyfish/squid footage sequentially; no rendering."""
import csv, json, subprocess, urllib.request
from pathlib import Path

OUT = Path("output/noaa-clips")
ITEMS = [
    ("noaa_jellyfish_cyanea.mp4", "https://oceanexplorer.noaa.gov/wp-content/uploads/2018/07/jelly-1280x720-1.mp4", "Cyanea jellyfish", "NOAA Ocean Exploration, Windows to the Deep 2018", "https://oceanexplorer.noaa.gov/multimedia/video-playlist-invert-jellyfish/"),
    ("noaa_jellyfish_crossota.mp4", "https://oceanexplorer.noaa.gov/wp-content/uploads/2018/07/0424-jelly-1920x1080-2.mp4", "Crossota hydromedusa jellyfish", "NOAA Ocean Exploration, 2016 Deepwater Exploration of the Marianas", "https://oceanexplorer.noaa.gov/multimedia/video-playlist-best-jellyfish/"),
    ("noaa_jellies_glass_squid.mp4", "https://oceanexplorer.noaa.gov/wp-content/uploads/2023/07/dive01-unexplored-planet-1920x1080-1.mp4", "Jellies and blinking glass squid", "NOAA Ocean Exploration, Seascape Alaska", "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-seascape-alaska-ex2304-gallery-media-dive01-unexplored-planet/"),
    ("noaa_squid_illex.mp4", "https://oceanexplorer.noaa.gov/wp-content/uploads/2021/11/dive09-mollusk-monday-1280x720-1.mp4", "Illex squid", "NOAA Ocean Exploration, Windows to the Deep 2021", "https://oceanexplorer.noaa.gov/multimedia/okeanos-explorations-ex2107-gallery-media-dive09-mollusk-monday/"),
    ("noaa_deepsea_jellies_squid.mp4", "https://oceanexplorer.noaa.gov/wp-content/uploads/2018/05/dark-1280x720-1.mp4", "Jellyfish, siphonophores and piglet squid among other midwater organisms", "NOAA Ocean Exploration, Deep-Sea Symphony", "https://oceanexplorer.noaa.gov/multimedia/video-playlist-ex1708-hiding-dark/"),
]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    attribution = ["NOAA footage attribution and source records:"]
    for i, (name, url, subject, credit, page) in enumerate(ITEMS, 1):
        dest = OUT / name
        temp = OUT / (name + ".source")
        if dest.exists() and dest.stat().st_size > 100_000:
            print(f"[{i}/{len(ITEMS)}] Retained existing {name}", flush=True)
            report.append((name, subject, "already-present", dest.stat().st_size, ""))
            continue
        print(f"[{i}/{len(ITEMS)}] Downloading {name} from NOAA", flush=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"POPLUARvids-NOAA-downloader/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r, temp.open("wb") as f:
                if r.status != 200: raise RuntimeError(f"HTTP {r.status}")
                while True:
                    b = r.read(1024*1024)
                    if not b: break
                    f.write(b)
            if temp.stat().st_size < 100_000: raise RuntimeError("source file too small")
            cmd = ["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-i",str(temp),"-an","-c:v","libx264","-preset","veryfast","-crf","21","-pix_fmt","yuv420p","-movflags","+faststart",str(dest)]
            p = subprocess.run(cmd, capture_output=True, text=True)
            if p.returncode: raise RuntimeError("FFmpeg conversion failed: " + p.stderr[-500:])
            probe = subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=codec_name,width,height","-of","json",str(dest)],capture_output=True,text=True)
            streams = json.loads(probe.stdout).get("streams", [])
            if probe.returncode or not streams or streams[0].get("codec_name") != "h264" or int(streams[0].get("width",0)) < 1280:
                raise RuntimeError("technical verification failed")
            detail = f"{dest.stat().st_size} bytes; H.264 {streams[0]['width']}x{streams[0]['height']}"
            print(f"  VERIFIED {name}: {detail}", flush=True)
            report.append((name, subject, "downloaded", dest.stat().st_size, detail))
            attribution.append(f"{name} | {subject} | {credit} | {page} | Public-domain NOAA footage; retain credit.")
        except Exception as e:
            dest.unlink(missing_ok=True)
            print(f"  FAILED {name}: {type(e).__name__}: {e}", flush=True)
            report.append((name, subject, "failed", 0, str(e)))
        finally:
            temp.unlink(missing_ok=True)
    with (OUT/"noaa_download_report.csv").open("w", newline="", encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(["filename","subject","status","bytes","details"]); w.writerows(report)
    (OUT/"ATTRIBUTION_NOAA.txt").write_text("\n".join(attribution)+"\n",encoding="utf-8")
    ok=sum(x[2] in ("downloaded","already-present") for x in report)
    failed=sum(x[2]=="failed" for x in report)
    print(f"NOAA FINAL: {ok} verified/present, {failed} failed, {len(ITEMS)} attempted.", flush=True)
    if failed: raise SystemExit(1)

if __name__ == "__main__": main()
