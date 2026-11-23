#!/usr/bin/env python3
"""
7 Scariest Deep Sea Creatures: script-to-b-roll video builder (no AI credits).

What it does
  1. Makes a voiceover for each scene (edge-tts) OR uses your own voiceover file.
  2. For each scene, uses clips you put in assets/<scene-slug>/ first, then searches
     the Pixabay video API, filtering results by tags so off-topic clips are skipped.
  3. Cuts the clips into 5-second shots, scales them to 1080p, and stitches them
     to match each scene's narration length.
  4. Writes final.mp4, captions.srt and manifest.json (page URL of every clip used,
     so you can verify each license before publishing).

Setup
  pip install requests edge-tts
  FFmpeg + ffprobe must be installed and on your PATH.
  export PIXABAY_API_KEY=your_key      (Windows: set PIXABAY_API_KEY=your_key)

Run
  python deep_sea_video.py --dry-run          # search only, preview what it finds
  python deep_sea_video.py                    # full build with edge-tts voice
  python deep_sea_video.py --voiceover my.mp3 # use your own recording instead

Tip: Pixabay has little footage of real deep-sea animals. For the best result, drop
real clips (NOAA Ocean Exploration, Wikimedia Commons, etc. - check each license)
into assets/<slug>/ using the slugs in SCENES below.
"""
import argparse
import asyncio
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

W, H, FPS = 1920, 1080, 30
CLIP_SECONDS = 5.0      # max time each shot stays on screen
MIN_SEG = 2.5           # shortest usable piece of a source clip
GAP = 0.45              # pause after each scene's narration
API = "https://pixabay.com/api/videos/"

# Tags that mean "wrong footage" (fishing anglers, cartoons, AI, people, etc.)
BAD_SUBSTR = ["cartoon", "animat", "3d", "render", "cgi", "generated",
              "artificial intelligence", "illustration", "fishing", "fisherman"]
BAD_TOKENS = {"man", "woman", "people", "person", "boy", "girl", "child",
              "boat", "lake", "river", "pond", "fish tank", "sushi", "cooking",
              "restaurant", "market"}

