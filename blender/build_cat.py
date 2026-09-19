"""
Realistic black cat with big cute eyes -- fully procedural Blender build.
  blender -b --factory-startup --python build_cat.py -- [--quick] [--no-render] [--final]
Outputs: black_cat.blend + renders/*.png
"""
import bpy, bmesh, math, os, sys, random, time
from mathutils import Vector, Matrix, Quaternion

T0 = time.time()
OUT = os.path.dirname(os.path.abspath(__file__))
RENDER_DIR = os.path.join(OUT, "renders")
ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
QUICK = ("--quick" in ARGS) or bool(os.environ.get("CAT_QUICK"))
NO_RENDER = ("--no-render" in ARGS) or bool(os.environ.get("CAT_NO_RENDER"))
FINAL = "--final" in ARGS
LIVE = bool(os.environ.get("CAT_LIVE"))
random.seed(7)
os.makedirs(RENDER_DIR, exist_ok=True)
V = Vector


def log(*a):
    print("[cat %6.1fs]" % (time.time() - T0), *a, flush=True)


# ------------------------------------------------------------------ helpers
def link(ob):
    sc = bpy.context.scene
    target = bpy.context.collection or sc.collection
    target.objects.link(ob)
    return ob


def new_obj_from_bm(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return link(bpy.data.objects.new(name, me))


def activate(ob):
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    return ob


def shade_smooth(ob, angle=32.0):
    activate(ob)
    bpy.ops.object.shade_smooth()
    try:
        bpy.ops.object.shade_auto_smooth(angle=math.radians(angle))
    except Exception:
        pass


def apply_modifiers(ob):
    activate(ob)
    for m in list(ob.modifiers):
        try:
            bpy.ops.object.modifier_apply(modifier=m.name)
        except Exception as ex:
            log("modifier apply failed", m.name, ex)


def merge_slots(ob):
    """Drop empty material slots, remap face indices."""
    me = ob.data
    mats = list(me.materials)
    for p in me.polygons:
        m = mats[p.material_index] if p.material_index < len(mats) else None
        if m is None:
            p.material_index = 0
    used = sorted({p.material_index for p in me.polygons})
    old = list(me.materials)
    remap = {o: n for n, o in enumerate(used)}
    new = [old[i] for i in used]
    for p in me.polygons:
        p.material_index = remap[p.material_index]
    for i, m in enumerate(new):
        me.materials[i] = m
    for i in range(len(old) - 1, len(new) - 1, -1):
        me.materials.pop(index=i)
    return ob


def snap(ob, p, offset=0.0):
    ok, loc, nor, idx = ob.closest_point_on_mesh(V(p))
    if not ok:
        return V(p), V((1, 0, 0))
    return loc + nor * offset, nor


def set_input(node, names, value):
    for n in (names if isinstance(names, (list, tuple)) else [names]):
        if n in node.inputs:
            node.inputs[n].default_value = value
            return True
    return False


# ---------------------------------------------------------------- materials
def mat_fur_skin():
    m = bpy.data.materials.new("FurSkin")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    set_input(b, "Base Color", (0.006, 0.0058, 0.006, 1))
    set_input(b, "Roughness", 0.65)
    set_input(b, "Specular IOR Level", 0.25)
    set_input(b, "Sheen Weight", 0.35)
    tex = m.node_tree.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 260.0
    tex.inputs["Detail"].default_value = 6.0
    ramp = m.node_tree.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.003, 0.003, 0.003, 1)
    ramp.color_ramp.elements[1].color = (0.011, 0.009, 0.0085, 1)
    m.node_tree.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    m.node_tree.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def mat_fur_hair():
    """Strands: near black at the root, warm brown sheen towards the tip."""
    m = bpy.data.materials.new("FurHair")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled"); b.location = (250, 0)
    ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.location = (-140, 60)
    ramp.color_ramp.interpolation = 'EASE'
    e = ramp.color_ramp.elements
    e[0].position, e[0].color = 0.0, (0.0045, 0.0045, 0.0052, 1)
    e[1].position, e[1].color = 1.0, (0.038, 0.027, 0.021, 1)
    e.new(0.5).color = (0.009, 0.008, 0.0085, 1)
    try:
        hi = nt.nodes.new("ShaderNodeHairInfo"); hi.location = (-420, 60)
        nt.links.new(hi.outputs["Intercept"], ramp.inputs["Fac"])
    except Exception:
        pass
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    set_input(b, "Roughness", 0.34)
    set_input(b, "Specular IOR Level", 0.35)
    set_input(b, "Sheen Weight", 0.12)
    set_input(b, "Anisotropic", 0.55)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def mat_hair_light():
    """Pale fur that lines the inside of the ears on black cats."""
    m = bpy.data.materials.new("FurHairLight")
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
    b = nt.nodes.new("ShaderNodeBsdfPrincipled"); b.location = (250, 0)
    ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.location = (-140, 60)
    e = ramp.color_ramp.elements
    e[0].position, e[0].color = 0.0, (0.16, 0.14, 0.135, 1)
    e[1].position, e[1].color = 1.0, (0.52, 0.47, 0.44, 1)
    try:
        hi = nt.nodes.new("ShaderNodeHairInfo"); hi.location = (-420, 60)
        nt.links.new(hi.outputs["Intercept"], ramp.inputs["Fac"])
    except Exception:
        pass
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    set_input(b, "Roughness", 0.35)
    set_input(b, "Specular IOR Level", 0.3)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def mat_simple(name, color, rough=0.4, spec=0.5, coat=0.0, transmission=0.0, ior=1.45):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    set_input(b, "Base Color", tuple(color) + (1.0,) if len(color) == 3 else color)
    set_input(b, "Roughness", rough)
    set_input(b, "Specular IOR Level", spec)
    set_input(b, "IOR", ior)
    set_input(b, "Coat Weight", coat)
    set_input(b, "Transmission Weight", transmission)
    return m


