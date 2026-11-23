# POPLUARvids — 15-minute silent-footage edit

This repository contains the render pipeline for the 15-minute animal countdown video. It deliberately excludes the unrelated Three.js demo and does not generate or add narration.

## Output

- `output/animals-countdown-15min.mp4`
- 15:00 runtime, 1920x1080, 30 fps
- No audio stream
- Timeline follows the timestamps in the supplied narration script
- Only the 60 named shots in `clip_manifest.csv` are eligible sources

## Important source limitation

The supplied Pixabay URLs are **search pages**, not downloadable video files. They do not identify 50 specific, approved clip files. The NOAA URLs identify only a small number of clips and some are not footage of the exact animal named in the script (for example, a Greenland shark or hammerhead is not a great white). The renderer will not silently substitute unrelated footage or scrape a search page and pretend it is an approved clip.

To render, place the 60 chosen, rights-checked video files in `assets/clips/` using the exact filenames in `clip_manifest.csv`. Keep the source URL and license evidence in the manifest. The renderer stops with a clear list if any required file is missing.

## Render locally

Install FFmpeg, then run:

```bash
python render.py
```

The script uses FFmpeg to normalize each shot, mute all source audio, and assemble the 15-minute timeline. It never creates narration.

## GitHub Actions

Run **Actions → Render 15-minute video → Run workflow**. The workflow installs FFmpeg and Python dependencies, validates all 60 source clips, renders the MP4, and uploads it as a workflow artifact. It will fail before rendering if source clips are missing.

## Timing plan

- 00:00–01:30 — Hook montage
- 01:30–03:00 — #10 Box jellyfish / giant squid
- 03:00–04:30 — #9 Komodo dragon
- 04:30–06:00 — #8 Grizzly bear
- 06:00–07:30 — #7 African lion
- 07:30–09:00 — #6 Bengal tiger
- 09:00–10:30 — #5 Spinosaurus
- 10:30–12:00 — #4 T. rex
- 12:00–13:30 — #3 Megalodon
- 13:30–14:30 — #2 Great white shark
- 14:30–15:00 — #1 Saltwater crocodile

The supplied timestamps are treated as the edit's timing map. Since no narration audio is included, the video is timed to these script sections rather than synchronized to an actual spoken performance.
