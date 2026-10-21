"""Mux v2 PNG frames + SAPI voiceover WAVs into the final MP4 with Blender's sequencer.

Usage: blender -b --factory-startup -P video/scripts/encode_video_v2.py
Needs video/render/frames_v2/f_*.png and video/render/voice/vo_*.wav + cues.txt (make_voice.ps1).
"""
import glob
import os

import bpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FPS = 30
frames = sorted(glob.glob(os.path.join(ROOT, "render", "frames_v2", "f_*.png")))
scene = bpy.context.scene
scene.render.resolution_x, scene.render.resolution_y = 1080, 1350
scene.render.resolution_percentage = 100
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, len(frames)
scene.view_settings.view_transform = "Standard"
seq = scene.sequence_editor_create()
strips = seq.strips if hasattr(seq, "strips") else seq.sequences
strip = strips.new_image("frames", frames[0], channel=1, frame_start=1)
for f in frames[1:]:
    strip.elements.append(os.path.basename(f))

voice = os.path.join(ROOT, "render", "voice")
with open(os.path.join(voice, "cues.txt")) as cues:
    for line in cues:
        cue, start, _ = line.strip().split(";")
        sound = strips.new_sound(f"vo_{cue}", os.path.join(voice, f"vo_{cue}.wav"), channel=2 + int(cue) % 2,
                                 frame_start=1 + round(float(start) * FPS))
        sound.volume = 1.0

settings = scene.render.image_settings
if hasattr(settings, "media_type"):
    settings.media_type = "VIDEO"
settings.file_format = "FFMPEG"
ff = scene.render.ffmpeg
ff.format = "MPEG4"
ff.codec = "H264"
ff.constant_rate_factor = "HIGH"
ff.ffmpeg_preset = "BEST"
ff.audio_codec = "AAC"
ff.audio_bitrate = 192
ff.audio_channels = "STEREO"
ff.audio_mixrate = 48000
scene.render.filepath = os.path.join(ROOT, "render", "aura_hft_promo_v2.mp4")
bpy.ops.render.render(animation=True)
print("ENCODE_OK", len(frames))