def mat_iris():
    m = bpy.data.materials.new("EyeIris")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-1250, 0)
    sep = nt.nodes.new("ShaderNodeSeparateXYZ"); sep.location = (-1050, 0)
    comb = nt.nodes.new("ShaderNodeCombineXYZ"); comb.location = (-880, 60)
    leng = nt.nodes.new("ShaderNodeVectorMath"); leng.operation = 'LENGTH'
    leng.location = (-710, 60)
    ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.location = (-520, 60)
    e = ramp.color_ramp.elements
    e[0].position, e[0].color = 0.0, (0.62, 0.66, 0.12, 1)      # amber-green centre
    e[1].position, e[1].color = 1.0, (0.030, 0.075, 0.020, 1)    # limbal ring
    ramp.color_ramp.elements.new(0.66).color = (0.17, 0.32, 0.045, 1)
    noise = nt.nodes.new("ShaderNodeTexNoise"); noise.location = (-710, -280)
    noise.inputs["Scale"].default_value = 90.0
    noise.inputs["Detail"].default_value = 8.0
    mix = nt.nodes.new("ShaderNodeMixRGB"); mix.blend_type = 'OVERLAY'
    mix.inputs["Fac"].default_value = 0.30
    mix.location = (-280, 0)
    nt.links.new(tc.outputs["Object"], sep.inputs["Vector"])
    nt.links.new(sep.outputs["Y"], comb.inputs["Y"])
    nt.links.new(sep.outputs["Z"], comb.inputs["Z"])
    nt.links.new(comb.outputs["Vector"], leng.inputs[0])
    nt.links.new(leng.outputs["Value"], ramp.inputs["Fac"])
    nt.links.new(noise.outputs["Fac"], mix.inputs["Color2"])
    nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(mix.outputs["Color"], b.inputs["Base Color"])
    set_input(b, "Roughness", 0.10)
    set_input(b, "Specular IOR Level", 0.75)
    set_input(b, "Coat Weight", 0.5)
    set_input(b, "Coat Roughness", 0.03)
    return m


# ------------------------------------------------------- metaball cat anatomy
VIS = 0.845          # visible radius factor for stiffness 2 / threshold 0.6
MB_RES = 0.0060 if (FINAL or not QUICK) else 0.0110

# ---- the whole cat is designed around these anchors (metres, +X = nose) ----
EYE_C = V((0.2225, 0.0245, 0.2875))
EYE_R = 0.0175
EYE_DIR = V((0.965, 0.215, 0.145))
NOSE_TIP = V((0.2375, 0.0, 0.2585))
EAR_BASE = V((0.1720, 0.0280, 0.3085))

