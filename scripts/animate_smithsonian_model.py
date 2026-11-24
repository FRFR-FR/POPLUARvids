#!/usr/bin/env python3
"""Download and animate a Smithsonian CC0 megalodon fossil-tooth scan.
This is an object turntable, NOT a reconstruction of a living megalodon.
"""
import json, math, os, subprocess, urllib.request
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path("output/smithsonian-models")
ROOT.mkdir(parents=True, exist_ok=True)
MODEL = ROOT / "megalodon_fossil_tooth.glb"
VIDEO = ROOT / "megalodon_fossil_tooth_turntable.mp4"
MODEL_URL = "https://3d-api.si.edu/content/document/3d_package:106e215b-a829-40c6-8e4d-dfba37350f36/resources/carcharodon-megalodon-(usnm-v-10333)-150k-4096.glb"
SOURCE_PAGE = "https://3d.si.edu/object/3d/carcharocles-megalodon:106e215b-a829-40c6-8e4d-dfba37350f36"

def download():
    if not MODEL.exists() or MODEL.stat().st_size < 100_000:
        print("Downloading Smithsonian megalodon fossil tooth GLB...", flush=True)
        req = urllib.request.Request(MODEL_URL, headers={"User-Agent":"POPLUARvids/1.0"})
        with urllib.request.urlopen(req, timeout=180) as response, MODEL.open("wb") as out:
            if response.status != 200:
                raise RuntimeError(f"Smithsonian returned HTTP {response.status}")
            while True:
                block = response.read(1024 * 1024)
                if not block: break
                out.write(block)
    if MODEL.stat().st_size < 100_000:
        raise RuntimeError("Downloaded GLB is unexpectedly small")
    print(f"MODEL_DOWNLOADED bytes={MODEL.stat().st_size}", flush=True)

def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        pass

def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()

