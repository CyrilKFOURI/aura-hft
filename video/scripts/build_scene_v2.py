"""Build the AURA-HFT promo v2 scene (Blender 5.2, EEVEE): 90 s dive inside the FPGA.

Usage:
    blender -b --factory-startup -P video/scripts/build_scene_v2.py
Saves video/aura_hft_promo_v2.blend. Shot list: video/SHOTLIST_v2.md.
"""
import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FPS = 30
FRAMES = 2700
RES = (1080, 1350)
FONT_LIGHT = "C:/Windows/Fonts/segoeuil.ttf"
FONT_SEMI = "C:/Windows/Fonts/seguisb.ttf"
FONT_MONO = "C:/Windows/Fonts/consola.ttf"

# Public numbers: docs/CLAIMS.md (C1) on feat/p4-obi-notional-top. Cycle-accurate simulation only.
CYCLES = 27
CLOCK_MHZ = 156.25
REAL_MESSAGES = "215,674"

CYAN = (0.05, 0.75, 1.0)
AMBER = (1.0, 0.45, 0.05)
GREEN = (0.1, 1.0, 0.35)
GOLD = (1.0, 0.62, 0.22)
VIOLET = (0.55, 0.3, 1.0)
WHITE = (0.92, 0.95, 1.0)

Z_TOP = 0.32  # die surface
PZ = 0.42  # packet altitude inside the die

random.seed(7)


# --------------------------------------------------------------------------- helpers
def link(obj, scene):
    scene.collection.objects.link(obj)
    return obj


def set_interp(kind):
    bpy.context.preferences.edit.keyframe_new_interpolation_type = kind


def box(name, size, loc, mat, scene, bevel=0.12):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    obj = link(bpy.data.objects.new(name, me), scene)
    obj.location = loc
    if bevel:
        mod = obj.modifiers.new("bevel", "BEVEL")
        mod.width = min(size) * bevel
        mod.segments = 2
    return obj