SPINE = [
    (-0.150, 0.000, 0.205, 0.052),
    (-0.118, 0.000, 0.203, 0.069),
    (-0.062, 0.000, 0.201, 0.072),
    (0.000, 0.000, 0.200, 0.073),
    (0.058, 0.000, 0.203, 0.069),
    (0.100, 0.000, 0.207, 0.058),
]
NECK = [(0.126, 0.000, 0.220, 0.052), (0.152, 0.000, 0.250, 0.047)]
HEAD = [
    (0.158, 0.000, 0.262, 0.041),
    (0.176, 0.000, 0.283, 0.046),
    (0.194, 0.000, 0.296, 0.045),
    (0.207, 0.000, 0.287, 0.042),   # eye plane
    (0.219, 0.000, 0.272, 0.031),   # bridge
    (0.227, 0.000, 0.262, 0.025),   # muzzle
    (0.232, 0.000, 0.2555, 0.019),  # nose leather
    (0.219, 0.000, 0.2465, 0.020),  # chin
    (0.224, 0.000, 0.2375, 0.013),  # jaw
]
CHEEK = (0.202, 0.028, 0.273, 0.025)
TAIL = [
    (-0.170, 0.006, 0.203, 0.024),
    (-0.205, 0.018, 0.222, 0.021),
    (-0.228, 0.034, 0.256, 0.019),
    (-0.238, 0.052, 0.296, 0.018),
    (-0.234, 0.068, 0.336, 0.016),
    (-0.222, 0.080, 0.372, 0.015),
    (-0.206, 0.088, 0.400, 0.013),
    (-0.190, 0.092, 0.418, 0.010),
]
FRONT_LEG = [(0.104, 0.046, 0.185, 0.030), (0.104, 0.046, 0.138, 0.020),
             (0.108, 0.046, 0.090, 0.016), (0.112, 0.046, 0.048, 0.014),
             (0.115, 0.046, 0.024, 0.016), (0.125, 0.046, 0.017, 0.019)]
HIND_LEG = [(-0.118, 0.052, 0.168, 0.046), (-0.104, 0.052, 0.120, 0.030),
            (-0.090, 0.050, 0.078, 0.022), (-0.080, 0.048, 0.048, 0.017),
            (-0.048, 0.047, 0.020, 0.016), (-0.014, 0.047, 0.017, 0.018)]


def mball(mb, co, r, stiff=2.0, neg=False):
    el = mb.elements.new()
    el.co = V(co)
    el.stiffness = stiff
    el.use_negative = neg
    el.radius = max(r, 1e-4) / VIS
    return el


def chain(mb, pts, step=0.5):
    """Interpolated ball chain so consecutive blobs actually fuse."""
    for i in range(len(pts) - 1):
        a, ra = V(pts[i][:3]), pts[i][3]
        b, rb = V(pts[i + 1][:3]), pts[i + 1][3]
        d = (b - a).length
        n = max(1, int(d / max(min(ra, rb) * step, 1e-4)))
        first = 0 if i == 0 else 1
        for k in range(first, n + 1):
            t = k / n
            mball(mb, a.lerp(b, t), ra + (rb - ra) * t)


def build_body():
    mb = bpy.data.metaballs.new("CatMB")
    mb.resolution = mb.render_resolution = MB_RES
    mb.threshold = 0.6
    ob = link(bpy.data.objects.new("CatMB", mb))

    chain(mb, SPINE)
    chain(mb, NECK)
    chain(mb, HEAD)
    chain(mb, TAIL)
    mball(mb, (0.100, 0.0, 0.172), 0.050)                 # breast / deep chest
    mball(mb, (0.2225, 0.0, 0.2410), 0.016)               # chin point
    mball(mb, (0.2080, 0.0, 0.2725), 0.026)               # nose bridge
    mball(mb, (-0.140, 0.0, 0.178), 0.045)                # rump
    for s in (1, -1):
        mball(mb, (CHEEK[0], CHEEK[1] * s, CHEEK[2]), CHEEK[3])
        mball(mb, (0.227, 0.0120 * s, 0.2545), 0.0123)    # whisker pad
        mball(mb, (0.222, 0.0190 * s, 0.2875), 0.0220)    # flat face plane
        mball(mb, (0.198, 0.0240 * s, 0.3015), 0.0170)    # brow ridge
        mball(mb, (0.2335, 0.0245 * s, 0.2875), 0.0190, stiff=1.0, neg=True)  # eye socket
        chain(mb, [(p[0], p[1] * s, p[2], p[3]) for p in FRONT_LEG])
        chain(mb, [(p[0], p[1] * s, p[2], p[3]) for p in HIND_LEG])

    bpy.context.view_layer.update()
    activate(ob)
    bpy.ops.object.convert(target='MESH')
    cat = bpy.context.view_layer.objects.active
    cat.name, cat.data.name = "Cat", "CatMesh"
    log("metaball -> mesh:", len(cat.data.vertices), "verts", len(cat.data.polygons), "faces")
    return cat


