#!/usr/bin/env python3
"""Build a 15-minute entertainment edit with exact-species footage and Liam narration."""
import json, os, shutil, subprocess, sys, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "ocean_build"
OUT = ROOT / "production_output"
W, H, FPS = 1920, 1080, 30
DURS = {"intro":60,"reef_stonefish":110,"blue_ringed_octopus":110,"box_jellyfish":110,
        "tiger_shark":110,"bull_shark":110,"great_white_shark":110,"saltwater_crocodile":110,"outro":70}
assert sum(DURS.values()) == 900
UA = "POPLUARvids/1.1 (https://github.com/FRFR-FR/POPLUARvids/issues)"

MEDIA = [
 ("Gaboxjellyfish.jpg","box_jellyfish"),
 ("Box jellyfish (Carybdea sp.) (29889242658).jpg","box_jellyfish"),
 ("Box jellyfish (Carybdea sp.) (49187737008).jpg","box_jellyfish"),
 ("Jumping crocodile adelaide river australia.ogv","saltwater_crocodile"),
 ("Feeding a saltwater crocodile (Crocodylus porosus).webm","saltwater_crocodile"),
 ("Cage diving with great white sharks.webm","great_white_shark"),
 ("Great white shark as seen from a cage.webm","great_white_shark"),
 ("Bull sharks (Carcharhinus leucas) in Mexico.webm","bull_shark"),
 ("Tiger shark (Galeocerdo cuvier) in the Bahamas in 2017.webm","tiger_shark"),
 ("Tiger shark (Galeocerdo cuvier) in Fiji.webm","tiger_shark"),
 ("Blue-ringed octopus.jpg","blue_ringed_octopus"),
 ("Synanceia verrucosa 26195372.jpg","reef_stonefish"),
 ("Synanceia verrucosa 49756178.jpg","reef_stonefish"),
 ("Synanceia verrucosa 15645190.jpg","reef_stonefish"),
 ("Synanceia verrucosa 108702067.jpg","reef_stonefish"),
 ("Synanceia verrucosa 108702066.jpg","reef_stonefish"),
]
NOAA = ["noaa_jellyfish_cyanea.mp4","noaa_jellyfish_crossota.mp4",
        "noaa_jellies_glass_squid.mp4","noaa_squid_illex.mp4","noaa_deepsea_jellies_squid.mp4"]

def run(cmd):
    p = subprocess.run([str(x) for x in cmd], capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError("Command failed: " + " ".join(map(str,cmd)) + "\n" + p.stderr[-2500:])
    return p

def info(path):
    p=run(["ffprobe","-v","error","-show_entries","format=duration:stream=codec_type,width,height",
           "-of","json",path])
    j=json.loads(p.stdout)
    return float(j.get("format",{}).get("duration",0)),j.get("streams",[])

def fetch(url,dst):
    if dst.exists() and dst.stat().st_size>20000: return dst
    dst.parent.mkdir(parents=True,exist_ok=True)
    last_error=None
    for attempt in range(1,7):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"*/*"})
            with urllib.request.urlopen(req,timeout=180) as response,dst.open("wb") as f:
                while True:
                    b=response.read(1024*1024)
                    if not b: break
                    f.write(b)
            if dst.stat().st_size<20000: raise RuntimeError("Invalid media file: "+dst.name)
            return dst
        except urllib.error.HTTPError as exc:
            last_error=exc
            dst.unlink(missing_ok=True)
            if exc.code not in (429,503):
                raise
            retry=exc.headers.get("Retry-After")
            try: wait=max(5,int(retry)) if retry else min(60,5*attempt)
            except ValueError: wait=min(60,5*attempt)
            print(f"Rate-limited by Wikimedia; respecting retry delay of {wait}s.",flush=True)
            time.sleep(wait)
        except Exception as exc:
            last_error=exc
            dst.unlink(missing_ok=True)
            time.sleep(min(30,3*attempt))
    raise RuntimeError(f"Could not fetch {url} after retries: {last_error}")

