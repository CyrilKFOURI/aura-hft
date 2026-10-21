"""Render preview stills of key frames from the v2 .blend.

Usage: blender -b video/aura_hft_promo_v2.blend -P video/scripts/render_stills.py -- 300 700 [--pct 50]
Writes video/render/stills_v2/s_<frame>.png.
"""
import os
import sys

import bpy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
args = sys.argv[sys.argv.index("--") + 1:]
pct = 100
if "--pct" in args:
    pct = int(args[args.index("--pct") + 1])
    del args[args.index("--pct"):args.index("--pct") + 2]
scene = bpy.data.scenes["Main"]
scene.render.resolution_percentage = pct
for f in map(int, args):
    scene.frame_set(f)
    scene.render.filepath = os.path.join(ROOT, "render", "stills_v2", f"s_{f:04d}.png")
    bpy.ops.render.render(write_still=True, scene=scene.name)
    print("STILL", f)
