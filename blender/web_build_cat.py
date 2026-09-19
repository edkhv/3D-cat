"""
Web version of the cat: light skin mesh + simple materials + armature + baked
animations, exported to GLB for three.js.

  blender -b --factory-startup --python web_build_cat.py

Output: web/models/cat.glb  (+ cat_web.blend for reference)
"""
import bpy, bmesh, math, os, sys
from mathutils import Vector, Matrix, Euler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_cat as bc                      # anatomy tables / helpers (main() guarded)

ROOT = os.path.dirname(HERE)
# repo layout: <root>/models + <root>/blender, dev layout: <cat>/web/models
WEB = ROOT if os.path.isdir(os.path.join(ROOT, "models")) else os.path.join(HERE, "web")
os.makedirs(os.path.join(WEB, "models"), exist_ok=True)
R = math.radians


def log(*a):
    print("[web]", *a, flush=True)


def tri_count(ob):
    return sum(len(p.vertices) - 2 for p in ob.data.polygons)


def activate(ob):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    return ob


def apply_mods(ob):
    activate(ob)
    for m in list(ob.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


def join(objs, name):
    objs = [o for o in objs if o]
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    return ob


# --------------------------------------------------------------- 1. skin
def build_skin():
    cat = bc.build_body()                       # metaball -> mesh (~11k faces)
    m_skin = bc.mat_simple("CatBlack", (0.016, 0.015, 0.015), rough=0.92, spec=0.15)
    m_inner = bc.mat_simple("InnerEar", (0.098, 0.036, 0.036), rough=0.92, spec=0.12)
    cat.data.materials.clear()
    cat.data.materials.append(m_skin)
    ears = bc.build_ears(m_skin, m_inner)
    cat = join([cat] + ears, "CatBody")
    cat = bc.merge_slots(cat)
    mod = cat.modifiers.new("Smooth", 'SMOOTH')
    mod.factor = 0.5
    mod.iterations = 3
    apply_mods(cat)
    bc.shade_smooth(cat, 34)
    apply_mods(cat)
    log("skin:", len(cat.data.vertices), "verts", tri_count(cat), "tris")

    dec = cat.modifiers.new("Decimate", 'DECIMATE')
    dec.decimate_type = 'COLLAPSE'
    dec.ratio = 0.42
    apply_mods(cat)
    bc.shade_smooth(cat, 34)
    log("decimated:", len(cat.data.vertices), "verts", tri_count(cat), "tris")
    return cat


# --------------------------------------------------- 2. eyes / nose / whiskers
def build_face(cat):
    m_sclera = bc.mat_simple("EyeSclera", (0.020, 0.017, 0.015), rough=0.35, spec=0.4)
    m_iris = bc.mat_simple("EyeIris", (0.42, 0.50, 0.10), rough=0.22, spec=0.6)
    m_pupil = bc.mat_simple("EyePupil", (0.008, 0.008, 0.010), rough=0.12, spec=0.7)
    m_cornea = bc.mat_simple("EyeCornea", (1, 1, 1), rough=0.03, spec=0.5, transmission=1.0, ior=1.376)
    # glTF has no transmission here -> give the cornea explicit alpha instead
    cb = m_cornea.node_tree.nodes["Principled BSDF"]
    bc.set_input(cb, "Alpha", 0.28)
    m_cornea.blend_method = 'BLEND' if hasattr(m_cornea, "blend_method") else m_cornea.blend_method
    objs = []
    for s in (1, -1):
        fwd = Vector((bc.EYE_DIR.x, bc.EYE_DIR.y * s, bc.EYE_DIR.z)).normalized()
        c = Vector((bc.EYE_C.x, bc.EYE_C.y * s, bc.EYE_C.z)) - fwd * (bc.EYE_R * 0.30)
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=14, radius=bc.EYE_R)
        bmesh.ops.translate(bm, vec=c, verts=bm.verts)
        o = bc.new_obj_from_bm("EyeBall_%d" % s, bm)
        o.data.materials.append(m_sclera)
        bc.shade_smooth(o, 60)
        objs.append(o)
        for key, (rmul, ya, za, mat) in {
            "iris": (1.0040, 63.0, 63.0, m_iris),
            "pupil": (1.0085, 32.0, 37.0, m_pupil),
            "cornea": (1.050, 74.0, 74.0, m_cornea),
        }.items():
            bm = bc.patch_cap(bc.EYE_R * rmul, fwd, ya, za, rings=5, segs=28)
            bmesh.ops.translate(bm, vec=c, verts=bm.verts)
            o = bc.new_obj_from_bm("%s_%d" % (key, s), bm)
            o.data.materials.append(mat)
            bc.shade_smooth(o, 60)
            objs.append(o)

    m_nose = bc.mat_simple("NoseLeather", (0.0115, 0.0105, 0.0110), rough=0.34, spec=0.55, coat=0.35)
    p, n = bc.snap(cat, bc.NOSE_TIP)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=1.0)
    for v in bm.verts:
        v.co.x *= 0.0066
        v.co.y *= 0.0086
        v.co.z *= 0.0056
    for v in bm.verts:
        t = max(0.0, -(v.co.z / 0.005))
        v.co.x += 0.0022 * t ** 1.5
        v.co.y *= (1.0 - 0.45 * t)
        v.co.z -= 0.0012 * t
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.translate(bm, vec=p + Vector((-0.0018, 0, -0.0016)), verts=bm.verts)
    nose = bc.new_obj_from_bm("Nose", bm)
    nose.data.materials.append(m_nose)
    bc.shade_smooth(nose, 60)
    objs.append(nose)

    strips = bc.build_whiskers(cat)             # curves -> mesh
    bpy.ops.object.select_all(action='DESELECT')
    for w in strips:
        w.select_set(True)
    bpy.context.view_layer.objects.active = strips[0]
    bpy.ops.object.convert(target='MESH')
    whisk = [o for o in bpy.context.selected_objects]
    m_wh = bc.mat_simple("Whisker", (0.55, 0.53, 0.48), rough=0.30, spec=0.4)
    for w in whisk:
        w.data.materials.clear()
        w.data.materials.append(m_wh)
    face = join(objs + whisk, "CatFace")
    face.data.name = "CatFaceMesh"
    face = bc.merge_slots(face)
    log("face:", len(face.data.vertices), "verts", tri_count(face), "tris",
        [m.name for m in face.data.materials])
    return face