def find_file(folder,name):
    hits=list(folder.rglob(name)) if folder.exists() else []
    return hits[0] if hits else None

def get_assets():
    groups={}
    media_dir=WORK/"media"
    for filename,animal in MEDIA:
        url="https://commons.wikimedia.org/wiki/Special:FilePath/"+urllib.parse.quote(filename.replace(" ","_"),safe="()_-.")
        try:
            p=fetch(url,media_dir/filename)
            groups.setdefault(animal,[]).append(p)
            print("Ready:",filename,flush=True)
        except Exception as exc:
            print("Optional source unavailable:",filename,str(exc),flush=True)
        time.sleep(5)
    for filename,animal in [
      ("31_blue-ringed-octopus_hook.mp4","blue_ringed_octopus"),
      ("13_great-white-shark_hook.mp4","great_white_shark"),
      ("14_great-white-shark_closeup.mp4","great_white_shark")
    ]:
        p=find_file(ROOT/"downloads"/"pixabay",filename)
        if p: groups.setdefault(animal,[]).append(p)
    groups["general_ocean"]=[]
    for filename in NOAA:
        p=find_file(ROOT/"downloads"/"noaa",filename)
        if p: groups["general_ocean"].append(p)
    required=["reef_stonefish","blue_ringed_octopus","box_jellyfish","tiger_shark",
              "bull_shark","great_white_shark","saltwater_crocodile"]
    missing=[x for x in required if not groups.get(x)]
    if missing: raise RuntimeError("Missing any visual source for: "+", ".join(missing))
    return groups

def make_shot(src,dst,seconds,index):
    ext=src.suffix.lower()
    if ext in (".jpg",".jpeg",".png",".webp"):
        frames=int(seconds*FPS)
        z="0.0007" if index%2==0 else "0.0005"
        vf=("scale=2600:-1,zoompan=z='min(zoom+"+z+",1.12)':"
            "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d="+str(frames)+
            ":s=1920x1080:fps=30,eq=contrast=1.08:saturation=0.84,vignette=PI/5,format=yuv420p")
        run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-loop","1","-i",src,
             "-t",seconds,"-vf",vf,"-an","-c:v","libx264","-preset","veryfast","-crf","21",
             "-r","30","-pix_fmt","yuv420p",dst])
        return
    dur,streams=info(src)
    v=next((x for x in streams if x.get("codec_type")=="video"),{})
    width,height=int(v.get("width",1920)),int(v.get("height",1080))
    start=0 if dur<seconds+0.5 else (index*7.3)%max(1,dur-seconds)
    loop=["-stream_loop","-1"] if dur<seconds+0.5 else []
    if height>width:
        fc=("[0:v]split=2[b][f];[b]scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,boxblur=24:10[bg];[f]scale=850:1080:force_original_aspect_ratio=decrease[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,eq=contrast=1.10:saturation=0.84,"
            "vignette=PI/5,fps=30,format=yuv420p[v]")
        filt=["-filter_complex",fc,"-map","[v]"]
    else:
        vf=("scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
            "eq=contrast=1.10:saturation=0.84,vignette=PI/5,fps=30,format=yuv420p")
        filt=["-vf",vf]
    run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",*loop,
         "-ss",f"{start:.2f}","-i",src,"-t",seconds,*filt,"-an",
         "-c:v","libx264","-preset","veryfast","-crf","21","-r","30",
         "-pix_fmt","yuv420p",dst])