def multi_box_mesh(name, boxes, mat, scene):
    """One object made of many boxes [(size, loc)] — cheap carpets of tiles."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    for size, loc in boxes:
        geom = bmesh.ops.create_cube(bm, size=1.0)["verts"]
        for v in geom:
            v.co = Vector((v.co.x * size[0] + loc[0], v.co.y * size[1] + loc[1], v.co.z * size[2] + loc[2]))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    return link(bpy.data.objects.new(name, me), scene)


def principled(name, base, metallic=0.0, rough=0.4, emit=None, strength=0.0):
    mat = bpy.data.materials.new(name)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*base, 1)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = rough
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1)
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def emission(name, color, strength):
    mat = bpy.data.materials.new(name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs[0], out.inputs[0])
    return mat


def key_socket(sock, frame, value):
    sock.default_value = value
    sock.keyframe_insert("default_value", frame=frame)


def emit_strength(mat):
    nodes = mat.node_tree.nodes
    if "Principled BSDF" in nodes:
        return nodes["Principled BSDF"].inputs["Emission Strength"]
    return next(n for n in nodes if n.bl_idname == "ShaderNodeEmission").inputs["Strength"]


def emit_color(mat):
    return next(n for n in mat.node_tree.nodes if n.bl_idname == "ShaderNodeEmission").inputs["Color"]


def glow(name, color, idle, keys):
    """Emission material with idle strength and (frame, strength) keys."""
    mat = emission(name, color, idle)
    sock = emit_strength(mat)
    key_socket(sock, 1, idle)
    for f, v in keys:
        key_socket(sock, f, v)
    return mat


def flash_keys(frame, idle, peak, hold):
    """Idle until `frame`, flare to `peak`, settle at `hold`."""
    return ((frame - 6, idle), (frame, peak), (frame + 30, hold))


def poly_curve(name, points, depth, mat, scene):
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = depth
    cu.bevel_resolution = 2
    cu.use_fill_caps = True
    cu.bevel_factor_mapping_end = "SPLINE"
    sp = cu.splines.new("POLY")
    sp.points.add(len(points) - 1)
    for p, co in zip(sp.points, points):
        p.co = (*co, 1)
    cu.materials.append(mat)
    return link(bpy.data.objects.new(name, cu), scene)


def key_visible(obj, show_at, hide_at=None):
    obj.hide_render = True
    obj.keyframe_insert("hide_render", frame=1)
    obj.hide_render = False
    obj.keyframe_insert("hide_render", frame=show_at)
    if hide_at:
        obj.hide_render = True
        obj.keyframe_insert("hide_render", frame=hide_at)


def action_fcurves(action):
    if hasattr(action, "fcurves") and len(action.fcurves):
        return list(action.fcurves)
    curves = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in strip.channelbags:
                curves.extend(bag.fcurves)
    return curves


# --------------------------------------------------------------------------- scene
def setup_scene():
    scene = bpy.context.scene
    scene.name = "Main"
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = RES
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.frame_start, scene.frame_end = 1, FRAMES
    scene.eevee.taa_render_samples = 24
    scene.eevee.use_raytracing = True
    scene.eevee.use_shadows = True
    scene.eevee.bokeh_max_size = 60
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5
    scene.view_settings.view_transform = "AgX"
    try:
        scene.view_settings.look = "AgX - Punchy"
    except TypeError:
        pass
    world = bpy.data.worlds.new("World")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs[0].default_value = (0.0015, 0.002, 0.004, 1)
    scene.world = world
    return scene


# --------------------------------------------------------------------------- board
def build_board(scene):
    board_mat = principled("PCB", (0.012, 0.016, 0.02), metallic=0.5, rough=0.32)
    nt = board_mat.node_tree
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 140
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.08
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], nt.nodes["Principled BSDF"].inputs["Normal"])
    box("Board", (16, 12, 0.16), (0, 0, -0.08), board_mat, scene)

    ground = principled("Ground", (0.004, 0.005, 0.007), metallic=0.6, rough=0.4)
    box("Ground", (120, 120, 0.01), (0, 0, -0.6), ground, scene, bevel=0)

    metal = principled("Metal", (0.55, 0.57, 0.6), metallic=1.0, rough=0.22)
    dark_metal = principled("DarkMetal", (0.03, 0.032, 0.036), metallic=0.95, rough=0.18)

    for name, y, hit in (("SFP_IN", 2.0, 520), ("SFP_OUT", -2.0, 2285)):
        box(name, (1.6, 0.9, 0.5), (-7.6, y, 0.25), metal, scene)
        mouth = glow(name + "_glow", CYAN, 0.0, ((hit - 30, 0.3), (hit, 12.0), (hit + 45, 1.0)))
        box(name + "_mouth", (0.05, 0.6, 0.28), (-8.41, y, 0.25), mouth, scene)

    box("Substrate", (4.6, 4.6, 0.12), (0, 0, 0.06), principled("Substrate", (0.02, 0.05, 0.035), rough=0.5), scene)
    box("Package", (4.0, 4.0, 0.18), (0, 0, 0.21), dark_metal, scene, bevel=0.05)

    glass = principled("Glass", (0.8, 0.9, 1.0), rough=0.04)
    bsdf = glass.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    bsdf.inputs["IOR"].default_value = 1.45
    glass.surface_render_method = "BLENDED"
    alpha = bsdf.inputs["Alpha"]
    key_socket(alpha, 1, 0.55)
    key_socket(alpha, 585, 0.55)
    key_socket(alpha, 612, 0.0)
    lid = box("GlassLid", (4.0, 4.0, 0.04), (0, 0, 0.75), glass, scene)
    key_visible(lid, 1, 615)

    silk = emission("Silk", (0.75, 0.8, 0.85), 0.25)
    for text, loc, size in (("AMD KRIA  KR260", (3.2, -5.3, 0.005), 0.42), ("AURA-HFT", (3.6, 5.0, 0.005), 0.3),
                            ("10GbE IN", (-7.6, 3.0, 0.005), 0.22), ("10GbE OUT", (-7.6, -3.0, 0.005), 0.22)):
        cu = bpy.data.curves.new("silk", "FONT")
        cu.body = text
        cu.size = size
        cu.align_x = "CENTER"
        cu.font = bpy.data.fonts.load(FONT_SEMI, check_existing=True)
        cu.materials.append(silk)
        link(bpy.data.objects.new("Silk_" + text, cu), scene).location = loc

    build_traces(scene)
    build_components(scene)


def inside_keepout(x, y):
    in_chip = abs(x) < 2.5 and abs(y) < 2.5
    in_sfp = x < -6.5 and (abs(y - 2) < 0.8 or abs(y + 2) < 0.8)
    in_lane = x < -1.2 and abs(abs(y) - 2) < 0.75
    return in_chip or in_sfp or in_lane


def build_traces(scene):
    gold = principled("Gold", GOLD, metallic=1.0, rough=0.25, emit=(1.0, 0.5, 0.12), strength=0.0)
    sock = emit_strength(gold)
    for f, v in ((1, 0.0), (190, 0.0), (330, 1.2), (2400, 1.2), (2480, 0.45)):
        key_socket(sock, f, v)
    via_mesh = None
    for i in range(170):
        x, y = random.uniform(-7.6, 7.6), random.uniform(-5.6, 5.6)
        if inside_keepout(x, y):
            continue
        pts = [(x, y, 0.012)]
        horizontal = random.random() < 0.5
        for _ in range(random.randint(2, 4)):
            step = random.choice((-1, 1)) * random.uniform(0.6, 3.0)
            if horizontal:
                x = max(-7.7, min(7.7, x + step))
            else:
                y = max(-5.7, min(5.7, y + step))
            horizontal = not horizontal
            pts.append((x, y, 0.012))
        obj = poly_curve(f"Trace_{i:03d}", pts, random.choice((0.008, 0.012, 0.018)), gold, scene)
        start = random.randint(190, 320)
        obj.data.bevel_factor_end = 0.0
        obj.data.keyframe_insert("bevel_factor_end", frame=start)
        obj.data.bevel_factor_end = 1.0
        obj.data.keyframe_insert("bevel_factor_end", frame=start + random.randint(25, 60))
        for end in (pts[0], pts[-1]):
            if via_mesh is None:
                via_mesh = box("Via", (0.08, 0.08, 0.03), end, gold, scene, bevel=0.45).data
            else:
                link(bpy.data.objects.new("Via", via_mesh), scene).location = end
    # the two data lanes SFP <-> FPGA the packet rides on
    for y in (2.0, -2.0):
        poly_curve(f"Lane_{y}", [(-7.0, y, 0.012), (-2.6, y, 0.012), (-2.3, y * 0.55, 0.012)], 0.02, gold, scene)


def build_components(scene):
    body = principled("SMDBody", (0.015, 0.015, 0.017), rough=0.45)
    cap = principled("Cap", (0.25, 0.18, 0.1), rough=0.5)
    meshes = {}
    for _ in range(150):
        x, y = random.uniform(-7.5, 7.5), random.uniform(-5.5, 5.5)
        if inside_keepout(x, y):
            continue
        kind = random.choice(("res", "res", "cap", "ic"))
        size = {"res": (0.22, 0.11, 0.07), "cap": (0.3, 0.16, 0.14), "ic": (0.8, 0.8, 0.12)}[kind]
        if kind not in meshes:
            obj = box("Comp_" + kind, size, (x, y, size[2] / 2), {"res": body, "cap": cap, "ic": body}[kind], scene)
            meshes[kind] = obj.data
        else:
            obj = link(bpy.data.objects.new("Comp", meshes[kind]), scene)
            obj.location = (x, y, size[2] / 2)
        obj.rotation_euler.z = random.choice((0, math.pi / 2))
    fin = principled("Fin", (0.08, 0.085, 0.09), metallic=1.0, rough=0.3)
    for i in range(14):
        box(f"Fin_{i}", (0.06, 2.4, 0.5), (3.4 + i * 0.22, 0, 0.25), fin, scene)


# --------------------------------------------------------------------------- die interior
def build_die(scene):
    """Silicon floor: CLB tile carpet with BRAM and DSP columns, routing glow comes up on entry."""
    die = principled("Die", (0.012, 0.014, 0.022), metallic=0.8, rough=0.18, emit=CYAN, strength=0.0)
    dnt = die.node_tree
    brick = dnt.nodes.new("ShaderNodeTexBrick")
    brick.inputs["Scale"].default_value = 30
    brick.inputs["Mortar Size"].default_value = 0.02
    brick.inputs["Color1"].default_value = (0, 0, 0, 1)
    brick.inputs["Color2"].default_value = (0, 0, 0, 1)
    brick.inputs["Mortar"].default_value = (*CYAN, 1)
    dnt.links.new(brick.outputs["Color"], dnt.nodes["Principled BSDF"].inputs["Emission Color"])
    key_socket(emit_strength(die), 1, 0.0)
    key_socket(emit_strength(die), 590, 0.0)
    key_socket(emit_strength(die), 640, 0.12)
    box("Die", (3.7, 3.7, 0.02), (0, 0, 0.31), die, scene, bevel=0.2)

    clb = principled("CLB", (0.03, 0.035, 0.05), metallic=0.9, rough=0.25, emit=CYAN, strength=0.0)
    key_socket(emit_strength(clb), 1, 0.0)
    key_socket(emit_strength(clb), 600, 0.0)
    key_socket(emit_strength(clb), 660, 0.04)
    bram = principled("BRAMcol", (0.05, 0.04, 0.02), metallic=0.9, rough=0.3, emit=GOLD, strength=0.0)
    key_socket(emit_strength(bram), 1, 0.0)
    key_socket(emit_strength(bram), 620, 0.0)
    key_socket(emit_strength(bram), 680, 0.25)
    dsp = principled("DSPcol", (0.03, 0.02, 0.06), metallic=0.9, rough=0.3, emit=VIOLET, strength=0.0)
    key_socket(emit_strength(dsp), 1, 0.0)
    key_socket(emit_strength(dsp), 620, 0.0)
    key_socket(emit_strength(dsp), 680, 0.3)
    pitch = 0.07
    clbs, brams, dsps = [], [], []
    n = int(3.5 / pitch)
    for i in range(n):
        x = -1.75 + (i + 0.5) * pitch
        col = i % 9
        for j in range(n):
            y = -1.75 + (j + 0.5) * pitch
            if col == 3:
                if j % 3 == 0:
                    brams.append(((0.055, pitch * 2.8, 0.012), (x, y + pitch, Z_TOP + 0.006)))
            elif col == 7:
                if j % 2 == 0:
                    dsps.append(((0.055, pitch * 1.8, 0.012), (x, y + pitch / 2, Z_TOP + 0.006)))
            else:
                clbs.append(((pitch * 0.82, pitch * 0.82, 0.006), (x, y, Z_TOP + 0.003)))
    multi_box_mesh("CLB_Carpet", clbs, clb, scene)
    multi_box_mesh("BRAM_Columns", brams, bram, scene)
    multi_box_mesh("DSP_Columns", dsps, dsp, scene)
    # global routing: faint horizontal/vertical channels
    route = glow("Routing", CYAN, 0.0, ((600, 0.0), (680, 0.6)))
    for k in range(-5, 6):
        poly_curve(f"RouteH{k}", [(-1.8, k * 0.32, Z_TOP + 0.014), (1.8, k * 0.32, Z_TOP + 0.014)], 0.0015, route, scene)
        poly_curve(f"RouteV{k}", [(k * 0.32, -1.8, Z_TOP + 0.014), (k * 0.32, 1.8, Z_TOP + 0.014)], 0.0015, route, scene)


def housing_mat():
    return principled("Housing", (0.025, 0.028, 0.034), metallic=0.95, rough=0.22)


def plate(name, size, cx, cy, scene, mat):
    return box(name, (size[0], size[1], 0.02), (cx, cy, Z_TOP + 0.01), mat, scene, bevel=0.3)


def build_ingress(scene, h):
    """SerDes lanes -> MAC -> FCS gate (green when the CRC-32 passes)."""
    cx, cy = -1.3, 1.1
    plate("ING_Plate", (0.8, 0.6), cx, cy, scene, h)
    coil = principled("Coil", GOLD, metallic=1.0, rough=0.2)
    for k, dy in enumerate((-0.18, -0.06, 0.06, 0.18)):
        lane = glow(f"Lane{k}", CYAN, 0.6, flash_keys(650 + k * 6, 0.6, 14.0, 2.0))
        box(f"ING_Lane{k}", (0.42, 0.014, 0.01), (cx - 0.2, cy + dy, Z_TOP + 0.03), lane, scene, bevel=0)
        for m in range(3):
            bpy.ops.mesh.primitive_torus_add(major_radius=0.022, minor_radius=0.005, major_segments=24,
                                             location=(cx - 0.34 + m * 0.07, cy + dy, Z_TOP + 0.03),
                                             rotation=(0, math.pi / 2, 0))
            bpy.context.active_object.data.materials.append(coil)
        box(f"ING_PMA{k}", (0.05, 0.06, 0.04), (cx - 0.07, cy + dy, Z_TOP + 0.04), h, scene)
    mac = box("ING_MAC", (0.16, 0.5, 0.11), (cx + 0.08, cy, Z_TOP + 0.075), h, scene)
    stripe = glow("MACstripe", CYAN, 0.5, flash_keys(700, 0.5, 10.0, 1.5))
    box("ING_MACstripe", (0.012, 0.46, 0.006), (cx + 0.08, cy, Z_TOP + 0.133), stripe, scene, bevel=0)
    gate = glow("FCSgate", AMBER, 3.0, ((750, 4.0), (762, 25.0), (800, 6.0)))
    col = emit_color(gate)
    key_socket(col, 755, (*AMBER, 1))
    key_socket(col, 762, (*GREEN, 1))
    gx = cx + 0.3
    for dy in (-0.12, 0.12):
        box("FCS_post", (0.03, 0.03, 0.17), (gx, cy + dy, Z_TOP + 0.085), gate, scene)
    box("FCS_lintel", (0.03, 0.27, 0.03), (gx, cy, Z_TOP + 0.18), gate, scene)
    return mac


def build_moldudp(scene, h):
    """Sequence ring (16 slots advancing) around a PTP time-stamp dial."""
    cx, cy = -0.4, 1.1
    bpy.ops.mesh.primitive_cylinder_add(radius=0.36, depth=0.02, vertices=64, location=(cx, cy, Z_TOP + 0.01))
    bpy.context.active_object.data.materials.append(h)
    for i in range(16):
        a = i / 16 * 2 * math.pi + math.pi
        lit = 860 + i * 6 if i < 12 else 10_000
        mat = glow(f"Seq{i}", CYAN, 0.2, ((lit - 2, 0.2), (lit, 9.0), (lit + 18, 1.2)))
        slot = box(f"SEQ_{i}", (0.08, 0.035, 0.05), (cx + 0.27 * math.cos(a), cy + 0.27 * math.sin(a), Z_TOP + 0.045),
                   mat, scene)
        slot.rotation_euler.z = a + math.pi / 2
    bpy.ops.mesh.primitive_torus_add(major_radius=0.34, minor_radius=0.004, location=(cx, cy, Z_TOP + 0.03))
    bpy.context.active_object.data.materials.append(glow("SeqRing", VIOLET, 3.0, ()))
    bpy.ops.mesh.primitive_cylinder_add(radius=0.11, depth=0.07, vertices=48, location=(cx, cy, Z_TOP + 0.045))
    bpy.context.active_object.data.materials.append(h)
    bpy.ops.mesh.primitive_torus_add(major_radius=0.1, minor_radius=0.004, location=(cx, cy, Z_TOP + 0.082))
    bpy.context.active_object.data.materials.append(glow("PTPdial", GOLD, 4.0, flash_keys(930, 4.0, 20.0, 4.0)))
    hand = box("PTP_hand", (0.09, 0.008, 0.006), (cx, cy, Z_TOP + 0.085), glow("PTPhand", WHITE, 8.0, ()), scene, 0)
    hand.data.transform(Matrix.Translation((0.045, 0, 0)))
    set_interp("LINEAR")
    hand.rotation_euler.z = 0
    hand.keyframe_insert("rotation_euler", frame=1)
    hand.rotation_euler.z = -FRAMES / FPS * 2 * math.pi
    hand.keyframe_insert("rotation_euler", frame=FRAMES)
    set_interp("BEZIER")


PARSE_FIELDS = (("TYPE", 1), ("REF", 8), ("SIDE", 1), ("SHARES", 4), ("STOCK", 8), ("PRICE", 4))


def build_parser(scene, h):
    """Splitter spine fans the message into six byte-proportional lanes ending in field registers."""
    cx, cy = 0.5, 1.1
    plate("PAR_Plate", (0.75, 0.6), cx, cy, scene, h)
    box("PAR_Spine", (0.05, 0.52, 0.1), (cx - 0.27, cy, Z_TOP + 0.07), h, scene)
    box("PAR_SpineGlow", (0.008, 0.5, 0.01), (cx - 0.243, cy, Z_TOP + 0.08),
        glow("Spine", CYAN, 1.0, flash_keys(1050, 1.0, 14.0, 2.0)), scene, 0)
    for i, (name, nbytes) in enumerate(PARSE_FIELDS):
        y = cy - 0.21 + i * 0.084
        w = 0.008 + nbytes * 0.004
        start = 1065 + i * 9
        lane = glow(f"PLane{i}", CYAN, 0.4, ((start, 0.4), (start + 10, 6.0), (start + 60, 1.0)))
        box(f"PAR_Lane{i}", (0.42, w, 0.006), (cx - 0.02, y, Z_TOP + 0.025), lane, scene, bevel=0)
        reg = glow(f"PReg{i}", CYAN, 0.3, flash_keys(start + 70, 0.3, 10.0, 2.5))
        box(f"PAR_Reg{i}", (0.07, w + 0.03, 0.07), (cx + 0.26, y, Z_TOP + 0.045), housing_mat(), scene)
        box(f"PAR_RegCap{i}", (0.06, w + 0.02, 0.006), (cx + 0.26, y, Z_TOP + 0.082), reg, scene, bevel=0)
        slug = box(f"PAR_Slug{i}", (0.05, w, 0.02), (cx - 0.22, y, Z_TOP + 0.04),
                   emission(f"Slug{i}", WHITE if name == "PRICE" else CYAN, 16.0), scene, 0)
        slug.keyframe_insert("location", frame=start)
        slug.location.x = cx + 0.2
        slug.keyframe_insert("location", frame=start + 70)
        key_visible(slug, start, start + 72)


def build_order_store(scene, h):
    """Two BRAM banks (8 sets x 4 ways each) + 4-entry stash; two-choice probe, hit turns green."""
    cx, cy = 1.35, 1.1
    plate("ORD_Plate", (0.95, 0.75), cx, cy, scene, h)
    idle = principled("BRAMtile", (0.04, 0.035, 0.03), metallic=0.85, rough=0.3, emit=GOLD, strength=0.35)
    probes = {("A", 2): 1290, ("B", 5): 1296}
    for bank, dy in (("A", -0.2), ("B", 0.2)):
        for s in range(8):
            x = cx - 0.33 + s * 0.095
            for w in range(4):
                z = Z_TOP + 0.04 + w * 0.05
                hit = probes.get((bank, s))
                if hit:
                    mat = glow(f"Probe{bank}{s}{w}", CYAN, 0.3, ((hit - 2, 0.3), (hit + 4, 9.0), (hit + 60, 2.5)))
                    if bank == "A" and w == 1:
                        col = emit_color(mat)
                        key_socket(col, hit + 50, (*CYAN, 1))
                        key_socket(col, hit + 62, (*GREEN, 1))
                        key_socket(emit_strength(mat), hit + 62, 16.0)
                        key_socket(emit_strength(mat), hit + 120, 5.0)
                else:
                    mat = idle
                box(f"BRAM_{bank}{s}{w}", (0.08, 0.14, 0.038), (x, cy + dy, z), mat, scene)
        rail = principled("Rail", (0.4, 0.42, 0.45), metallic=1.0, rough=0.2)
        box(f"BRAM_rail{bank}", (0.8, 0.012, 0.05), (cx, cy + dy + (0.08 if dy > 0 else -0.08), Z_TOP + 0.035), rail,
            scene)
    box("HASH_unit", (0.08, 0.16, 0.1), (cx - 0.44, cy, Z_TOP + 0.06), h, scene)
    beam = emission("HashBeam", CYAN, 12.0)
    for s, dy, f in ((2, -0.2, 1284), (5, 0.2, 1290)):
        x = cx - 0.33 + s * 0.095
        tgt = Vector((x, cy + dy, Z_TOP + 0.24))
        src = Vector((cx - 0.44, cy, Z_TOP + 0.12))
        b = poly_curve(f"HashBeam{s}", [tuple(src), tuple((src + tgt) / 2 + Vector((0, 0, 0.12))), tuple(tgt)],
                       0.003, beam, scene)
        b.data.bevel_factor_end = 0.0
        b.data.keyframe_insert("bevel_factor_end", frame=f - 12)
        b.data.bevel_factor_end = 1.0
        b.data.keyframe_insert("bevel_factor_end", frame=f)
        key_visible(b, f - 12, 1400)
    for k in range(4):
        st = glow(f"Stash{k}", AMBER, 0.6, ((1310 + k * 8, 0.6), (1316 + k * 8, 7.0), (1340 + k * 8, 1.0)))
        box(f"STASH_{k}", (0.06, 0.06, 0.035), (cx + 0.45, cy - 0.09 + k * 0.06, Z_TOP + 0.04), st, scene)


def build_depth_book(scene, h):
    """Price-indexed bid/ask slot rows, 3-level occupancy bitmap tree, top-5 extractor."""
    x0, x1, cy = 0.65, 1.72, -0.7
    plate("DEP_Plate", (1.15, 0.75), (x0 + x1) / 2, cy, scene, h)
    n = 56
    pitch = (x1 - x0) / n
    best_bid, best_ask = 24, 29
    for side, dy, color, sel in (("bid", -0.13, CYAN, lambda i: i <= best_bid),
                                 ("ask", 0.0, AMBER, lambda i: i >= best_ask)):
        boxes = []
        for i in range(n):
            x = x0 + (i + 0.5) * pitch
            occupied = sel(i) and random.random() < 0.7
            height = random.uniform(0.02, 0.12) if occupied else 0.004
            boxes.append(((pitch * 0.7, 0.1, height), (x, cy + dy, Z_TOP + 0.02 + height / 2)))
        mat = glow(f"Slots_{side}", color, 0.8, ((1500, 0.8), (1560, 3.5), (1700, 2.0)))
        multi_box_mesh(f"DEP_{side}", boxes, mat, scene)
    tree_y = cy + 0.22
    levels = ((16, Z_TOP + 0.1, 1640), (4, Z_TOP + 0.22, 1625), (1, Z_TOP + 0.34, 1610))
    edge = emission("TreeEdge", CYAN, 1.5)
    prev = None
    for count, z, f in levels:
        xs = [x0 + (x1 - x0) * (k + 0.5) / count for k in range(count)]
        for k, x in enumerate(xs):
            mat = glow(f"Node{count}_{k}", CYAN, 0.3, flash_keys(f + (k % 4) * 2, 0.3, 12.0, 2.0))
            size = 0.035 + (16 // count) * 0.008
            box(f"BMP_{count}_{k}", (size, size, size), (x, tree_y, z), mat, scene)
        if prev:
            pc, pxs, pz = prev
            for k, x in enumerate(pxs):
                parent = xs[k * count // pc]
                poly_curve("TreeEdge", [(x, tree_y, pz), (parent, tree_y, z)], 0.0018, edge, scene)
        prev = (count, xs, z)
    for k in range(5):
        top = glow(f"Top5_{k}", WHITE if k == 0 else CYAN, 2.0, flash_keys(1665 + k * 8, 2.0, 14.0, 4.0))
        bar = box(f"TOP5_{k}", (0.16, 0.04, 0.018), (x0 - 0.1, cy - 0.06, Z_TOP + 0.03), top, scene)
        bar.keyframe_insert("location", frame=1660 + k * 8)
        bar.location.z = Z_TOP + 0.08 + k * 0.035
        bar.keyframe_insert("location", frame=1680 + k * 8)


def build_signal(scene, h):
    """Four DSP48 tiles (pre-adder, multiplier, ALU) cascading into a comparator wedge."""
    cx, cy = 0.2, -0.7
    plate("SIG_Plate", (0.75, 0.6), cx, cy, scene, h)
    for i in range(4):
        x = cx + 0.24 - i * 0.16
        f = 1790 + i * 22
        tile = principled(f"DSP48_{i}", (0.03, 0.02, 0.06), metallic=0.9, rough=0.25)
        box(f"DSP48_{i}", (0.12, 0.16, 0.3), (x, cy + 0.15, Z_TOP + 0.15), tile, scene, bevel=0.06)
        for k, (zo, hgt, color) in enumerate(((0.06, 0.04, CYAN), (0.15, 0.08, VIOLET), (0.25, 0.04, CYAN))):
            m = glow(f"DSPsub{i}{k}", color, 0.4, flash_keys(f + k * 6, 0.4, 16.0, 1.5))
            box(f"DSPsub{i}{k}", (0.125, 0.01, hgt), (x, cy + 0.068, Z_TOP + zo), m, scene, bevel=0)
        bpy.ops.mesh.primitive_torus_add(major_radius=0.03, minor_radius=0.004, location=(x, cy + 0.06, Z_TOP + 0.15),
                                         rotation=(math.pi / 2, 0, 0))
        bpy.context.active_object.data.materials.append(glow(f"Mul{i}", WHITE, 1.0, flash_keys(f + 6, 1.0, 20.0, 2.0)))
        if i:
            casc = glow(f"Casc{i}", CYAN, 0.3, flash_keys(f - 4, 0.3, 12.0, 1.0))
            box(f"Cascade{i}", (0.06, 0.012, 0.012), (x + 0.08, cy + 0.15, Z_TOP + 0.31), casc, scene, bevel=0)
    me = bpy.data.meshes.new("Comparator")
    me.from_pydata([(0, -0.09, 0), (0, 0.09, 0), (0, -0.09, 0.14), (0, 0.09, 0.14), (-0.14, 0, 0.07)], [],
                   [(0, 1, 3, 2), (0, 2, 4), (1, 4, 3), (0, 4, 1), (2, 3, 4)])
    me.materials.append(glow("Comparator", VIOLET, 1.0, flash_keys(1880, 1.0, 18.0, 3.0)))
    link(bpy.data.objects.new("Comparator", me), scene).location = (cx - 0.3, cy + 0.15, Z_TOP + 0.02)


def build_risk(scene, h):
    """Stage 1: notional multiplier block; stage 2: four comparator arches, amber -> green."""
    cx, cy = -0.7, -0.7
    plate("RSK_Plate", (0.7, 0.5), cx, cy, scene, h)
    mul = glow("RiskMul", AMBER, 1.0, flash_keys(2000, 1.0, 16.0, 3.0))
    box("RSK_Mul", (0.1, 0.06, 0.16), (cx + 0.24, cy + 0.13, Z_TOP + 0.08), h, scene)
    box("RSK_Mul2", (0.1, 0.06, 0.16), (cx + 0.24, cy - 0.13, Z_TOP + 0.08), h, scene)
    for dy in (0.098, -0.098):
        box("RSK_MulFace", (0.09, 0.004, 0.14), (cx + 0.24, cy + dy, Z_TOP + 0.08), mul, scene, bevel=0)
    for i in range(4):
        x = cx + 0.1 - i * 0.1
        f = 2045 + i * 14
        gate = glow(f"Limit{i}", AMBER, 3.0, ((f - 4, 3.0), (f, 22.0), (f + 30, 6.0)))
        col = emit_color(gate)
        key_socket(col, f - 1, (*AMBER, 1))
        key_socket(col, f + 2, (*GREEN, 1))
        for dy in (-0.11, 0.11):
            box("Limit_post", (0.022, 0.022, 0.16), (x, cy + dy, Z_TOP + 0.08), gate, scene)
        box("Limit_lintel", (0.022, 0.24, 0.022), (x, cy, Z_TOP + 0.17), gate, scene)


def build_egress(scene, h):
    """OUCH frame builder: header slabs stack, then a serializer lane streams to the die edge."""
    cx, cy = -1.4, -0.7
    plate("OUT_Plate", (0.6, 0.5), cx, cy, scene, h)
    names = ("ETH", "IP", "UDP", "SOUP", "OUCH")
    for k, _ in enumerate(names):
        f = 2150 + k * 7
        slab = box(f"OUT_Slab{k}", (0.15, 0.2, 0.016), (cx + 0.05, cy + 0.12, Z_TOP + 0.4),
                   glow(f"Slab{k}", GREEN if k == 4 else CYAN, 6.0, ((f + 12, 6.0), (f + 40, 1.5))), scene)
        slab.keyframe_insert("location", frame=f)
        slab.location.z = Z_TOP + 0.03 + k * 0.02
        slab.keyframe_insert("location", frame=f + 12)
        key_visible(slab, f)
    for k, dy in enumerate((-0.15, -0.05, 0.05, 0.15)):
        lane = glow(f"OutLane{k}", CYAN, 0.5, flash_keys(2205 + k * 3, 0.5, 16.0, 1.5))
        box(f"OUT_Lane{k}", (0.35, 0.014, 0.01), (cx - 0.25, cy + dy, Z_TOP + 0.03), lane, scene, bevel=0)


def build_pipeline(scene):
    h = housing_mat()
    build_ingress(scene, h)
    build_moldudp(scene, h)
    build_parser(scene, h)
    build_order_store(scene, h)
    build_depth_book(scene, h)
    build_signal(scene, h)
    build_risk(scene, h)
    build_egress(scene, h)
    # die-local soft light so close-ups are readable
    for name, loc, energy in (("DieKey", (0.3, -2.4, 2.4), 90), ("DieTop", (0, 0, 2.6), 60)):
        light = bpy.data.lights.new(name, "AREA")
        light.size = 3.5
        light.color = (0.8, 0.88, 1.0)
        obj = link(bpy.data.objects.new(name, light), scene)
        obj.location = loc
        obj.constraints.new("TRACK_TO").target = link(bpy.data.objects.new(name + "Tgt", None), scene)
        obj.visible_camera = False
        for f, e in ((1, 0), (590, 0), (650, energy), (2300, energy), (2380, 0)):
            light.energy = e
            light.keyframe_insert("energy", frame=f)


# --------------------------------------------------------------------------- packet
WAYPOINTS = [
    ((-13.0, 2.0, 0.25), 470), ((-8.4, 2.0, 0.25), 520), ((-7.0, 2.0, 0.04), 532), ((-2.6, 2.0, 0.04), 572),
    ((-2.3, 1.1, 0.04), 586), ((-1.95, 1.1, PZ), 610),
    ((-1.7, 1.1, PZ), 650), ((-1.05, 1.1, PZ), 762), ((-0.85, 1.1, PZ), 800),
    ((-0.4, 1.1, PZ + 0.04), 860), ((-0.4, 1.1, PZ + 0.04), 960), ((-0.05, 1.1, PZ), 1010),
    ((0.2, 1.1, PZ), 1045), ((0.2, 1.1, PZ), 1060), ((0.86, 1.1, PZ), 1150), ((0.86, 1.1, PZ), 1190),
    ((1.0, 1.1, PZ), 1230), ((1.35, 1.1, PZ), 1270), ((1.35, 1.1, PZ), 1440),
    ((1.35, 0.4, PZ), 1470), ((1.78, -0.25, PZ), 1495),
    ((1.75, -0.68, PZ + 0.06), 1510), ((0.62, -0.68, PZ + 0.06), 1700),
    ((0.5, -0.7, PZ), 1740), ((0.2, -0.7, PZ), 1770), ((0.2, -0.7, PZ), 1890), ((-0.15, -0.7, PZ), 1960),
    ((-0.46, -0.7, PZ), 2000), ((-0.46, -0.7, PZ), 2035), ((-1.05, -0.7, PZ), 2110), ((-1.2, -0.7, PZ), 2140),
    ((-1.35, -0.7, PZ), 2160), ((-1.35, -0.7, PZ), 2200), ((-1.85, -0.7, PZ), 2222),
    ((-2.3, -1.1, 0.04), 2236), ((-2.6, -2.0, 0.04), 2248), ((-7.0, -2.0, 0.04), 2272), ((-8.4, -2.0, 0.25), 2285),
    ((-13.0, -2.0, 0.25), 2310),
]


def build_packet(scene):
    pts = [p for p, _ in WAYPOINTS]
    lengths = [0.0]
    for a, b in zip(pts, pts[1:]):
        lengths.append(lengths[-1] + (Vector(b) - Vector(a)).length)
    total = lengths[-1]

    trail = poly_curve("DataTrail", pts, 0.0025, glow("Trail", CYAN, 3.0, ()), scene)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.022, location=pts[0])
    packet = bpy.context.active_object
    packet.name = "Packet"
    packet.data.materials.append(emission("PacketCore", (0.3, 0.85, 1.0), 25.0))
    light = bpy.data.lights.new("PacketLight", "POINT")
    light.color = CYAN
    light.shadow_soft_size = 0.02
    plight = link(bpy.data.objects.new("PacketLight", light), scene)
    plight.parent = packet
    for f, e in ((1, 18), (600, 18), (630, 1.2), (2215, 1.2), (2240, 18)):
        light.energy = e
        light.keyframe_insert("energy", frame=f)

    set_interp("LINEAR")
    for (p, f), d in zip(WAYPOINTS, lengths):
        packet.location = p
        packet.keyframe_insert("location", frame=f)
        trail.data.bevel_factor_end = d / total
        trail.data.keyframe_insert("bevel_factor_end", frame=f)
    trail.data.bevel_factor_end = 0.0
    trail.data.keyframe_insert("bevel_factor_end", frame=1)
    set_interp("BEZIER")
    # stretched while travelling, shrinks into the parser while fields fly, back as one message
    for f, s in ((1, (3.0, 0.8, 0.8)), (1050, (3.0, 0.8, 0.8)), (1062, (0.05, 0.05, 0.05)), (1150, (0.05, 0.05, 0.05)),
                 (1165, (3.0, 0.8, 0.8))):
        packet.scale = s
        packet.keyframe_insert("scale", frame=f)
    key_visible(packet, 464, 2311)

    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.03, location=(-10, 2, 0.04))
    streak = bpy.context.active_object
    streak.scale = (4, 1, 1)
    streak.data.materials.append(emission("StreakCore", (0.6, 0.95, 1.0), 80.0))
    sl = link(bpy.data.objects.new("StreakLight", bpy.data.lights.new("StreakLight", "POINT")), scene)
    sl.data.color, sl.data.energy, sl.parent = CYAN, 25, streak
    hook = poly_curve("HookTrail", [(-10, 2, 0.02), (-1.5, 2, 0.02)], 0.01,
                      glow("HookTrailMat", CYAN, 6.0, ((120, 6.0), (170, 0.0))), scene)
    set_interp("LINEAR")
    for f, x in ((25, -10.0), (130, -1.5)):
        streak.location = (x, 2, 0.04)
        streak.keyframe_insert("location", frame=f)
        hook.data.bevel_factor_end = (x + 10) / 8.5
        hook.data.keyframe_insert("bevel_factor_end", frame=f)
    set_interp("BEZIER")
    key_visible(streak, 1, 150)


def build_lights(scene):
    def area(name, loc, rot, size, color, keys):
        light = bpy.data.lights.new(name, "AREA")
        light.size = size
        light.color = color
        obj = link(bpy.data.objects.new(name, light), scene)
        obj.location, obj.rotation_euler = loc, rot
        obj.visible_camera = False
        for f, e in keys:
            light.energy = e
            light.keyframe_insert("energy", frame=f)

    area("Key", (2, -6, 10), (math.radians(30), 0, 0), 9, (0.85, 0.9, 1.0),
         ((1, 0), (160, 0), (280, 900), (2700, 900)))
    area("Rim", (0, 9, 3), (math.radians(-75), 0, 0), 12, CYAN, ((1, 0), (180, 0), (300, 700)))
    area("Fill", (-9, -6, 4), (math.radians(60), 0, math.radians(-50)), 6, AMBER, ((1, 0), (200, 0), (320, 250)))


# --------------------------------------------------------------------------- camera
CAMERA_KEYS = [
    # frame, location, target, lens, f-stop
    (1, (-10.6, 0.7, 0.5), (-9.6, 2.0, 0.03), 45, 1.6),
    (75, (-6.4, 0.7, 0.5), (-5.3, 2.0, 0.03), 45, 1.6),
    (140, (-2.6, 0.7, 0.5), (-1.6, 2.0, 0.03), 45, 1.6),
    (240, (0.0, -17.0, 13.0), (0.0, 0.0, 0.0), 40, 9.0),
    (410, (13.0, -12.0, 8.0), (0.0, 0.0, 0.0), 40, 9.0),
    (480, (-12.0, -3.5, 3.5), (-8.4, 2.0, 0.25), 45, 4.0),
    (530, (-10.0, 0.3, 0.9), (-7.6, 2.0, 0.15), 45, 2.5),
    (580, (-4.2, 0.4, 1.5), (-2.3, 1.4, 0.1), 40, 3.0),
    (615, (-1.2, 0.7, 2.4), (-1.2, 0.95, 0.3), 35, 4.0),
    (655, (-1.85, 0.42, 0.72), (-1.45, 1.1, 0.40), 35, 2.0),
    (800, (-1.4, 0.45, 0.6), (-1.0, 1.1, 0.40), 35, 2.0),
    (850, (-0.55, 0.45, 1.2), (-0.4, 1.1, 0.36), 35, 2.4),
    (1000, (0.0, 0.55, 1.05), (-0.35, 1.1, 0.36), 35, 2.4),
    (1035, (0.05, 0.42, 0.62), (0.35, 1.1, 0.40), 35, 2.0),
    (1210, (0.95, 0.42, 0.62), (0.7, 1.1, 0.40), 35, 2.0),
    (1250, (0.85, 0.4, 0.8), (1.35, 1.1, 0.42), 30, 2.0),
    (1440, (2.2, 0.3, 1.15), (1.35, 1.1, 0.42), 35, 2.2),
    (1500, (2.05, -1.5, 0.7), (1.55, -0.6, 0.42), 35, 2.0),
    (1650, (0.75, -1.6, 0.72), (1.05, -0.6, 0.45), 35, 2.0),
    (1725, (0.95, -1.5, 1.1), (1.15, -0.55, 0.55), 35, 2.2),
    (1765, (0.55, -1.25, 0.42), (0.2, -0.6, 0.5), 30, 1.8),
    (1950, (-0.2, -1.3, 0.5), (0.15, -0.6, 0.47), 30, 1.8),
    (1985, (0.15, -0.74, 0.58), (-0.8, -0.7, 0.4), 35, 2.0),
    (2125, (-0.42, -0.74, 0.56), (-1.3, -0.7, 0.4), 35, 2.0),
    (2165, (-0.95, -1.25, 0.7), (-1.4, -0.7, 0.42), 35, 2.2),
    (2225, (-1.4, -1.7, 1.5), (-2.4, -1.5, 0.1), 35, 3.0),
    (2300, (-5.8, -4.6, 2.2), (-8.4, -2.0, 0.25), 40, 4.0),
    (2440, (0.0, -13.0, 17.0), (0.0, -0.6, 0.0), 40, 9.0),
    (2700, (0.0, -14.0, 19.0), (0.0, -0.6, 0.0), 40, 9.0),
]


def build_camera(scene):
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.sensor_fit = "VERTICAL"
    cam_data.sensor_height = 30
    cam_data.clip_start = 0.005
    cam = link(bpy.data.objects.new("Camera", cam_data), scene)
    target = link(bpy.data.objects.new("CamTarget", None), scene)
    cam.constraints.new("TRACK_TO").target = target
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = target
    cam_data.dof.aperture_blades = 7
    for f, loc, tgt, lens, fstop in CAMERA_KEYS:
        cam.location = loc
        cam.keyframe_insert("location", frame=f)
        target.location = tgt
        target.keyframe_insert("location", frame=f)
        cam_data.lens = lens
        cam_data.keyframe_insert("lens", frame=f)
        cam_data.dof.aperture_fstop = fstop
        cam_data.dof.keyframe_insert("aperture_fstop", frame=f)
    for idb in (cam, target, cam_data):
        for fc in action_fcurves(idb.animation_data.action):
            for kp in fc.keyframe_points:
                kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
    scene.camera = cam


# --------------------------------------------------------------------------- overlay (titles)
def faded_text(scene, body, loc, size, color, font, f_in, f_out, align="LEFT", strength=6.0):
    cu = bpy.data.curves.new("txt", "FONT")
    cu.body = body
    cu.size = size
    cu.align_x = align
    cu.font = bpy.data.fonts.load(font, check_existing=True)
    mat = bpy.data.materials.new("Txt")
    mat.surface_render_method = "BLENDED"
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (*color, 1)
    em.inputs["Strength"].default_value = strength
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    cu.materials.append(mat)
    obj = link(bpy.data.objects.new("T_" + body[:12], cu), scene)
    obj.location = loc
    fac = mix.inputs[0]
    for f, v in ((f_in - 1, 0.0), (f_in + 10, 1.0), (f_out - 10, 1.0), (f_out, 0.0)):
        key_socket(fac, max(1, f), v)
    obj.location.y = loc[1] - 0.08
    obj.keyframe_insert("location", frame=max(1, f_in - 1))
    obj.location.y = loc[1]
    obj.keyframe_insert("location", frame=f_in + 14)
    return obj


CHAPTERS = [
    ("01", "MARKET DATA IN", "NASDAQ ITCH 5.0  ·  MoldUDP64  ·  10GbE", 485, 630),
    ("02", "INGRESS", "SerDes lanes  ·  MAC  ·  CRC-32 frame check", 640, 840),
    ("03", "MOLDUDP64", "Sequence check  ·  PTP timestamp  ·  unpack", 845, 1020),
    ("04", "ITCH PARSER", "Message split into fields, decoded in parallel", 1025, 1215),
    ("05", "ORDER STORE", "Hash table in BRAM  ·  2 banks × 4 ways + stash", 1220, 1485),
    ("06", "DEPTH BOOK", "One slot per price tick  ·  bitmap tree  ·  top 5", 1490, 1725),
    ("07", "SIGNAL", "Order-book imbalance on DSP48  ·  no divider", 1730, 1965),
    ("08", "PRE-TRADE RISK", "Notional multiply  ·  limit comparators", 1970, 2145),
    ("09", "ORDER OUT", "NASDAQ OUCH  ·  back on the wire", 2150, 2300),
]
BAR_START, BAR_END = 645, 2285


def build_overlay():
    ov = bpy.data.scenes.new("Overlay")
    ov.render.engine = "BLENDER_EEVEE"
    ov.render.resolution_x, ov.render.resolution_y = RES
    ov.render.film_transparent = True
    ov.render.fps = FPS
    ov.frame_start, ov.frame_end = 1, FRAMES
    ov.eevee.taa_render_samples = 8
    ov.view_settings.view_transform = "Standard"
    cam_data = bpy.data.cameras.new("OverlayCam")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = 10
    cam = link(bpy.data.objects.new("OverlayCam", cam_data), ov)
    cam.location = (0, 0, 10)
    ov.camera = cam

    build_scrims(ov)
    grey = (0.45, 0.5, 0.56)
    L = -3.6

    faded_text(ov, "Markets move in", (0, 2.3, 0), 0.42, WHITE, FONT_LIGHT, 20, 160, "CENTER")
    faded_text(ov, "nanoseconds.", (0, 1.55, 0), 0.62, CYAN, FONT_SEMI, 45, 160, "CENTER", 8)

    faded_text(ov, "AURA-HFT", (L, 4.2, 0), 0.62, WHITE, FONT_SEMI, 200, 470)
    faded_text(ov, "Tick-to-trade pipeline on FPGA", (L, 3.65, 0), 0.24, grey, FONT_LIGHT, 215, 470)
    faded_text(ov, "AMD Kria KR260  ·  Zynq UltraScale+", (L, -4.45, 0), 0.2, grey, FONT_MONO, 240, 470)

    for num, title, sub, f_in, f_out in CHAPTERS:
        faded_text(ov, num, (L, 4.2, 0), 0.26, AMBER if num == "08" else CYAN, FONT_MONO, f_in, f_out)
        faded_text(ov, title, (L + 0.55, 4.2, 0), 0.34, WHITE, FONT_SEMI, f_in + 4, f_out)
        faded_text(ov, sub, (L, 3.72, 0), 0.19, grey, FONT_LIGHT, f_in + 8, f_out)

    faded_text(ov, "ORDER SENT", (0, 0.9, 0), 0.5, GREEN, FONT_SEMI, 2240, 2330, "CENTER", 8)

    ns = CYCLES * 1000 / CLOCK_MHZ
    faded_text(ov, f"{CYCLES} CYCLES", (0, 2.3, 0), 0.5, WHITE, FONT_MONO, 2345, 2701, "CENTER")
    faded_text(ov, f"{ns:.1f} ns", (0, 1.1, 0), 1.15, CYAN, FONT_SEMI, 2360, 2701, "CENTER", 9)
    faded_text(ov, "tick-to-trade  ·  cycle-accurate simulation", (0, 0.5, 0), 0.22, grey, FONT_LIGHT, 2375, 2701,
               "CENTER")
    faded_text(ov, f"reference clock {CLOCK_MHZ:g} MHz", (0, 0.1, 0), 0.2, grey, FONT_MONO, 2380, 2701, "CENTER")
    faded_text(ov, "0 divergence", (0, -0.95, 0), 0.42, GREEN, FONT_SEMI, 2560, 2701, "CENTER", 7)
    faded_text(ov, f"order book vs {REAL_MESSAGES} real NASDAQ ITCH messages", (0, -1.45, 0), 0.2, WHITE, FONT_LIGHT,
               2570, 2701, "CENTER", 4)
    faded_text(ov, "AAPL · MSFT · TSLA  ·  01/30/2019", (0, -1.8, 0), 0.18, grey, FONT_MONO, 2580, 2701, "CENTER")
    faded_text(ov, "AURA-HFT", (0, -3.7, 0), 0.5, WHITE, FONT_SEMI, 2600, 2701, "CENTER")
    faded_text(ov, "SystemVerilog  ·  Verilator  ·  cocotb  ·  AMD Kria KR260", (0, -4.25, 0), 0.17, grey,
               FONT_MONO, 2610, 2701, "CENTER")

    build_cycle_bar(ov)
    return ov


def scrim(ov, name, loc, scale, keys, flip=False):
    """Black plane in the overlay whose alpha follows a vertical gradient (or is flat)."""
    mat = bpy.data.materials.new(name)
    mat.surface_render_method = "BLENDED"
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    black = nt.nodes.new("ShaderNodeEmission")
    black.inputs["Color"].default_value = (0, 0, 0, 1)
    black.inputs["Strength"].default_value = 0.0
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    mul = nt.nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    if flip is not None:
        coord = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(coord.outputs["Object"], sep.inputs[0])
        ramp = nt.nodes.new("ShaderNodeMapRange")
        ramp.interpolation_type = "SMOOTHERSTEP"
        ramp.inputs["From Min"].default_value = 0.5 if flip else -0.5
        ramp.inputs["From Max"].default_value = -0.5 if flip else 0.5
        nt.links.new(sep.outputs["Y"], ramp.inputs["Value"])
        nt.links.new(ramp.outputs["Result"], mul.inputs[0])
    else:
        mul.inputs[0].default_value = 1.0
    for f, v in keys:
        key_socket(mul.inputs[1], f, v)
    nt.links.new(mul.outputs[0], mix.inputs[0])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(black.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    me = bpy.data.meshes.new(name)
    me.from_pydata([(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], [], [(0, 1, 2, 3)])
    me.materials.append(mat)
    obj = link(bpy.data.objects.new(name, me), ov)
    obj.location, obj.scale = loc, scale
    return obj


def build_scrims(ov):
    scrim(ov, "ScrimTop", (0, 4.0, -1), (9, 2.4, 1), ((1, 0.75),), flip=False)
    scrim(ov, "ScrimBottom", (0, -4.0, -1), (9, 3.0, 1), ((1, 0.9),), flip=True)
    scrim(ov, "EndPlate", (0, 0, -0.5), (9, 11, 1), ((1, 0.0), (2320, 0.0), (2380, 0.82)), flip=None)


def build_cycle_bar(ov):
    """CYCLES segments along the bottom edge: a progress bar for the packet's trip through the die."""
    width = 7.2
    seg = width / CYCLES
    for c in range(CYCLES):
        x = -width / 2 + (c + 0.5) * seg
        f = int(BAR_START + (BAR_END - BAR_START) * (c + 1) / CYCLES)
        mat = bpy.data.materials.new(f"Seg{c}")
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*CYAN, 1)
        nt.links.new(em.outputs[0], out.inputs[0])
        s = em.inputs["Strength"]
        for fk, v in ((1, 0.0), (BAR_START - 20, 0.0), (BAR_START, 0.15), (f, 0.15), (f + 2, 7.0), (2660, 7.0),
                      (2700, 0.0)):
            key_socket(s, fk, v)
        me = bpy.data.meshes.new(f"Seg{c}")
        me.from_pydata([(-0.5, -0.5, 0), (0.5, -0.5, 0), (0.5, 0.5, 0), (-0.5, 0.5, 0)], [], [(0, 1, 2, 3)])
        me.materials.append(mat)
        p = link(bpy.data.objects.new(f"Seg{c}", me), ov)
        p.location, p.scale = (x, -4.75, 0), (seg * 0.7, 0.07, 1)