SCENES = [
    {
        "slug": "intro",
        "title": "Intro",
        "queries": ["deep sea darkness", "bioluminescent ocean", "dark underwater abyss",
                    "jellyfish dark water"],
        "must": ["deep", "dark", "bioluminescen", "abyss", "jellyfish", "underwater", "ocean"],
        "text": (
            "A thousand meters down, the sunlight is gone. Not dim. Gone. Down here, the water "
            "is crushing, the cold is relentless, and food is so rare that every animal has had "
            "to evolve into something that looks like it crawled out of a nightmare. Most of the "
            "deep ocean has never been seen by human eyes, and the few creatures we have filmed "
            "look like monsters from a horror movie. But these aren't monsters. They're survivors. "
            "Every tooth, every glowing lure, every impossible jaw exists for one reason: to make "
            "sure the next meal doesn't get away. Today, we're counting down seven of the most "
            "terrifying animals living in the dark. And number one might make you never look at "
            "the ocean the same way again."
        ),
    },
    {
        "slug": "giant-isopod",
        "title": "7. Giant Isopod",
        "queries": ["giant isopod", "isopod", "deep sea crustacean", "crustacean macro"],
        "must": ["isopod", "crustacean", "amphipod", "woodlouse", "pill bug"],
        "text": (
            "Number seven: the giant isopod. Picture a pill bug, the little creature you find "
            "under a rock in your garden. Now blow it up to the size of a football, or even bigger. "
            "Some giant isopods grow longer than forty centimeters. They crawl along the freezing "
            "seafloor on fourteen legs, wearing armored plates like a medieval knight, with two "
            "huge compound eyes staring into the darkness. They are scavengers, and when a dead "
            "whale or fish sinks down, they swarm the carcass and eat until their bodies are almost "
            "too full to move. Then they simply wait. Giant isopods can survive an astonishingly "
            "long time without food. One captive isopod in a Japanese aquarium famously went more "
            "than five years without a single meal. If something threatens them, they curl into a "
            "tight armored ball, just like the bugs in your garden. Only this one is the size of a "
            "football. It is slow, it is patient, and it is always waiting for the next free meal "
            "to fall from above."
        ),
    },
    {
        "slug": "vampire-squid",
        "title": "6. Vampire Squid",
        "queries": ["vampire squid", "squid", "cephalopod", "octopus tentacles"],
        "must": ["squid", "cephalopod", "octopus", "cuttlefish", "tentacle"],
        "text": (
            "Number six: the vampire squid from hell. Yes, that is its real scientific name, "
            "Vampyroteuthis infernalis. It has eyes that can glow red or blue, dark webbed arms, "
            "and a body that looks like it is wrapped in a cloak. But here is the twist: it is not "
            "a squid, and it is not an octopus. It is the only surviving member of its own ancient "
            "group. And its defense is bizarre. Instead of squirting ink, it shoots out a cloud of "
            "glowing mucus filled with blue lights, dazzling its attacker while the animal vanishes "
            "into the dark. When it is truly frightened, it flips its arms up over its body, turning "
            "itself inside out like an umbrella, bristling with soft spines. The strangest part is "
            "how gentle it really is. It drifts through the oxygen-starved layers of the ocean, and "
            "instead of hunting, it collects falling bits of dead matter, called marine snow, using "
            "two long sticky threads. A nightmare in appearance, a gentle drifter in real life."
        ),
    },
    {
        "slug": "goblin-shark",
        "title": "5. Goblin Shark",
        "queries": ["goblin shark", "shark jaws", "shark teeth", "deep sea shark"],
        "must": ["shark"],
        "text": (
            "Number five: the goblin shark. It looks like something designed by a horror movie "
            "studio. A long flat snout, a pale pink body, and a face that seems put together from "
            "spare parts. The pink color is not paint. The skin is so thin that you can see the "
            "blood vessels underneath. Goblin sharks belong to a lineage that stretches back well "
            "over a hundred million years, which is why scientists call them living fossils. But the "
            "real horror happens in a split second. When prey drifts near, the shark's entire jaw "
            "launches forward out of its face, lined with sharp, needle-like teeth, and snaps the "
            "animal up. Then the jaw slides back into place. It happens so fast that it has only "
            "been filmed a handful of times. Imagine swimming in complete darkness, never knowing "
            "that something is quietly approaching, until its mouth reaches out for you."
        ),
    },
    {
        "slug": "viperfish",
        "title": "4. Viperfish",
        "queries": ["viperfish", "fish teeth", "bioluminescent fish", "deep sea fish"],
        "must": ["viperfish", "fang", "teeth", "bioluminescen", "deep sea"],
        "text": (
            "Number four: the viperfish. Meet an animal whose teeth are so long that its mouth "
            "cannot fully close around them. The fangs curve up in front of its eyes. A viperfish "
            "is only about thirty centimeters long, but it is all weapon. Along its belly, rows of "
            "glowing organs called photophores light up in the darkness, and a long spine on its "
            "back dangles a glowing lure above its head. A hungry fish sees the light, swims "
            "closer, and then the viperfish strikes at astonishing speed, impaling its prey on "
            "those needle-like fangs. It can even swing its head upward to open its jaws extra "
            "wide. Some viperfish rise toward the surface at night and sink back into the deep "
            "during the day, in one of the largest migrations on Earth. And they do it all in a "
            "world where meals are rare, so every single strike has to count."
        ),
    },
    {
        "slug": "fangtooth",
        "title": "3. Fangtooth",
        "queries": ["fangtooth fish", "fish teeth", "deep sea fish teeth", "dark fish open mouth"],
        "must": ["fangtooth", "fang", "teeth", "deep sea", "predator"],
        "text": (
            "Number three: the fangtooth. If the viperfish has long teeth, the fangtooth has some "
            "of the longest teeth, relative to its body size, of any fish in the ocean. Its two "
            "lower fangs are so enormous that they cannot fit inside its mouth. So the fish evolved "
            "special sockets in the roof of its mouth, letting the teeth slide in when it closes. "
            "Without them, those fangs would risk piercing its own skull. The fangtooth is small, "
            "only about sixteen centimeters long, with a huge head, dark skin, and a face that "
            "looks permanently angry. It lives in some of the deepest waters where fish have ever "
            "been found, in cold, crushing darkness. And because food is so hard to find down "
            "there, the fangtooth does not wait for the perfect meal. It will bite almost anything "
            "it meets. One tiny fish, a mouth full of daggers, and absolutely no manners."
        ),
    },
    {
        "slug": "colossal-squid",
        "title": "2. Colossal Squid",
        "queries": ["colossal squid", "giant squid", "squid eye", "squid tentacles"],
        "must": ["squid", "cephalopod", "tentacle", "octopus"],
        "text": (
            "Number two: the colossal squid. Most of us have heard of the giant squid, but the "
            "colossal squid may be even more terrifying. It lives in the freezing waters around "
            "Antarctica, and it can reach lengths of around ten meters, with a body that is "
            "thicker and heavier than any other squid. Its eyes may be the largest in the animal "
            "kingdom, as wide as a dinner plate, built to catch even the tiniest flicker of light "
            "in the dark. And its arms are armed with something few other squid have: sharp, "
            "swiveling hooks that rotate on the tentacles, ready to tear into prey. Scientists "
            "know it mostly from specimens found in the bellies of sperm whales, or caught by "
            "accident in fishing nets. A live one has only very recently been filmed in its natural "
            "habitat. That is the scariest part. We are still discovering how big the monsters "
            "down there can get."
        ),
    },
    {
        "slug": "anglerfish",
        "title": "1. Anglerfish",
        "queries": ["anglerfish", "deep sea anglerfish", "bioluminescent lure fish", "glowing fish dark"],
        "must": ["anglerfish", "deep sea", "bioluminescen", "lure"],
        "text": (
            "And number one: the anglerfish. This is the creature that defines the deep sea "
            "nightmare. In the pitch black, a female anglerfish carries a glowing lure on a long "
            "spine that sticks out of her head, like a fishing rod with a lantern. The light comes "
            "from bacteria living inside it. Curious prey swims toward the glow, and then she "
            "opens a mouth full of long, needle-sharp teeth and snaps it shut in a fraction of a "
            "second. Her stomach can stretch so she can swallow fish nearly as big as herself. "
            "But the strangest part is her love life. In some species, the males are tiny, and when "
            "one finds a female, he bites onto her body and never lets go. Over time his skin and "
            "blood vessels fuse with hers, and he becomes little more than a permanent attachment. "
            "Glowing bait, deadly teeth, and a partner who becomes part of her body. That is why "
            "the anglerfish takes the top spot."
        ),
    },
    {
        "slug": "outro",
        "title": "Outro",
        "queries": ["deep sea darkness", "jellyfish dark water", "bioluminescent ocean"],
        "must": ["deep", "dark", "bioluminescen", "abyss", "jellyfish", "underwater", "ocean"],
        "text": (
            "So there you have it: seven creatures that look like nightmares, but are really "
            "masterpieces of survival. Every strange tooth, glowing lure and stretching jaw exists "
            "because the deep ocean gives no second chances. And here is the most unsettling "
            "thought of all: scientists believe we have explored only a small fraction of the deep "
            "sea. Somewhere down there, in the darkness, there are animals that no human has ever "
            "seen. Which of these seven creatures was the scariest to you? Let me know in the "
            "comments, and subscribe if you want to keep exploring the strangest places on Earth."
        ),
    },
]