def make_scene(slug,assets,seconds,title):
    folder=WORK/"scenes"/slug
    folder.mkdir(parents=True,exist_ok=True)
    parts=[];elapsed=0;index=0
    while elapsed<seconds-0.05:
        src=assets[index%len(assets)]
        is_image=src.suffix.lower() in (".jpg",".jpeg",".png",".webp")
        length=min(11 if is_image else 8,seconds-elapsed)
        part=folder/f"shot_{index:03}.mp4"
        make_shot(src,part,length,index)
        parts.append(part);elapsed+=length;index+=1
    concat=folder/"parts.txt"
    concat.write_text("".join("file '"+p.as_posix()+"'\n" for p in parts),encoding="utf-8")
    clean=folder/"clean.mp4"
    run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",concat,
         "-t",seconds,"-an","-c:v","libx264","-preset","veryfast","-crf","20","-r","30",
         "-pix_fmt","yuv420p",clean])
    safe=title.replace("'","").replace(":"," ")
    draw=("drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf:text='"+safe+
          "':fontcolor=white:fontsize=54:box=1:boxcolor=black@0.45:boxborderw=20:"
          "x=(w-text_w)/2:y=h*0.78:enable='between(t,0,5)'")
    final=folder/"final.mp4"
    run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-i",clean,"-vf",draw,
         "-an","-c:v","libx264","-preset","veryfast","-crf","20","-r","30","-pix_fmt","yuv420p",final])
    return final

def mix_audio(voice_file):
    """Use an already-recorded Liam voiceover; no text-to-speech or voice cloning."""
    folder=WORK/"audio"
    folder.mkdir(parents=True,exist_ok=True)
    length,streams=info(voice_file)
    if not any(s.get("codec_type")=="audio" for s in streams):
        raise RuntimeError("The supplied Liam file has no audio stream.")
    if length>900.5:
        raise RuntimeError(f"Liam's recording is {length:.1f}s; it is longer than the 15-minute edit.")
    voice=folder/"voice_15min.wav"
    run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-i",voice_file,
         "-af","loudnorm=I=-17:TP=-1.5:LRA=7,apad","-t","900","-ar","48000","-ac","2",
         "-c:a","pcm_s16le",voice])
    bed=folder/"ambience.wav"
    mixfilter=("[0:a]lowpass=f=80,volume=0.18[a];[1:a]lowpass=f=140,volume=0.12[b];"
               "[2:a]lowpass=f=520,volume=0.12[c];[a][b][c]amix=inputs=3:normalize=0,"
               "afade=t=in:st=0:d=4,afade=t=out:st=890:d=10[out]")
    run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
         "-f","lavfi","-i","sine=frequency=42:sample_rate=48000:duration=900",
         "-f","lavfi","-i","sine=frequency=58:sample_rate=48000:duration=900",
         "-f","lavfi","-i","anoisesrc=color=pink:amplitude=0.04:sample_rate=48000:duration=900",
         "-filter_complex",mixfilter,"-map","[out]","-ar","48000","-ac","2","-c:a","pcm_s16le",bed])
    mixed=folder/"mixed.wav"
    run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-i",voice,"-i",bed,
         "-filter_complex","[0:a]volume=1[v];[1:a]volume=0.3[b];[v][b]amix=inputs=2:normalize=0,alimiter=limit=0.94[out]",
         "-map","[out]","-t","900","-ar","48000","-ac","2","-c:a","pcm_s16le",mixed])
    return mixed

