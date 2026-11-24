# POPLUARvids — 7 Most Dangerous Creatures in the Ocean

This project is now a 15-minute wildlife documentary about seven dangerous marine and coastal-water animals. It uses real, species-matched footage only. No 3D visualisations or AI-generated animal footage are required.

## The seven creatures
1. Box jellyfish
2. Saltwater (estuarine) crocodile
3. Great white shark
4. Bull shark
5. Tiger shark
6. Blue-ringed octopus
7. Reef stonefish

This is an editorial selection, not a claim that one universal scientific ranking exists. The Florida Museum's International Shark Attack File identifies white, tiger, and bull sharks as the three shark species most repeatedly implicated in serious incidents. NOAA identifies the Australian box jellyfish as the most venomous marine animal; health authorities also warn about blue-ringed octopuses and stonefish. Estuarine crocodiles are dangerous in coastal waterways and sometimes come ashore on beaches.

## Footage plan
- 42 clips total: six different shot types per creature
- Each clip is budgeted for 21.428571 seconds of the edit
- Total target runtime: 900 seconds (15:00)
- Output footage: silent H.264 MP4, minimum 1280x720
- One candidate is downloaded and verified before the next clip is attempted
- Failed candidates are skipped automatically; the script tries the next species-matched candidate
- The report and creator/source attributions are uploaded with the footage artifact

## Download
Run **Actions → Download seven dangerous ocean creatures sequentially**. The workflow reads `PIXABAY_API_KEY` from the GitHub Actions secret, downloads one clip at a time, checks species tags and media format, and uploads the successful clips plus a CSV report.

The downloader does not print or expose the API key. It will leave a clip marked unresolved rather than silently substituting a different species.

## Rendering
Rendering remains a separate, manual workflow. It is intentionally not triggered by footage downloads. Before rendering, the 42 clips must be visually checked and placed under `assets/clips/` with their manifest filenames. The render script refuses to start when files are missing.