# --------------------------------------------------------------------- ears
def build_ear(side):
    """Thin dish shaped ear; the inner (front) surface gets the pink slot."""
    s = side
    HEIGHT, HALF_W, LEAN = 0.057, 0.0255, 0.009
    NU, NV = 18, 14
    bm = bmesh.new()
    front, back = [], []
    for i in range(NU + 1):
        u = i / NU
        w = HALF_W * (1.0 - u ** 1.95) ** 0.42
        cx = LEAN * u ** 2.2
        cz = HEIGHT * u
        th = (0.0055 * (1.0 - 0.72 * u)) / 2.0
        dish = 0.0052 * math.sin(math.pi * min(1.0, u * 0.92 + 0.06)) ** 0.7
        row_f, row_b = [], []
        for j in range(NV + 1):
            v = -1.0 + 2.0 * j / NV
            y = w * v
            # rounded outline near the base corners
            bulge = (1.0 - abs(v) ** 3) * w * 0.10
            x = cx - bulge * 0.4
            f = bm.verts.new((x - dish * (1.0 - v * v) - th, y, cz + bulge * 0.25))
            b = bm.verts.new((x + dish * 0.25 * (1.0 - v * v) + th, y, cz + bulge * 0.25))
            row_f.append(f)
            row_b.append(b)
        front.append(row_f)
        back.append(row_b)
    for i in range(NU):
        for j in range(NV):
            bm.faces.new((front[i][j], front[i][j + 1], front[i + 1][j + 1], front[i + 1][j]))
            bm.faces.new((back[i][j + 1], back[i][j], back[i + 1][j], back[i + 1][j + 1]))
    for i in range(NU):                                   # side rims
        bm.faces.new((front[i][0], front[i + 1][0], back[i + 1][0], back[i][0]))
        bm.faces.new((front[i][NV], back[i][NV], back[i + 1][NV], front[i + 1][NV]))
    for j in range(NV):                                   # base rim
        bm.faces.new((front[0][j], back[0][j], back[0][j + 1], front[0][j + 1]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.verts.ensure_lookup_table()
    ear = new_obj_from_bm("Ear_%s" % ("L" if s > 0 else "R"), bm)
    ear.rotation_euler = (math.radians(-24 * s), math.radians(-7), math.radians(19 * s))
    ear.location = (EAR_BASE.x, EAR_BASE.y * s, EAR_BASE.z)
    return ear


def build_ears(m_skin, m_inner):
    ears = []
    for s in (1, -1):
        e = build_ear(s)
        e.data.materials.append(m_skin)
        e.data.materials.append(m_inner)
        for p in e.data.polygons:
            if p.normal.x < -0.15:                            # inner (front) face
                p.material_index = 1
        shade_smooth(e, 40)
        ears.append(e)
    return ears


# --------------------------------------------------------------------- eyes
def patch_cap(radius, fwd, y_ang, z_ang, rings=10, segs=72):
    """Smooth spherical cap with an elliptical boundary, oriented along fwd."""
    fwd = V(fwd).normalized()
    ref = V((0, 0, 1)) if abs(fwd.z) < 0.9 else V((1, 0, 0))
    right = fwd.cross(ref).normalized()
    up = right.cross(fwd).normalized()
    sy, sz = math.sin(math.radians(y_ang)), math.sin(math.radians(z_ang))
    bm = bmesh.new()
    center = bm.verts.new(fwd * radius)
    ring_prev = None
    for i in range(1, rings + 1):
        t = i / rings
        row = []
        for k in range(segs):
            phi = 2 * math.pi * k / segs
            b = (fwd + right * (sy * math.sin(phi)) + up * (sz * math.cos(phi))).normalized()
            d = (fwd * (1 - t) + b * t).normalized()
            row.append(bm.verts.new(d * radius))
        if ring_prev is None:
            for k in range(segs):
                bm.faces.new((center, row[k], row[(k + 1) % segs]))
        else:
            for k in range(segs):
                k2 = (k + 1) % segs
                bm.faces.new((ring_prev[k], row[k], row[k2], ring_prev[k2]))
        ring_prev = row
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def torus_ring(bm, R, r, seg=72, ring=14, squash=0.90):
    verts = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        row = []
        for j in range(ring):
            b = 2 * math.pi * j / ring
            x = r * math.sin(b)
            y = (R + r * math.cos(b)) * math.cos(a)
            z = (R + r * math.cos(b)) * math.sin(a) * squash
            row.append(bm.verts.new((x, y, z)))
        verts.append(row)
    for i in range(seg):
        for j in range(ring):
            a, b = verts[i][j], verts[(i + 1) % seg][j]
            c, d = verts[(i + 1) % seg][(j + 1) % ring], verts[i][(j + 1) % ring]
            bm.faces.new((a, b, c, d))
    return bm


def build_eyes(cat):
    m_sclera = mat_simple("EyeSclera", (0.014, 0.011, 0.010), rough=0.32, spec=0.4)
    m_iris = mat_iris()
    m_pupil = mat_simple("EyePupil", (0.003, 0.003, 0.004), rough=0.05, spec=0.85, coat=0.9)
    m_cornea = mat_simple("EyeCornea", (1, 1, 1), rough=0.015, spec=0.5,
                          transmission=1.0, ior=1.376)
    m_lid = m_sclera          # rims join the skin and get fur like the rest of the face
    out, lids = [], []
    for s in (1, -1):
        fwd = V((EYE_DIR.x, EYE_DIR.y * s, EYE_DIR.z)).normalized()
        c = V((EYE_C.x, EYE_C.y * s, EYE_C.z)) - fwd * (EYE_R * 0.30)

        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=32, radius=EYE_R)
        bmesh.ops.translate(bm, vec=c, verts=bm.verts)
        o = new_obj_from_bm("EyeBall_%d" % s, bm)
        o.data.materials.append(m_sclera)
        shade_smooth(o, 60)
        out.append(o)

        for key, (rmul, ya, za, mat) in {
            "iris": (1.0040, 63.0, 63.0, m_iris),
            "pupil": (1.0085, 32.0, 37.0, m_pupil),
            "cornea": (1.050, 74.0, 74.0, m_cornea),
        }.items():
            bm = patch_cap(EYE_R * rmul, fwd, ya, za)
            bmesh.ops.translate(bm, vec=c, verts=bm.verts)
            o = new_obj_from_bm("%s_%d" % (key, s), bm)
            o.data.materials.append(mat)
            shade_smooth(o, 60)
            out.append(o)

        bm = bmesh.new()
        torus_ring(bm, EYE_R * 1.10, 0.0038)
        rot = V((1, 0, 0)).rotation_difference(fwd).to_matrix().to_4x4()
        bmesh.ops.transform(bm, matrix=rot, verts=bm.verts)
        bmesh.ops.translate(bm, vec=c + fwd * (EYE_R * 0.20), verts=bm.verts)
        o = new_obj_from_bm("Eyelid_%d" % s, bm)
        o.data.materials.append(m_lid)
        shade_smooth(o, 60)
        lids.append(o)
    return out, lids


# ------------------------------------------------------------ nose and mouth
def build_nose(cat):
    m = mat_simple("NoseLeather", (0.0115, 0.0105, 0.0110), rough=0.34, spec=0.55, coat=0.35)
    p, n = snap(cat, NOSE_TIP)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=32, v_segments=20, radius=1.0)
    for v in bm.verts:
        v.co.x *= 0.0066
        v.co.y *= 0.0086
        v.co.z *= 0.0056
    for v in bm.verts:
        t = max(0.0, -(v.co.z / 0.005))               # pull the bottom into a wedge
        v.co.x += 0.0022 * t ** 1.5
        v.co.y *= (1.0 - 0.45 * t)
        v.co.z -= 0.0012 * t
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bmesh.ops.translate(bm, vec=p + V((-0.0018, 0, -0.0016)), verts=bm.verts)
    o = new_obj_from_bm("Nose", bm)
    o.data.materials.append(m)
    shade_smooth(o, 60)
    return [o]