def render():
    reset_scene()
    bpy.ops.import_scene.gltf(filepath=str(MODEL.resolve()))
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("GLB imported without any mesh objects")

    points = [o.matrix_world @ Vector(corner) for o in meshes for corner in o.bound_box]
    mins = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    maxs = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    center = (mins + maxs) / 2
    dimensions = maxs - mins
    max_dim = max(dimensions)
    if max_dim <= 0:
        raise RuntimeError("Invalid model bounds")

    pivot = bpy.data.objects.new("Fossil tooth turntable pivot", None)
    bpy.context.collection.objects.link(pivot)
    pivot.location = center
    for obj in meshes:
        world = obj.matrix_world.copy()
        obj.parent = pivot
        obj.matrix_world = world
    pivot.scale = (2.8 / max_dim,) * 3

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items.keys() else "BLENDER_EEVEE"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.frame_start = 1
    scene.frame_end = 192
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.filepath = str(VIDEO.resolve())
    scene.render.use_file_extension = True
    scene.world.color = (0.008, 0.018, 0.035)
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1

    # Dark studio floor and soft museum-style lighting.
    bpy.ops.mesh.primitive_plane_add(size=200, location=(center.x, center.y, mins.z - 0.08 * max_dim))
    floor = bpy.context.object
    floor.name = "Dark studio floor"
    mat = bpy.data.materials.new("Deep ocean slate")
    mat.diffuse_color = (0.012, 0.035, 0.055, 1)
    mat.use_nodes = True
    bs = mat.node_tree.nodes.get("Principled BSDF")
    if bs:
        bs.inputs["Base Color"].default_value = (0.012, 0.035, 0.055, 1)
        bs.inputs["Roughness"].default_value = 0.72
    floor.data.materials.append(mat)

    def area(name, loc, power, size, color):
        data = bpy.data.lights.new(name, "AREA")
        data.energy = power
        data.shape = "DISK"
        data.size = size
        data.color = color
        ob = bpy.data.objects.new(name, data)
        bpy.context.collection.objects.link(ob)
        ob.location = Vector(center) + Vector(loc) * max_dim
        aim(ob, center)
    area("Key softbox", (2.8, -3.5, 3.8), 900, 3.0, (0.72, 0.86, 1.0))
    area("Warm rim", (-3.0, 1.5, 2.6), 1100, 2.5, (1.0, 0.62, 0.34))
    area("Top fill", (0.0, 0.4, 4.5), 700, 2.8, (0.55, 0.75, 1.0))

    cam_data = bpy.data.cameras.new("Fossil display camera")
    cam = bpy.data.objects.new("Fossil display camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = Vector(center) + Vector((0.0, -4.7, 1.45)) * max_dim
    cam_data.lens = 52
    aim(cam, center)
    scene.camera = cam

    # Camera-facing title card, explicitly identifying the object as a fossil tooth.
    text_data = bpy.data.curves.new("Fossil title", "FONT")
    text_data.body = "MEGALODON  |  FOSSIL TOOTH"
    text_data.size = 0.22
    text_data.extrude = 0
    title = bpy.data.objects.new("Fossil title", text_data)
    bpy.context.collection.objects.link(title)
    title.parent = cam
    title.location = (-3.05, -1.72, -8.0)
    title.rotation_euler = (0, 0, 0)
    title_mat = bpy.data.materials.new("Title emission")
    title_mat.diffuse_color = (0.8, 0.9, 1.0, 1)
    title_mat.use_nodes = True
    nodes = title_mat.node_tree.nodes
    nodes.clear()
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (0.72, 0.86, 1.0, 1)
    emission.inputs["Strength"].default_value = 1.2
    output = nodes.new("ShaderNodeOutputMaterial")
    title_mat.node_tree.links.new(emission.outputs[0], output.inputs["Surface"])
    title.data.materials.append(title_mat)

    pivot.rotation_euler.z = 0
    pivot.keyframe_insert(data_path="rotation_euler", index=2, frame=1)
    pivot.rotation_euler.z = 2 * math.pi
    pivot.keyframe_insert(data_path="rotation_euler", index=2, frame=193)
    for action in bpy.data.actions:
        for fc in action.fcurves:
            for key in fc.keyframe_points:
                key.interpolation = "LINEAR"

    scene.frame_set(1)
    print("RENDER_START megalodon fossil tooth turntable 1280x720 24fps 8s", flush=True)
    bpy.ops.render.render(animation=True)
    if not VIDEO.exists() or VIDEO.stat().st_size < 100_000:
        raise RuntimeError("Rendered video missing or unexpectedly small")

    probe = subprocess.run(
        ["ffprobe","-v","error","-select_streams","v:0","-show_entries","stream=codec_name,width,height","-of","json",str(VIDEO)],
        capture_output=True, text=True
    )
    info = json.loads(probe.stdout)
    stream = info.get("streams", [{}])[0]
    if probe.returncode or stream.get("codec_name") != "h264" or stream.get("width") != 1280 or stream.get("height") != 720:
        raise RuntimeError(f"Video verification failed: {probe.stdout} {probe.stderr}")
    report = {
        "model": MODEL.name, "model_bytes": MODEL.stat().st_size,
        "video": VIDEO.name, "video_bytes": VIDEO.stat().st_size,
        "video_mb": round(VIDEO.stat().st_size / 1_000_000, 2),
        "codec": stream.get("codec_name"), "resolution": "1280x720",
        "duration_seconds": 8, "animation": "camera-lit turntable rotation of a scanned fossil tooth; not a living-animal reconstruction",
        "source_page": SOURCE_PAGE, "model_url": MODEL_URL,
        "license": "Smithsonian media page identifies this specific fossil-tooth scan as public domain / CC0"
    }
    (ROOT / "model_video_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (ROOT / "ATTRIBUTION.txt").write_text(
        "Carcharocles megalodon fossil tooth, USNM V10333. 3D scan from Smithsonian Institution, National Museum of Natural History, Paleobiology Department.\n"
        f"Source record: {SOURCE_PAGE}\nModel download: {MODEL_URL}\n"
        "Smithsonian record marks metadata CC0 and states the media file is public domain. This is a scan of a tooth, not a complete megalodon reconstruction.\n",
        encoding="utf-8"
    )
    print(f"VIDEO_VERIFIED {VIDEO} {VIDEO.stat().st_size} bytes ({report['video_mb']} MB)", flush=True)

download()
render()