# ---------------------------------------------------------------- helpers
def run(cmd):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"Command failed: {' '.join(map(str, cmd))}\n{r.stderr[-800:]}")
    return r.stdout


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "csv=p=0", path])
    return float(out.strip())


def words(text):
    return len(text.split())


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


# ---------------------------------------------------------------- audio
async def _tts(text, out, voice, rate):
    import edge_tts
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def make_audio(args, work):
    """Returns (audio_path, [scene_durations])."""
    if args.voiceover:
        total = duration(args.voiceover)
        total_words = sum(words(s["text"]) for s in SCENES)
        return Path(args.voiceover), [total * words(s["text"]) / total_words for s in SCENES]

    adir = work / "audio"
    adir.mkdir(parents=True, exist_ok=True)
    parts, durs = [], []
    for i, s in enumerate(SCENES):
        mp3, m4a = adir / f"{i:02}.mp3", adir / f"{i:02}.m4a"
        if not m4a.exists():
            print(f"  voice: {s['title']}")
            asyncio.run(_tts(s["text"], mp3, args.voice, args.rate))
            run(["ffmpeg", "-y", "-i", mp3, "-af", f"apad=pad_dur={GAP}",
                 "-ar", "44100", "-ac", "2", "-c:a", "aac", m4a])
        parts.append(m4a)
        durs.append(duration(m4a))
    out = work / "voice.m4a"
    concat(parts, out)
    return out, durs