def build_mouth(cat):
    m = mat_simple("Mouth", (0.016, 0.011, 0.011), rough=0.5)
    out = []
    for s in (1, -1):
        cu = bpy.data.curves.new("Mouth", 'CURVE')
        cu.dimensions = '3D'
        cu.bevel_depth = 0.0008
        cu.bevel_resolution = 3
        cu.resolution_u = 10
        cu.use_fill_caps = True
        sp = cu.splines.new('BEZIER')
        sp.bezier_points.add(2)
        pts = [(0.004 * s, -0.0035), (0.0105 * s, -0.0062), (0.0175 * s, -0.0068)]
        for j, (dy, dz) in enumerate(pts):
            q, _ = snap(cat, NOSE_TIP + V((-0.0055, dy, dz)), offset=0.00025)
            bp = sp.bezier_points[j]
            bp.co = q
            bp.handle_left_type = bp.handle_right_type = 'AUTO'
            bp.radius = (1.0, 0.95, 0.45)[j]
        o = link(bpy.data.objects.new("Mouth_%d" % s, cu))
        o.data.materials.append(m)
        out.append(o)
    return out


# ---------------------------------------------------------------- whiskers
def build_whiskers(cat):
    m = mat_simple("Whisker", (0.55, 0.53, 0.48), rough=0.25, spec=0.55)
    out = []
    for s in (1, -1):
        for i in range(8):
            t = i / 7.0
            pad = V((0.227, 0.0120 * s, 0.2545))
            root, _ = snap(cat, pad + V((0.0, 0.0, 0.0075 - 0.016 * t)), offset=-0.0015)
            yaw = math.radians(88 - 34 * abs(t - 0.3))
            pitch = math.radians(22 - 46 * t)
            d = V((math.cos(pitch) * math.cos(yaw) * 0.6,
                   math.cos(pitch) * math.sin(yaw) * s,
                   math.sin(pitch))).normalized()
            L = 0.070 - 0.016 * abs(t - 0.45) + random.uniform(-0.005, 0.005)
            p1 = root + d * L * 0.5 + V((0, 0, 0.004))
            p2 = root + d * L + V((0.012, 0.002 * s, -0.008 - 0.016 * t))
            cu = bpy.data.curves.new("Whisker", 'CURVE')
            cu.dimensions = '3D'
            cu.bevel_depth = 0.00020
            cu.bevel_resolution = 2
            cu.resolution_u = 8
            cu.use_fill_caps = True
            sp = cu.splines.new('BEZIER')
            sp.bezier_points.add(2)
            for j, (q, r) in enumerate(((root, 1.0), (p1, 0.60), (p2, 0.15))):
                bp = sp.bezier_points[j]
                bp.co = q
                bp.handle_left_type = bp.handle_right_type = 'AUTO'
                bp.radius = r
            o = link(bpy.data.objects.new("Whisker_%d_%d" % (s, i), cu))
            o.data.materials.append(m)
            out.append(o)
        for i in range(3):                                   # brow whiskers
            root, _ = snap(cat, V((0.198, 0.0240 * s, 0.3045)) +
                           V((0.004 * i, 0.0025 * i * s, 0.005 * i)), offset=-0.0015)
            d = V((0.30 + 0.06 * i, 0.72 * s, 0.60 - 0.10 * i)).normalized()
            L = 0.050 + 0.008 * i
            cu = bpy.data.curves.new("Brow", 'CURVE')
            cu.dimensions = '3D'
            cu.bevel_depth = 0.00017
            cu.bevel_resolution = 2
            cu.resolution_u = 8
            sp = cu.splines.new('BEZIER')
            sp.bezier_points.add(2)
            for j, (q, r) in enumerate(((root, 1.0), (root + d * L * 0.55, 0.6),
                                        (root + d * L + V((-0.004, 0, 0.010)), 0.15))):
                bp = sp.bezier_points[j]
                bp.co = q
                bp.handle_left_type = bp.handle_right_type = 'AUTO'
                bp.radius = r
            o = link(bpy.data.objects.new("Brow_%d_%d" % (s, i), cu))
            o.data.materials.append(m)
            out.append(o)
    return out