# --------------------------------------------------------------------------- compositor / output
def build_compositor(scene, overlay):
    tree = bpy.data.node_groups.new("Comp", "CompositorNodeTree")
    tree.interface.new_socket("Image", in_out="OUTPUT", socket_type="NodeSocketColor")
    scene.compositing_node_group = tree
    n = tree.nodes
    main = n.new("CompositorNodeRLayers")
    main.scene = scene
    ovl = n.new("CompositorNodeRLayers")
    ovl.scene = overlay
    bloom = n.new("CompositorNodeGlare")
    bloom.inputs["Type"].default_value = "Bloom"
    bloom.inputs["Quality"].default_value = "High"
    bloom.inputs["Threshold"].default_value = 0.8
    bloom.inputs["Strength"].default_value = 0.6
    bloom.inputs["Size"].default_value = 0.7
    lens = n.new("CompositorNodeLensdist")
    lens.inputs["Dispersion"].default_value = 0.012
    over = n.new("CompositorNodeAlphaOver")
    out = n.new("NodeGroupOutput")
    tree.links.new(main.outputs["Image"], bloom.inputs["Image"])
    tree.links.new(bloom.outputs["Image"], lens.inputs["Image"])
    tree.links.new(lens.outputs["Image"], over.inputs["Background"])
    tree.links.new(ovl.outputs["Image"], over.inputs["Foreground"])
    tree.links.new(over.outputs["Image"], out.inputs[0])


def setup_output(scene):
    """Render PNG frames (resumable); encode_video_v2.py assembles the MP4 with the voiceover."""
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_depth = "8"
    scene.render.use_overwrite = False
    scene.render.use_placeholder = True
    scene.render.filepath = os.path.join(ROOT, "render", "frames_v2", "f_")


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = setup_scene()
    build_board(scene)
    build_die(scene)
    build_pipeline(scene)
    build_packet(scene)
    build_lights(scene)
    build_camera(scene)
    overlay = build_overlay()
    build_compositor(scene, overlay)
    setup_output(scene)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "aura_hft_promo_v2.blend"))
    print("BUILD_OK", len(bpy.data.objects))


main()