# ---------------------------------------------------------------- footage
def search(key, q):
    r = requests.get(API, params={"key": key, "q": q, "video_type": "film",
                                  "per_page": 30, "safesearch": "true"}, timeout=30)
    time.sleep(0.8)  # stay well under Pixabay's rate limit
    r.raise_for_status()
    return r.json().get("hits", [])


def is_good(hit, scene):
    tags = hit.get("tags", "").lower()
    if any(b in tags for b in BAD_SUBSTR) or re.search(r"\bai\b", tags):
        return False
    if {t.strip() for t in tags.split(",")} & BAD_TOKENS:
        return False
    if hit.get("duration", 0) < 4:
        return False
    return any(m in tags for m in scene["must"])


def pick_url(hit, quality):
    v = hit.get("videos", {})
    for k in (quality, "medium", "small", "large"):
        if v.get(k, {}).get("url"):
            return v[k]["url"]
    return None


def download(url, dest):
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=90) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def gather(scene, need_s, args, work):
    clips = []
    for p in sorted((Path("assets") / scene["slug"]).glob("*")):
        if p.suffix.lower() in (".mp4", ".mov", ".webm", ".mkv"):
            clips.append({"path": p, "dur": duration(p), "source": "local", "page": str(p)})

    target = math.ceil(need_s / CLIP_SECONDS) + 2

    def capacity():
        return sum(max(1, min(2, int(c["dur"] // CLIP_SECONDS))) for c in clips)

    seen = set()
    for q in scene["queries"]:
        if capacity() >= target:
            break
        for hit in search(args.key, q):
            if capacity() >= target:
                break
            if hit["id"] in seen or not is_good(hit, scene):
                continue
            seen.add(hit["id"])
            url = pick_url(hit, args.quality)
            if not url:
                continue
            info = {"source": "pixabay", "page": hit["pageURL"], "tags": hit["tags"], "query": q}
            if args.dry_run:
                clips.append({**info, "path": None, "dur": float(hit.get("duration", 5))})
                continue
            dest = work / "dl" / f"pix_{hit['id']}.mp4"
            download(url, dest)
            clips.append({**info, "path": dest, "dur": duration(dest)})
    return clips


def plan(clips, need_s):
    segs, total, r = [], 0.0, 0
    while clips and total < need_s - 0.05 and r < 60:
        for c in clips:
            if total >= need_s - 0.05:
                break
            start = r * CLIP_SECONDS
            if start + MIN_SEG > c["dur"]:  # ran out of new footage: reuse a different part
                start = start % max(c["dur"] - MIN_SEG, 0.1)
            length = min(CLIP_SECONDS, c["dur"] - start, need_s - total)
            if length < 0.4:
                continue
            segs.append((c, start, length))
            total += length
        r += 1
    return segs, total


def cut(src, start, length, out):
    run(["ffmpeg", "-y", "-ss", f"{start:.2f}", "-t", f"{length:.2f}", "-i", src, "-an",
         "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", out])


def black(length, out):
    run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=black:s={W}x{H}:r={FPS}",
         "-t", f"{length:.2f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", out])


def concat(files, out):
    lst = Path(out).with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(f).resolve().as_posix()}'\n" for f in files))
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", out])


# ---------------------------------------------------------------- captions
def write_srt(durs, path):
    lines, t, n = [], 0.0, 1
    for s, d in zip(SCENES, durs):
        sents = re.split(r"(?<=[.!?])\s+", s["text"].strip())
        chars = sum(len(x) for x in sents)
        speak = max(d - GAP, 1)
        cur = t
        for x in sents:
            span = speak * len(x) / chars
            lines.append(f"{n}\n{srt_time(cur)} --> {srt_time(cur + span)}\n{x}\n")
            cur += span
            n += 1
        t += d
    Path(path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default=os.environ.get("PIXABAY_API_KEY"), help="Pixabay API key")
    ap.add_argument("--voiceover", help="your own voiceover file (mp3/wav/m4a)")
    ap.add_argument("--voice", default="en-US-GuyNeural", help="edge-tts voice")
    ap.add_argument("--rate", default="-8%", help="edge-tts speed, e.g. -8%% slows it down")
    ap.add_argument("--quality", default="medium", choices=["tiny", "small", "medium", "large"])
    ap.add_argument("--dry-run", action="store_true", help="search only, no downloads or render")
    ap.add_argument("--work", default="work")
    ap.add_argument("--out", default="final.mp4")
    args = ap.parse_args()

    if not args.key:
        sys.exit("Set PIXABAY_API_KEY or pass --key.")
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        durs = [words(s["text"]) / 2.5 for s in SCENES]
        audio = None
    else:
        print("Making voiceover...")
        audio, durs = make_audio(args, work)
    print(f"Narration length: {sum(durs) / 60:.1f} min")

    manifest, scene_videos = [], []
    for i, (s, need) in enumerate(zip(SCENES, durs)):
        print(f"[{i + 1}/{len(SCENES)}] {s['title']} ({need:.0f}s)")
        clips = gather(s, need, args, work)
        segs, total = plan(clips, need)
        print(f"   {len(clips)} clips found, {len(segs)} shots planned")
        manifest.append({"scene": s["title"], "clips": [
            {k: str(v) for k, v in c.items() if k != "dur"} for c in clips]})
        if args.dry_run:
            continue

        sdir = work / "scenes" / f"{i:02}"
        sdir.mkdir(parents=True, exist_ok=True)
        files = []
        for j, (c, start, length) in enumerate(segs):
            f = sdir / f"{j:03}.mp4"
            cut(c["path"], start, length, f)
            files.append(f)
        if total < need - 0.1:
            print("   WARNING: not enough footage, filling with black. "
                  f"Add clips to assets/{s['slug']}/")
            f = sdir / "fill.mp4"
            black(need - total, f)
            files.append(f)
        sv = work / "scenes" / f"scene_{i:02}.mp4"
        concat(files, sv)
        scene_videos.append(sv)

    Path("manifest.json").write_text(json.dumps(manifest, indent=2))
    if args.dry_run:
        print("Dry run done. See manifest.json for the clips it would use.")
        return

    video = work / "video_only.mp4"
    concat(scene_videos, video)
    run(["ffmpeg", "-y", "-i", video, "-i", audio, "-c:v", "copy", "-c:a", "aac",
         "-b:a", "192k", "-shortest", args.out])
    write_srt(durs, "captions.srt")
    print(f"Done: {args.out}, captions.srt, manifest.json")


if __name__ == "__main__":
    main()