# ---------------------------------------------------------------------- fur
EYE_L = V((EYE_C.x, EYE_C.y, EYE_C.z))
EYE_R_ = V((EYE_C.x, -EYE_C.y, EYE_C.z))


def region_of(c, mat=0):
    if mat != 0:
        return 'inner'
    if (c - NOSE_TIP).length < 0.048 or min((c - EYE_L).length, (c - EYE_R_).length) < 0.040:
        return 'face'
    if c.z > 0.328:
        return 'ear'
    if c.x > 0.150:
        return 'head'
    if c.x < -0.155:
        return 'fluff'                                   # tail
    if 0.108 < c.x < 0.150 and c.z > 0.185:
        return 'fluff'                                   # neck ruff
    if c.x > 0.085 and c.z < 0.195:
        return 'ruff2'                                   # chest bib
    if c.x < -0.05 and abs(c.y) > 0.042 and c.z < 0.215:
        return 'fluff'                                   # thigh plush
    if c.z < 0.085:
        return 'paw'
    if c.z < 0.150 and abs(c.y) < 0.050 and c.x < 0.105:
        return 'belly'                                  # short fur on the underside
    return 'body'


FUR_LAYOUT = {
    # region: (parents, length, children, clump, kink amplitude, -, -, name)
    'body':  (22000, 0.0135, 14, 0.30, 0.0010, 0, 0, "FurBody"),
    'head':  (11000, 0.0074, 14, 0.24, 0.0008, 0, 0, "FurHead"),
    'ear':   (2500, 0.0042, 10, 0.20, 0.0005, 0, 0, "FurEar"),
    'face':  (4000, 0.0042, 8, 0.18, 0.0005, 0, 0, "FurFace"),
    'paw':   (2600, 0.0055, 9, 0.22, 0.0006, 0, 0, "FurPaw"),
    'belly': (3000, 0.0085, 10, 0.26, 0.0007, 0, 0, "FurBelly"),
    'fluff': (4200, 0.0225, 16, 0.42, 0.0016, 0, 0, "FurFluff"),
    'ruff2': (2400, 0.0175, 14, 0.38, 0.0013, 0, 0, "FurBib"),
    'inner': (1400, 0.0048, 8, 0.18, 0.0006, 0, 0, "FurInnerEar"),
}


def make_emitter(src, name, keep, mat_hair):
    """Copy of the skin mesh; slot 0 is the strand material so that hair renders black."""
    ob = src.copy()
    ob.data = src.data.copy()
    ob.name = name
    link(ob)
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    kill = [f for f in bm.faces if not keep(f)]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    bmesh.ops.delete(bm, geom=loose, context='VERTS')
    for f in bm.faces:                       # face indices shift by one
        f.material_index += 1
    mats = [mat_hair] + list(ob.data.materials)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.materials.clear()
    for m in mats:
        ob.data.materials.append(m)
    return ob