# ------------------------------------------------------------------ 3. rig
BONES = [
    # name,        head,                    tail,                     parent
    ("hips",       (-0.115, 0.000, 0.200),  (0.000, 0.000, 0.200),    None),
    ("chest",      (0.000, 0.000, 0.200),   (0.115, 0.000, 0.205),    "hips"),
    ("neck",       (0.115, 0.000, 0.205),   (0.155, 0.000, 0.250),    "chest"),
    ("head",       (0.155, 0.000, 0.250),   (0.228, 0.000, 0.292),    "neck"),
    ("tail1",      (-0.115, 0.000, 0.200),  (-0.200, 0.020, 0.220),   "hips"),
    ("tail2",      (-0.200, 0.020, 0.220),  (-0.235, 0.050, 0.300),   "tail1"),
    ("tail3",      (-0.235, 0.050, 0.300),  (-0.205, 0.085, 0.400),   "tail2"),
    ("frontL_up",  (0.104, 0.046, 0.185),   (0.108, 0.046, 0.090),    "chest"),
    ("frontL_low", (0.108, 0.046, 0.090),   (0.120, 0.046, 0.018),    "frontL_up"),
    ("frontR_up",  (0.104, -0.046, 0.185),  (0.108, -0.046, 0.090),   "chest"),
    ("frontR_low", (0.108, -0.046, 0.090),  (0.120, -0.046, 0.018),   "frontR_up"),
    ("hindL_up",   (-0.118, 0.052, 0.168),  (-0.090, 0.050, 0.078),   "hips"),
    ("hindL_low",  (-0.090, 0.050, 0.078),  (-0.020, 0.047, 0.018),   "hindL_up"),
    ("hindR_up",   (-0.118, -0.052, 0.168), (-0.090, -0.050, 0.078),  "hips"),
    ("hindR_low",  (-0.090, -0.050, 0.078), (-0.020, -0.047, 0.018),  "hindR_up"),
]