def main():
    OUT.mkdir(parents=True,exist_ok=True);WORK.mkdir(parents=True,exist_ok=True)
    narration=json.loads((ROOT/"narration.json").read_text(encoding="utf-8"))
    assets=get_assets()
    montage=assets.get("general_ocean",[])
    for k in ["box_jellyfish","blue_ringed_octopus","tiger_shark","bull_shark","great_white_shark","saltwater_crocodile"]:
        montage.extend(assets[k][:1])
    if not montage: raise RuntimeError("No general ocean footage available for intro/outro.")
    scene_sources={"reef_stonefish":assets["reef_stonefish"],"blue_ringed_octopus":assets["blue_ringed_octopus"],
       "box_jellyfish":assets["box_jellyfish"],"tiger_shark":assets["tiger_shark"],
       "bull_shark":assets["bull_shark"],"great_white_shark":assets["great_white_shark"],
       "saltwater_crocodile":assets["saltwater_crocodile"]}
    cuts=[]
    for section in narration:
        slug=section["id"]
        source=montage if slug in ("intro","outro") else scene_sources[slug]
        print("Cutting:",section["title"],flush=True)
        cuts.append(make_scene(slug,source,DURS[slug],section["title"]))
    playlist=WORK/"video.txt"
    playlist.write_text("".join("file '"+p.as_posix()+"'\n" for p in cuts),encoding="utf-8")
    silent=WORK/"silent.mp4"
    run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-f","concat","-safe","0","-i",playlist,
         "-t","900","-an","-c:v","libx264","-preset","medium","-crf","21","-r","30",
         "-pix_fmt","yuv420p",silent])
    preview=OUT/"15-minute-visual-edit-silent-preview.mp4"
    shutil.copy2(silent,preview)
    shutil.copy2(ROOT/"sources.txt",OUT/"sources.txt")
    attrs=list((ROOT/"downloads"/"pixabay").rglob("ATTRIBUTION.txt"))
    if attrs:
        with (OUT/"sources.txt").open("a",encoding="utf-8") as f:
            f.write("\n\nEXACT PIXABAY CLIP ATTRIBUTION\n")
            for p in attrs:f.write(p.read_text(encoding="utf-8",errors="replace")+"\n")
    voice_file=ROOT/"assets"/"audio"/"liam_voiceover.mp3"
    if not voice_file.exists():
        voice_file=ROOT/"assets"/"audio"/"liam_voiceover.wav"
    if not voice_file.exists():
        note=("VISUAL EDIT READY — LIAM AUDIO NEEDED\n"
              "The 15-minute visual edit has been assembled without sound.\n"
              "To finish the requested version, add an already-recorded, authorised Liam voiceover as "
              "assets/audio/liam_voiceover.mp3 or assets/audio/liam_voiceover.wav, then run this workflow again.\n"
              "No replacement voice was generated.\n")
        (OUT/"NEEDS_LIAM_AUDIO.txt").write_text(note,encoding="utf-8")
        report=("VISUAL EDIT READY (SILENT PREVIEW ONLY)\n"
                "File: "+preview.name+"\nRuntime: 900 seconds (15:00)\n"
                "Resolution: 1920x1080, 30 fps\n"
                "The final narration mix is waiting for the Liam voice recording.\n"
                "Sources and credits are in sources.txt; none are shown on-screen.\n")
        (OUT/"render_report.txt").write_text(report,encoding="utf-8")
        print(report,flush=True)
        return
    audio=mix_audio(voice_file)
    video=OUT/"7-most-dangerous-creatures-in-the-ocean.mp4"
    run(["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y","-i",silent,"-i",audio,
         "-map","0:v:0","-map","1:a:0","-t","900","-c:v","copy","-c:a","aac",
         "-b:a","192k","-movflags","+faststart",video])
    length,streams=info(video)
    v=next((x for x in streams if x.get("codec_type")=="video"),{})
    a=next((x for x in streams if x.get("codec_type")=="audio"),{})
    if abs(length-900)>0.8 or v.get("codec_name")!="h264" or a.get("codec_name")!="aac" or (v.get("width"),v.get("height"))!=(W,H):
        raise RuntimeError("Final video failed duration, resolution or codec validation.")
    size=video.stat().st_size
    report=(f"SUCCESS\nVideo: {video.name}\nRuntime: {length:.2f} seconds\n"
            f"Resolution: {W}x{H}, {FPS} fps\nVideo: H.264\nAudio: AAC; supplied Liam recording with original-source audio muted\n"
            f"File size: {size:,} bytes ({size/1_000_000:.2f} MB)\n"
            "Sources/credits: separate sources.txt; no citations shown on-screen.\n"
            "Some scenes use real still photographs with slow camera movement where motion footage is limited.\n")
    (OUT/"render_report.txt").write_text(report,encoding="utf-8")
    (OUT/"voice_report.txt").write_text(f"Voice source: {voice_file.name}\n",encoding="utf-8")
    print(report,flush=True)

if __name__=="__main__":
    try: main()
    except Exception as exc:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/"build_error.txt").write_text("BUILD NOT COMPLETED\n"+type(exc).__name__+": "+str(exc)+"\n",encoding="utf-8")
        print("BUILD NOT COMPLETED:",type(exc).__name__,str(exc),file=sys.stderr,flush=True)
        sys.exit(1)