def add_fur(cat, mat_hair, mat_hair_light):
    dens = 0.4 if QUICK else 1.0
    for region, lay in FUR_LAYOUT.items():
        count, length, kids, clump, kink = lay[:5]
        name = lay[-1]
        ob = make_emitter(cat, name,
                          lambda f, r=region: region_of(f.calc_center_median(), f.material_index) == r,
                          mat_hair_light if region == 'inner' else mat_hair)
        if len(ob.data.polygons) == 0:
            bpy.data.objects.remove(ob, do_unlink=True)
            continue
        ob.modifiers.new("Fur", 'PARTICLE_SYSTEM')
        p = ob.particle_systems[-1].settings
        p.type = 'HAIR'
        p.count = max(50, int(count * dens))
        p.hair_length = length
        p.hair_step = 6
        p.render_step = 6
        p.length_random = 0.35
        p.use_advanced_hair = True
        p.use_modifier_stack = True
        p.emit_from = 'FACE'
        p.use_even_distribution = True
        p.distribution = 'JIT'
        p.use_roughness_curve = False
        p.child_type = 'INTERPOLATED'
        p.child_percent = max(2, int(kids * 0.5))
        p.rendered_child_count = max(4, int(kids * dens))
        p.child_length = 1.0
        p.child_length_threshold = 0.0
        p.child_radius = 0.45
        p.clump_factor = clump
        p.clump_shape = 0.15
        p.kink = 'WAVE'
        p.kink_amplitude = kink
        p.kink_frequency = 22.0
        p.kink_shape = -0.3
        p.roughness_endpoint = length * 0.55   # NOTE: metres! large values blow the fur up
        p.roughness_end_shape = 0.5
        p.roughness_1 = length * 0.45
        p.roughness_1_size = length * 0.70
        p.roughness_2 = length * 0.18
        p.roughness_2_size = length * 0.30
        p.brownian_factor = length * 0.35
        p.root_radius = 1.0
        p.tip_radius = 0.20
        p.use_close_tip = False
        p.shape = -0.30
        p.radius_scale = 0.0009 if QUICK else 0.00050    # strand diameter (m)
        # tangent_factor adds METRES to a strand and normal_factor rewrites hair_length,
        # so both are left alone: designed length stays intact.
        p.tangent_factor = 0.0
        p.material = 0
        log("fur", name, len(ob.data.polygons), "faces ->", p.count, "x", p.rendered_child_count)


# --------------------------------------------------------------- scene dress
def build_env():
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=3.0)
    floor = new_obj_from_bm("Floor", bm)
    floor.data.materials.append(mat_simple("FloorMat", (0.055, 0.055, 0.060), rough=0.8, spec=0.2))
    floor.location.z = -0.0015
    w = bpy.data.worlds.new("Studio")
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.014, 0.016, 0.024, 1)
    bg.inputs["Strength"].default_value = 1.0


def add_area(name, loc, target, size, power, color=(1, 1, 1), shape='RECTANGLE'):
    d = bpy.data.lights.new(name, 'AREA')
    d.energy = power
    d.size = size / 2 if shape == 'DISK' else size
    d.shape = shape
    d.color = color
    ob = link(bpy.data.objects.new(name, d))
    ob.location = loc
    ob.rotation_euler = (V(target) - V(loc)).to_track_quat('-Z', 'Y').to_euler()
    return ob


def build_lights():
    add_area("Key", (0.62, -0.58, 0.66), (0.14, 0, 0.24), 0.55, 13.0, (1.0, 0.95, 0.88))
    add_area("Fill", (-0.50, -0.80, 0.40), (0.08, 0, 0.22), 1.10, 3.2, (0.76, 0.84, 1.0))
    add_area("Rim", (-0.52, 0.58, 0.46), (0.00, 0.02, 0.28), 0.70, 11.0, (0.86, 0.92, 1.0))
    add_area("RimTop", (0.10, 0.22, 0.60), (0.16, 0, 0.32), 0.40, 4.5, (1.0, 0.98, 0.95))
    add_area("Glint", (0.50, -0.22, 0.34), (0.216, 0, 0.288), 0.18, 0.7, (1, 1, 1), shape='DISK')


VIEWS = {
    "01_portrait":   (V((0.585, -0.320, 0.335)), V((0.212, 0.004, 0.292)), 78, 4.0),
    "02_full_34":    (V((0.72, -0.66, 0.36)), V((0.055, 0.010, 0.215)), 50, 4.0),
    "03_side":       (V((0.00, -0.85, 0.23)), V((0.00, 0.0, 0.20)), 50, 5.6),
    "04_front":      (V((0.80, -0.16, 0.30)), V((0.06, 0.0, 0.25)), 55, 4.5),
}