def build_rig():
    arm_data = bpy.data.armatures.new("CatArm")
    arm = bc.link(bpy.data.objects.new("CatArmature", arm_data))
    activate(arm)
    bpy.ops.object.mode_set(mode='EDIT')
    made = {}
    for name, head, tail, parent in BONES:
        b = arm_data.edit_bones.new(name)
        b.head, b.tail = Vector(head), Vector(tail)
        b.use_connect = False
        if parent:
            b.parent = made[parent]
        made[name] = b
    bpy.ops.object.mode_set(mode='OBJECT')
    for pb in arm.pose.bones:
        pb.rotation_mode = 'XYZ'
    return arm


def skin(mesh_objs, arm):
    for ob in mesh_objs:
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        try:
            bpy.ops.object.parent_set(type='ARMATURE_AUTO')
            log("auto weights ok:", ob.name)
        except Exception as ex:
            log("auto weights failed -> envelope:", ob.name, ex)
            bpy.ops.object.parent_set(type='ARMATURE_ENVELOPE')


# ------------------------------------------------------------ 4. animation
def new_action(arm, name):
    if not arm.animation_data:
        arm.animation_data_create()
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    arm.animation_data.action = act
    return act


def key(arm, frame, pose):
    for name, rot in pose.items():
        pb = arm.pose.bones[name]
        pb.rotation_euler = Euler([R(a) for a in rot], 'XYZ')
        pb.keyframe_insert("rotation_euler", frame=frame)
    for name in getattr(key, "locs", []):
        pass


def key_loc(arm, frame, name, loc):
    pb = arm.pose.bones[name]
    pb.location = Vector(loc)
    pb.keyframe_insert("location", frame=frame)


def build_actions(arm):
    bones = [b[0] for b in BONES]

    # ---- idle: soft breathing, tail sway, head micro motion
    act = new_action(arm, "Idle")
    N = 48
    for f in range(N + 1):
        t = 2 * math.pi * f / N
        pose = {n: (0, 0, 0) for n in bones}
        pose["chest"] = (1.2 * math.sin(t), 0, 0)
        pose["hips"] = (0.8 * math.sin(t + 0.4), 0, 0)
        pose["head"] = (-1.5 * math.sin(t + 0.8), 0, 2.0 * math.sin(t * 0.5))
        pose["neck"] = (-1.0 * math.sin(t + 0.6), 0, 0)
        pose["tail1"] = (0, 0, 6 * math.sin(t))
        pose["tail2"] = (0, 0, 8 * math.sin(t + 0.6))
        pose["tail3"] = (0, 0, 10 * math.sin(t + 1.2))
        key(arm, f + 1, pose)
        key_loc(arm, f + 1, "hips", (0, 0, 0.004 * math.sin(t)))
    act.frame_end = N + 1

    # ---- run: 4 leg cycle, body bob, tail up, head forward
    act = new_action(arm, "Run")
    N = 20
    A = 34.0
    for f in range(N + 1):
        t = 2 * math.pi * f / N
        pose = {n: (0, 0, 0) for n in bones}
        sw = math.sin(t)
        pose["frontL_up"] = (A * sw, 0, 0)
        pose["frontL_low"] = (-max(0.0, 22 * math.sin(t - 0.9)), 0, 0)
        pose["frontR_up"] = (A * math.sin(t + math.pi), 0, 0)
        pose["frontR_low"] = (-max(0.0, 22 * math.sin(t + math.pi - 0.9)), 0, 0)
        pose["hindL_up"] = (A * math.sin(t + math.pi), 0, 0)
        pose["hindL_low"] = (-max(0.0, 26 * math.sin(t + math.pi - 0.8)), 0, 0)
        pose["hindR_up"] = (A * sw, 0, 0)
        pose["hindR_low"] = (-max(0.0, 26 * math.sin(t - 0.8)), 0, 0)
        pose["chest"] = (4.0 * math.sin(2 * t), 0, 3.0 * math.sin(t))
        pose["hips"] = (-4.0 * math.sin(2 * t), 0, -3.0 * math.sin(t))
        pose["neck"] = (-6 + 2 * math.sin(2 * t), 0, 0)
        pose["head"] = (-4 + 2 * math.sin(2 * t + 1.0), 0, 0)
        pose["tail1"] = (0, 0, -6 + 5 * math.sin(t))
        pose["tail2"] = (0, 0, 10 * math.sin(t + 0.7))
        pose["tail3"] = (0, 0, 12 * math.sin(t + 1.4))
        key(arm, f + 1, pose)
        key_loc(arm, f + 1, "hips", (0, 0, 0.012 * math.sin(2 * t + 1.2)))
    act.frame_end = N + 1

    # ---- swipe: right paw strike (played when the cat hits the ball)
    act = new_action(arm, "Swipe")
    frames = [
        {0: dict(frontR_up=(0, 0, 0), neck=(0, 0, 0), head=(0, 0, 0))},
        {5: dict(frontR_up=(-55, 0, -12), neck=(-8, 0, 0), head=(-6, 0, -6))},
        {9: dict(frontR_up=(28, 0, 10), frontR_low=(-30, 0, 0), neck=(4, 0, 0), head=(6, 0, 6))},
        {16: dict(frontR_up=(6, 0, 0), frontR_low=(0, 0, 0), neck=(0, 0, 0), head=(0, 0, 0))},
    ]
    for block in frames:
        for f, pose in block.items():
            full = {n: (0, 0, 0) for n in bones}
            full.update(pose)
            key(arm, f + 1, full)
    act.frame_end = 17

    # stash all actions in NLA so the glTF exporter emits every clip
    ad = arm.animation_data
    ad.action = None
    for name in ("Idle", "Run", "Swipe"):
        a = bpy.data.actions[name]
        tr = ad.nla_tracks.new()
        tr.name = name
        st = tr.strips.new(name, 1, a)
        st.name = name
        tr.mute = False
    log("actions:", [a.name for a in bpy.data.actions])


