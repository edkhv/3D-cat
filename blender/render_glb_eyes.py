"""Render close-up views of the eyes of a cat GLB (Cycles, no fur) — for comparing
eye geometry without the fur shells of the site.

  blender -b --factory-startup --python blender/render_glb_eyes.py -- <file.glb> <out_prefix> [hide:regex]

Example: blender -b --factory-startup --python blender/render_glb_eyes.py -- \
           models/cat.glb renders/eyes/x "Cornea|Glint"
"""
import bpy, math, re, sys, os
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
GLB, PREFIX = argv[0], argv[1]
HIDE = re.compile(argv[2], re.I) if len(argv) > 2 else None
OUT = os.path.dirname(PREFIX)
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)

# ---- collect eye geometry ----------------------------------------------------
eye_mats = {}          # material name -> list of object-local polygons centres (world)
all_eye_pts = []
iris_pts, iris_n = [], Vector((0, 0, 0))
for ob in bpy.data.objects:
    if ob.type != 'MESH':
        continue
    me = ob.data
    for i, m in enumerate(me.materials):
        if not m or not m.name.startswith("Eye"):
            continue
        pts = [p.center for p in me.polygons if p.material_index == i]
        if not pts:
            continue
        world = [ob.matrix_world @ p for p in pts]
        eye_mats.setdefault(m.name, []).extend(world)
        if not m.name.startswith("EyeSclera"):
            all_eye_pts += world
        if m.name.startswith("EyeIris"):
            iris_pts += world
            for p in me.polygons:
                if p.material_index == i:
                    iris_n += ob.matrix_world.to_3x3() @ p.normal
if not iris_pts:
    raise SystemExit("no iris faces found")
iris_n.normalize()

allpts = []
body_pts = []
for ob in bpy.data.objects:
    if ob.type == 'MESH':
        pts = [ob.matrix_world @ v.co for v in ob.data.vertices]
        allpts += pts
        if ob.name.startswith("CatBody") or ob.name.startswith("CatMesh"):
            body_pts += pts
body_c = sum(allpts, Vector()) / len(allpts)
if (sum(iris_pts, Vector()) / len(iris_pts) - body_c).dot(iris_n) < 0:
    iris_n = -iris_n

centre = sum(iris_pts + eye_mats.get("EyeSclera", []), Vector()) / len(iris_pts + eye_mats.get("EyeSclera", []))

# eye-plane basis (same convention as patch_cap)
ref = Vector((0, 0, 1)) if abs(iris_n.z) < 0.9 else Vector((1, 0, 0))
right = iris_n.cross(ref).normalized()
up = right.cross(iris_n).normalized()


def ext(pts, axis):
    v = [p.dot(axis) for p in pts]
    return max(v) - min(v)


sep = ext(iris_pts, right)
tall = max(ext(iris_pts, up), 1e-4)
print("[head] eyes=%d sep=%.4f tall=%.4f  iris radius=%.4f" % (len(iris_pts), sep, tall, tall / 2))
print("[head] materials:", sorted(eye_mats))

# ---- hide materials for inspection ------------------------------------------
if HIDE:
    for ob in bpy.data.objects:
        if ob.type == 'MESH':
            keep = [i for i, m in enumerate(ob.data.materials) if not (m and HIDE.search(m.name))]
            for p in ob.data.polygons:
                if p.material_index not in keep:
                    p.material_index = 0
            print("[head] hide", HIDE.pattern, "in", ob.name)


def add_area(loc, rot, energy, size):
    d = bpy.data.lights.new("A", 'AREA')
    d.energy, d.size = energy, size
    o = bpy.data.objects.new("A", d)
    o.location, o.rotation_euler = loc, rot
    bpy.context.scene.collection.objects.link(o)


world = bpy.data.worlds.new("W")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.05, 0.06, 1)
bpy.context.scene.world = world
add_area((0.4, -0.4, 0.45), (math.radians(55), 0, math.radians(45)), 8, 0.5)
add_area((-0.35, 0.3, 0.35), (math.radians(-60), 0, math.radians(-140)), 3, 0.5)
add_area((0.0, 0.0, 0.8), (0, 0, 0), 2, 0.6)

cam_data = bpy.data.cameras.new("Cam")
cam_data.lens = 85
cam = bpy.data.objects.new("Cam", cam_data)
bpy.context.scene.collection.objects.link(cam)
bpy.context.scene.camera = cam

sc = bpy.context.scene
sc.render.engine = 'CYCLES'
sc.cycles.samples = 48
sc.cycles.use_denoising = True
sc.render.resolution_x = sc.render.resolution_y = 900
sc.view_settings.look = 'None'

def look_at(target):
    cam.rotation_euler = (cam.location - target).to_track_quat('Z', 'Y').to_euler()

def shoot(name, angle_deg, elev_deg, fit_mul, target=None, base=None):
    target = target or centre
    base = base if base is not None else max(sep + tall * 1.5, 0.03)
    upv = Vector((0, 0, 1))
    side = iris_n.cross(upv).normalized() if abs(iris_n.dot(upv)) < 0.95 else Vector((1, 0, 0))
    d = iris_n * math.cos(math.radians(angle_deg)) + side * math.sin(math.radians(angle_deg))
    d = (d * math.cos(math.radians(elev_deg)) + upv * math.sin(math.radians(elev_deg))).normalized()
    fit = max(base * fit_mul, 0.01)
    dist = fit / math.tan(cam_data.angle / 2)
    cam.location = target + d * dist
    look_at(target)
    sc.render.filepath = f"{PREFIX}{name}.png"
    bpy.ops.render.render(write_still=True)
    print("[head] wrote", sc.render.filepath)

shoot("_eye_front", 0, 0, 0.95)
shoot("_eye_34", -32, 8, 1.0)
shoot("_head_front", 0, 5, 2.6)

# tight close-up of a single eye
left = [p for p in iris_pts if p.dot(right) < sum(q.dot(right) for q in iris_pts) / len(iris_pts)]
one = sum(left, Vector()) / len(left)
one_fit = tall * 3.4
shoot("_one_front", 0, 0, 1.0, target=one, base=one_fit)
shoot("_one_34", -40, 10, 1.1, target=one, base=one_fit)