def build_camera():
    cam = bpy.data.cameras.new("Cam")
    cam.lens, cam.sensor_width = 85, 36
    ob = link(bpy.data.objects.new("Cam", cam))
    ob.data.dof.use_dof = True
    ob.data.dof.aperture_fstop = 2.6
    bpy.context.scene.camera = ob
    return ob


def setup_render(quick):
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'GPU'
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'METAL'
        prefs.get_devices()
        for d in prefs.devices:
            d.use = (d.type == 'METAL')
    except Exception as ex:
        log("gpu setup:", ex)
    sc.cycles.samples = 32 if quick else 320
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02 if quick else 0.004
    sc.cycles.use_denoising = True
    try:
        sc.cycles.denoiser = 'OPENIMAGEDENOISE'
        sc.cycles.denoising_use_gpu = True
    except Exception:
        pass
    sc.cycles.max_bounces = 10
    sc.cycles.transmission_bounces = 10
    sc.render.resolution_x = 620 if quick else 1200
    sc.render.resolution_y = 780 if quick else 1500
    sc.render.image_settings.file_format = 'PNG'
    for vt, look in (("AgX", "AgX - Medium High Contrast"), ("Filmic", "Medium High Contrast"),
                     ("None", "None")):
        try:
            sc.view_settings.view_transform = vt
            if look:
                sc.view_settings.look = look
            break
        except Exception:
            continue
    sc.view_settings.exposure = -0.15
    log("view transform:", sc.view_settings.view_transform, sc.view_settings.look)


def render_views(quick):
    sc = bpy.context.scene
    cam = sc.camera
    names = ["01_portrait", "02_full_34"] if quick else list(VIEWS)
    for n in names:
        loc, tgt, lens, fstop = VIEWS[n]
        cam.location = loc
        cam.rotation_euler = (tgt - loc).to_track_quat('-Z', 'Y').to_euler()
        cam.data.lens = lens
        cam.data.dof.focus_distance = (tgt - loc).length
        cam.data.dof.aperture_fstop = fstop
        sc.render.filepath = os.path.join(RENDER_DIR, n + ".png")
        log("render", n)
        bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------------- main
def clear_scene_live():
    """Wipe whatever is in the running session without resetting preferences."""
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in list(bpy.data.collections):
        bpy.data.collections.remove(coll)
    for me in list(bpy.data.meshes):
        if me.users == 0:
            bpy.data.meshes.remove(me)
    for op in (bpy.data.metaballs, bpy.data.curves, bpy.data.materials, bpy.data.worlds,
               bpy.data.lights, bpy.data.cameras, bpy.data.particles):
        for db in list(op):
            if db.users == 0:
                op.remove(db)
    for sc in bpy.data.scenes:
        sc.world = None


def main():
    if LIVE:
        clear_scene_live()
    else:
        bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = 'METRIC'
    cat = build_body()

    m_skin = mat_fur_skin()
    m_hair = mat_fur_hair()
    m_hair_light = mat_hair_light()
    m_inner = mat_simple("InnerEar", (0.098, 0.036, 0.036), rough=0.92, spec=0.12)
    cat.data.materials.append(m_skin)
    ears = build_ears(m_skin, m_inner)
    cat = join_objs([cat] + ears, "Cat")
    cat = merge_slots(cat)
    log("slots:", [m.name for m in cat.data.materials])

    mod = cat.modifiers.new("Smooth", 'SMOOTH')
    mod.factor = 0.5
    mod.iterations = 3
    apply_modifiers(cat)
    shade_smooth(cat, 34)
    apply_modifiers(cat)

    eyes, lids = build_eyes(cat)
    for l in lids:                      # fold the lid rims into the furred skin
        l.data.materials[0] = m_skin
    cat = join_objs([cat] + lids, "Cat")
    cat = merge_slots(cat)
    shade_smooth(cat, 34)
    extras = eyes + build_nose(cat) + build_mouth(cat) + build_whiskers(cat)
    log("extras:", len(extras), "slots:", [m.name for m in cat.data.materials])

    add_fur(cat, m_hair, m_hair_light)
    bpy.data.objects.remove(cat, do_unlink=True)          # skin lives in the emitters

    build_env()
    build_lights()
    build_camera()
    setup_render(QUICK)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "black_cat.blend"))
    log("saved blend")
    if not NO_RENDER:
        render_views(QUICK)
    log("all done")


def join_objs(objs, name):
    objs = [o for o in objs if o]
    bpy.ops.object.select_all(action='DESELECT')
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    ob = bpy.context.view_layer.objects.active
    ob.name = name
    return ob


if __name__ == "__main__":
    main()