# ------------------------------------------------------------------- main
def clear_scene():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.armatures, bpy.data.curves, bpy.data.materials):
        for db in list(coll):
            if db.users == 0:
                coll.remove(db)


def main():
    clear_scene()
    cat = build_skin()
    face = build_face(cat)
    # keep the fur mesh centred so the shell offsets behave
    arm = build_rig()
    skin([cat], arm)
    # face parts ride rigidly on the head bone
    vg = face.vertex_groups.new(name="head")
    vg.add(list(range(len(face.data.vertices))), 1.0, 'REPLACE')
    bpy.ops.object.select_all(action='DESELECT')
    face.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE_NAME')
    log("face bound to head bone")

    # pink interior of the ears survives as vertex colour (used by the fur shader)
    me = cat.data
    col = me.color_attributes.new(name="FurTint", type='BYTE_COLOR', domain='CORNER')
    for poly in me.polygons:
        # byte colours clamp to 0..1: skin = white, inner ear = pink mask
        c = (1.0, 1.0, 1.0, 1.0) if poly.material_index == 0 else (1.0, 0.35, 0.30, 1.0)
        for li in poly.loop_indices:
            col.data[li].color = c
    build_actions(arm)

    log("body tris", tri_count(cat), "| face tris", tri_count(face),
        "| total", tri_count(cat) + tri_count(face))

    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(WEB, "cat_web.blend"))
    for ob in bpy.data.objects:
        ob.select_set(ob.type in ('MESH', 'ARMATURE'))
    glb = os.path.join(WEB, "models", "cat.glb")
    bpy.ops.export_scene.gltf(
        filepath=glb,
        export_format='GLB',
        use_selection=True,
        export_apply=False,
        export_animations=True,
        export_animation_mode='ACTIONS',
        export_nla_strips=True,
        export_bake_animation=True,
        export_optimize_animation_size=True,
        export_yup=True,
        export_skins=True,
        export_morph=False,
        export_texcoords=True,
        export_normals=True,
        export_tangents=False,
        export_vertex_color='ACTIVE',
    )
    log("exported", glb, os.path.getsize(glb), "bytes")


main()
