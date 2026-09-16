# -*- coding: utf-8 -*-
"""SBIBA - parametric bolted sheet-steel chassis for a two-wheel robot.

Frame (ROS REP-103): X forward, Y left, Z up, origin on the GROUND under the
midpoint of the wheel axle.  So the Z of anything IS its ground clearance.

Running gear: MY1016Z 24 V / 250 W geared brushed motors.  The gearbox output
shaft is NOT coaxial with the motor body - the wheel keys straight onto the
output shaft and the motor body sits sb_motor_offset above it.  The lowest
point of the whole machine is therefore the gearbox boss around that shaft.

Every joint is plane-on-plane with a bolt through it; nothing is welded.
Laser-cut flat blanks, press-brake bends (inner radius = thickness, outer =
2x thickness, concentric), bolted assembly.

Idempotent: re-running rebuilds every component it owns from the current
sb_* parameter values.
"""
import math
import adsk.core, adsk.fusion, traceback

MM = 0.1  # mm -> cm

DEFAULTS = [
    ("sb_track",        500.0, "BAZA: mezhdu centrami koles"),
    ("sb_wheel_dia",    254.0, "koleso 10 dyuymov"),
    ("sb_wheel_w",       85.0, "shirina kolesa"),
    ("sb_wheel_gap",      8.0, "zazor: torec kolesa -> naruzhnaya gran plity"),

    ("sb_motor_offset",  42.0, "os KORPUSA motora vyshe osi vyhodnogo vala"),
    ("sb_gear_boss_d",   88.0, "bobyshka reduktora vokrug vyhodnogo vala"),
    ("sb_boss_clear",     1.0, "zazor plity vokrug bobyshki"),
    ("sb_motor_case_d", 102.0, "korpus motora"),
    ("sb_motor_len",    107.0, "dlina motora vglub ot plity"),
    ("sb_motor_spig_d",  82.8, "posadochnyy bortik"),
    ("sb_motor_shaft_d", 17.0, "val"),
    ("sb_motor_bolt_d",   7.0, "krepezh motora, 4 sht (M6)"),

    ("sb_th_bridge",      3.0, "tolschina: most + plity motora"),
    ("sb_th_side",        2.0, "tolschina: paneli"),
    ("sb_th_cover",       1.0, "tolschina: kryshka"),

    ("sb_body_len",     240.0, "DLINA korpusa vpered/nazad"),
    ("sb_bay_h",         70.0, "VYSOTA vnutrennego otseka"),
    ("sb_deck_gap",       5.0, "zazor: verh motora -> niz nastila. >= tolschiny, pod nim ploschadka opory"),
    ("sb_rail_h",        22.0, "vysota otognutyh vverh reber nastila"),
    ("sb_panel_drop",    40.0, "naskolko paneli svisayut nizhe nastila"),
    ("sb_lip_depth",     22.0, "glubina otbortovki plity pod paneli"),
    ("sb_flange_depth",  14.0, "glubina verhnih otbortovok pod kryshku"),
    ("sb_relief",         6.0, "razmer uglovogo vyreza-reliefa"),

    ("sb_sup_pitch_x",  200.0, "OPORA: baza mezhdu boltami M8 po X"),
    ("sb_sup_pitch_y",  200.0, "OPORA: baza mezhdu boltami M8 po Y"),
    ("sb_sup_x",          0.0, "OPORA: centr ploschadki vpered ot osi koles"),
    ("sb_sup_bolt_d",     9.0, "OPORA: otverstie pod bolt M8"),
    ("sb_sup_edge",      20.0, "OPORA: kraevoy otstup ot centra bolta"),

    ("sb_btn_d",         22.0, "otverstie pod knopku vklyucheniya"),
    ("sb_bolt_m6",        6.6, "otverstie pod M6"),
    ("sb_bolt_m5",        5.5, "otverstie pod M5"),
]

LOG = []


def log(m):
    LOG.append(str(m))


# ---------------------------------------------------------------------- geo --
def tangent_down(px, pz, cx, cz, r):
    """Straight edge running from (px,pz) down-inboard, tangent to the circle
    (cx,cz,r).  Of the two tangents this returns the steeper one - that is the
    one that leaves the motor body inside the plate.
    Returns (vx, vz, tx, tz): unit direction and the tangency point."""
    dx, dz = cx - px, cz - pz
    L = math.hypot(dx, dz)
    if L <= r:
        raise ValueError("shoulder is inside the boss circle")
    a = math.asin(r / L)
    t = math.sqrt(L * L - r * r)
    ux, uz = dx / L, dz / L
    best = None
    for s in (+1.0, -1.0):
        ca, sa = math.cos(s * a), math.sin(s * a)
        vx = ux * ca - uz * sa
        vz = ux * sa + uz * ca
        cand = (vx, vz, px + t * vx, pz + t * vz)
        if best is None or abs(vz) > abs(best[1]):
            best = cand
    return best


class Geo(object):
    def __init__(self, p):
        self.p = p
        self.th_b = p["sb_th_bridge"]
        self.th_s = p["sb_th_side"]
        self.th_c = p["sb_th_cover"]
        self.m5 = p["sb_bolt_m5"]
        self.m6 = p["sb_bolt_m6"]
        self.relief = p["sb_relief"]

        self.wheel_r = p["sb_wheel_dia"] / 2.0
        self.wheel_w = p["sb_wheel_w"]
        self.wheel_y = p["sb_track"] / 2.0
        self.wheel_in = self.wheel_y - self.wheel_w / 2.0

        # --- vertical --------------------------------------------------------
        self.axle_z = self.wheel_r
        self.boss_r = p["sb_gear_boss_d"] / 2.0
        self.cut_r = self.boss_r + p["sb_boss_clear"]
        self.motor_r = p["sb_motor_case_d"] / 2.0
        self.motor_z = self.axle_z + p["sb_motor_offset"]
        self.motor_bot = self.motor_z - self.motor_r
        self.motor_top = self.motor_z + self.motor_r
        self.leg_bot = self.axle_z - self.cut_r
        self.clearance = min(self.leg_bot, self.motor_bot)

        self.deck_bot = self.motor_top + p["sb_deck_gap"]
        self.deck_top = self.deck_bot + self.th_b
        self.rail_h = p["sb_rail_h"]
        self.rail_top = self.deck_top + self.rail_h
        self.cover_bot = self.deck_top + p["sb_bay_h"]   # top face of the flanges
        self.cover_top = self.cover_bot + self.th_c
        self.panel_bot = self.deck_bot - p["sb_panel_drop"]

        # --- lateral (Y) ------------------------------------------------------
        self.mount_y = self.wheel_in - p["sb_wheel_gap"]  # plate outer face
        self.leg_y = self.mount_y - self.th_b             # leg outer = plate inner
        self.leg_in_y = self.leg_y - self.th_b            # flat half width of deck

        # --- fore/aft (X) -----------------------------------------------------
        self.body_hx = p["sb_body_len"] / 2.0             # lip outer
        self.panel_x = self.body_hx - self.th_b           # panel outer
        self.br_hx = self.panel_x - self.th_s             # rail outer / deck edge
        self.rail_in = self.br_hx - self.th_b             # rail inner

        self.lip_depth = p["sb_lip_depth"]
        self.fl_depth = p["sb_flange_depth"]
        # plate top flange stops short of the lips, so the two bend lines never
        # meet; the panel flanges stop short of the plate flanges for the same
        # reason.  Between them they still ring the cover on all four sides.
        self.pl_fl_hx = self.body_hx - self.th_b - self.relief
        # the panel ends short of the plate: the lip's inner bend radius lives
        # in that corner, and the lip covers the gap from outside
        self.panel_hy = self.leg_y - 2 * self.th_b
        self.pn_fl_hy = self.mount_y - self.lip_depth - 2.0

        # --- tapered silhouettes ---------------------------------------------
        self.pl_shld_z = self.panel_bot
        self.pl = tangent_down(self.body_hx, self.pl_shld_z, 0.0, self.axle_z, self.cut_r)
        self.leg_shld_z = self.deck_bot
        self.lg = tangent_down(self.br_hx, self.leg_shld_z, 0.0, self.axle_z, self.cut_r)
        self.pl_clear = self.edge_clear(self.body_hx, self.pl_shld_z, self.pl)
        self.lg_clear = self.edge_clear(self.br_hx, self.leg_shld_z, self.lg)

        # --- motor interface, measured on the real motor ----------------------
        # four M6 through the gearbox flange, offsets from the MOTOR BODY axis
        self.motor_bolts = [(21.50, 37.24), (-21.50, 37.24),
                            (42.32, -12.04), (-42.32, -12.04)]
        self.motor_bolt_d = p["sb_motor_bolt_d"]
        self.motor_case_d = p["sb_motor_case_d"]
        self.motor_len = p["sb_motor_len"]
        self.motor_spig_d = p["sb_motor_spig_d"]
        self.motor_shaft_d = p["sb_motor_shaft_d"]

        # --- support pad -------------------------------------------------------
        self.sup_x = p["sb_sup_x"]
        self.sup_px = p["sb_sup_pitch_x"]
        self.sup_py = p["sb_sup_pitch_y"]
        self.sup_bolt_d = p["sb_sup_bolt_d"]
        self.pad_bot = self.deck_bot - self.th_b
        self.btn_d = p["sb_btn_d"]

        self._bolts()
        e = p["sb_sup_edge"]
        self.sup_hx = min(max(abs(x) for x, y in self.sup_holes + self.bolt_pad_deck) + e,
                          self.rail_in - 1.0)
        self.sup_hy = min(max(abs(y) for x, y in self.sup_holes + self.bolt_pad_deck) + e,
                          self.leg_in_y - 1.0)

    # -- silhouette -----------------------------------------------------------
    def hw(self, sil, hw0, z0, z):
        vx, vz, tx, tz = sil
        if z >= z0:
            return hw0
        if z <= tz:
            rem = self.cut_r ** 2 - (z - self.axle_z) ** 2
            return math.sqrt(rem) if rem > 0 else 0.0
        return hw0 + (z - z0) * (vx / vz)

    def edge_clear(self, hw0, z0, sil):
        """Perpendicular distance from the motor body axis to the tapered edge.
        Must stay above motor_r or the plate cuts into the motor."""
        vx, vz, tx, tz = sil
        return abs((0.0 - hw0) * vz - (self.motor_z - z0) * vx)

    # -- bolt groups -----------------------------------------------------------
    def _bolts(self):
        # A: motor plate -> bridge leg, along Y.  (X, Z), mirrored in X.
        # Must clear the motor body, the gearbox boss and both silhouettes.
        self.bolt_plate_leg = []
        for z in (self.motor_z, self.motor_z + 26.0, self.deck_bot - 12.0):
            lim = min(self.hw(self.pl, self.body_hx, self.pl_shld_z, z),
                      self.hw(self.lg, self.br_hx, self.leg_shld_z, z)) - 11.0
            need = 0.0
            for cz, cr in ((self.motor_z, self.motor_r + 6.0),
                           (self.axle_z, self.cut_r + 7.0)):
                rem = cr ** 2 - (z - cz) ** 2
                if rem > 0:
                    need = max(need, math.sqrt(rem))
            lo, hi = need + 8.0, lim
            if lo > hi:
                continue
            if hi - lo >= 25.0:
                self.bolt_plate_leg.append((lo, z))
                self.bolt_plate_leg.append((hi, z))
            else:
                self.bolt_plate_leg.append(((lo + hi) / 2.0, z))

        # B: panel -> deck rail, along X.  (Y, Z)
        zr = (self.deck_top + self.rail_top) / 2.0
        sp = self.leg_in_y - 30.0
        self.bolt_panel_rail = [(-sp + 2 * sp * i / 6.0, zr) for i in range(7)]

        # C: panel -> motor-plate lip, along X.  (|Y|, Z)
        yc = self.mount_y - self.lip_depth / 2.0
        z0, z1 = self.panel_bot + 16.0, self.cover_bot - 18.0
        self.bolt_panel_lip = [(yc, z0 + (z1 - z0) * i / 2.0) for i in range(3)]

        # D: cover -> panel top flange, along Z.  (|X|, Y)
        xd = self.panel_x - self.fl_depth / 2.0
        sp = self.pn_fl_hy - 14.0
        self.bolt_cover_panel = [(xd, -sp + 2 * sp * i / 6.0) for i in range(7)]

        # E: cover -> motor-plate top flange, along Z.  (X, |Y|)
        ye = self.mount_y - self.fl_depth / 2.0
        sp = self.pl_fl_hx - 14.0
        self.bolt_cover_plate = [(-sp + 2 * sp * i / 4.0, ye) for i in range(5)]

        # F: support pad -> deck, along Z.  (X, Y).  Everything here has to sit
        # on the flat part of the deck - a hole inside a bend zone makes the
        # blank unfoldable - so clamp to the flat rectangle.
        fx = self.rail_in - 2 * self.th_b - 5.0
        fy = self.leg_in_y - 2 * self.th_b - 5.0
        def clamp(x, y):
            return (max(-fx, min(fx, x)), max(-fy, min(fy, y)))
        self.sup_holes = [clamp(self.sup_x + sx * self.sup_px / 2.0,
                                sy * self.sup_py / 2.0)
                          for sx in (-1, 1) for sy in (-1, 1)]
        self.bolt_pad_deck = []
        for sx in (-1, 1):
            for sy in (-1, 1):
                for dx, dy in ((-30.0, -30.0), (-30.0, 30.0)):
                    self.bolt_pad_deck.append(
                        clamp(self.sup_x + sx * (self.sup_px / 2.0 + dx),
                              sy * (self.sup_py / 2.0 + dy)))

    def n_bolts(self):
        return (len(self.bolt_plate_leg) * 2 * 2
                + len(self.bolt_panel_rail) * 2
                + len(self.bolt_panel_lip) * 2 * 2 * 2
                + len(self.bolt_cover_panel) * 2
                + len(self.bolt_cover_plate) * 2
                + len(self.bolt_pad_deck))


# ------------------------------------------------------------------ params --
def get_params(des):
    vals, created = {}, 0
    ups = des.userParameters
    units = des.unitsManager.defaultLengthUnits
    for name, default, comment in DEFAULTS:
        pr = ups.itemByName(name)
        if pr is None:
            pr = ups.add(name, adsk.core.ValueInput.createByString("%g %s" % (default, units)),
                         units, comment)
            created += 1
        vals[name] = pr.value / MM
    return vals, created


# ----------------------------------------------------------------- helpers --
def new_component(root, name):
    for i in range(root.occurrences.count - 1, -1, -1):
        occ = root.occurrences.item(i)
        if occ.component.name == name:
            occ.deleteMe()
    occ = root.occurrences.addNewComponent(adsk.core.Matrix3D.create())
    occ.component.name = name
    return occ.component


def sk_pts(sk, pts):
    return [sk.modelToSketchSpace(adsk.core.Point3D.create(a * MM, b * MM, c * MM))
            for a, b, c in pts]


def rect(sk, p0, p1):
    sp = sk_pts(sk, [p0, p1])
    return sk.sketchCurves.sketchLines.addTwoPointRectangle(sp[0], sp[1])


def circle(sk, centre, dia):
    return sk.sketchCurves.sketchCircles.addByCenterRadius(
        sk_pts(sk, [centre])[0], dia / 2.0 * MM)


def all_profiles(sk):
    col = adsk.core.ObjectCollection.create()
    for p in sk.profiles:
        col.add(p)
    return col


def biggest_profile(sk):
    best, best_a = None, -1.0
    for p in sk.profiles:
        bb = p.boundingBox
        d = (bb.maxPoint.x - bb.minPoint.x, bb.maxPoint.y - bb.minPoint.y,
             bb.maxPoint.z - bb.minPoint.z)
        a = d[0] * d[1] + d[1] * d[2] + d[0] * d[2]
        if a > best_a:
            best, best_a = p, a
    return best


def xy_at(comp, z):
    """Sketch plane parallel to the ground at height z.  Only the XY origin
    plane is offset like this - its normal is unambiguously +Z."""
    if abs(z) < 1e-9:
        return comp.xYConstructionPlane
    inp = comp.constructionPlanes.createInput()
    inp.setByOffset(comp.xYConstructionPlane, adsk.core.ValueInput.createByReal(z * MM))
    return comp.constructionPlanes.add(inp)


def bbox(body):
    b = body.boundingBox
    return (b.minPoint.x / MM, b.maxPoint.x / MM, b.minPoint.y / MM,
            b.maxPoint.y / MM, b.minPoint.z / MM, b.maxPoint.z / MM)


def fmt_bbox(body):
    return "X %6.1f..%6.1f  Y %6.1f..%6.1f  Z %6.1f..%6.1f" % bbox(body)


def translate(comp, bodies, dx, dy, dz):
    if abs(dx) < 1e-9 and abs(dy) < 1e-9 and abs(dz) < 1e-9:
        return
    col = adsk.core.ObjectCollection.create()
    for b in bodies:
        col.add(b)
    mv = comp.features.moveFeatures
    m = adsk.core.Matrix3D.create()
    m.translation = adsk.core.Vector3D.create(dx * MM, dy * MM, dz * MM)
    inp = mv.createInput2(col)
    inp.defineAsFreeMove(m)
    mv.add(inp)


def snap(comp, body, axis, lo):
    """The extrude direction follows the sketch plane normal; rather than guess
    its sign, put the finished body where it belongs."""
    bb = bbox(body)
    cur = {'x': bb[0], 'y': bb[2], 'z': bb[4]}[axis]
    if abs(cur - lo) < 1e-6:
        return
    d = lo - cur
    translate(comp, [body], d if axis == 'x' else 0.0,
              d if axis == 'y' else 0.0, d if axis == 'z' else 0.0)


def rename_bodies(comp, name):
    n = comp.bRepBodies.count
    for i in range(n):
        comp.bRepBodies.item(i).name = name if n == 1 else "%s_%d" % (name, i + 1)


def extrude(comp, profiles, dist, op=None, participants=None):
    ext = comp.features.extrudeFeatures
    inp = ext.createInput(profiles, op or adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    inp.setDistanceExtent(False, adsk.core.ValueInput.createByReal(dist * MM))
    if participants:
        inp.participantBodies = participants
    return ext.add(inp)


def extrude_sym(comp, profiles, total, op=None, participants=None):
    ext = comp.features.extrudeFeatures
    inp = ext.createInput(profiles, op or adsk.fusion.FeatureOperations.NewBodyFeatureOperation)
    inp.setSymmetricExtent(adsk.core.ValueInput.createByReal(total * MM), True)
    if participants:
        inp.participantBodies = participants
    return ext.add(inp)


def merge_all(comp):
    """An extrude with JoinFeatureOperation quietly leaves a separate body when
    the new material only touches its parent across a face - which is exactly
    how a folded flange touches - so boolean them together explicitly."""
    if comp.bRepBodies.count <= 1:
        return comp.bRepBodies.item(0) if comp.bRepBodies.count else None
    target, best = None, -1.0
    for i in range(comp.bRepBodies.count):
        b = comp.bRepBodies.item(i)
        if b.volume > best:
            target, best = b, b.volume
    tools = adsk.core.ObjectCollection.create()
    for i in range(comp.bRepBodies.count):
        b = comp.bRepBodies.item(i)
        if b != target:
            tools.add(b)
    cf = comp.features.combineFeatures
    inp = cf.createInput(target, tools)
    inp.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
    inp.isKeepToolBodies = False
    inp.isNewComponent = False
    cf.add(inp)
    return comp.bRepBodies.item(0)


def straight_edges(body, along, fixed, tol=0.02):
    idx = {'x': 0, 'y': 1, 'z': 2}
    out = []
    for e in body.edges:
        g = e.geometry
        if not isinstance(g, adsk.core.Line3D):
            continue
        a, b = g.startPoint, g.endPoint
        va = (a.x / MM, a.y / MM, a.z / MM)
        vb = (b.x / MM, b.y / MM, b.z / MM)
        if abs(va[idx[along]] - vb[idx[along]]) < 1.0:
            continue
        ok = True
        for k, want in fixed.items():
            i = idx[k]
            if abs(va[i] - vb[i]) > tol or abs(va[i] - want) > tol:
                ok = False
                break
        if ok:
            out.append(e)
    return out


def bend(comp, body, radius, along, fixed, label):
    """One press-brake bend: inner radius = thickness, outer = 2x, concentric."""
    edges = straight_edges(body, along, fixed)
    if not edges:
        log("    bend %-24s r%.0f: no edge" % (label, radius))
        return False
    col = adsk.core.ObjectCollection.create()
    for e in edges:
        col.add(e)
    try:
        fil = comp.features.filletFeatures
        inp = fil.createInput()
        inp.addConstantRadiusEdgeSet(col, adsk.core.ValueInput.createByReal(radius * MM), True)
        inp.isRollingBallCorner = True
        fil.add(inp)
        return True
    except Exception as ex:
        log("    bend %-24s r%.0f FAILED: %s" % (label, radius, str(ex)[:70]))
        return False


def draw_silhouette(sk, g, sil, hw0, z0, z_top):
    """Closed outline in the XZ plane at Y=0: flat top, straight sides down to
    the shoulder, tapered edges tangent to the gearbox boss, then the boss arc
    itself as the bottom edge."""
    vx, vz, tx, tz = sil
    p = sk_pts(sk, [(-hw0, 0.0, z_top), (hw0, 0.0, z_top), (hw0, 0.0, z0),
                    (tx, 0.0, tz), (-tx, 0.0, tz), (-hw0, 0.0, z0)])
    lines = sk.sketchCurves.sketchLines
    for i, j in ((0, 1), (1, 2), (2, 3), (4, 5), (5, 0)):
        lines.addByTwoPoints(p[i], p[j])
    ctr = sk_pts(sk, [(0.0, 0.0, g.axle_z)])[0]
    a0 = math.degrees(math.atan2(tz - g.axle_z, tx))
    sweep = math.radians(-180.0 - 2 * a0)
    arc = sk.sketchCurves.sketchArcs.addByCenterStartSweep(ctr, p[3], sweep)
    if arc.endSketchPoint.geometry.distanceTo(p[4]) > 0.05:
        arc.deleteMe()
        sk.sketchCurves.sketchArcs.addByCenterStartSweep(ctr, p[3], -sweep)


# ----------------------------------------------------------------- geometry --
def build_bridge(root, g):
    """3 mm U-channel: deck between the wheels, legs folded down at both ends
    to carry the motor plates, rails folded up along both long edges so the
    deck works as a channel and the panels have something to bolt to."""
    comp = new_component(root, "MAIN_BRIDGE")

    sk = comp.sketches.add(comp.xYConstructionPlane)
    rect(sk, (-g.br_hx, -g.leg_in_y, 0.0), (g.br_hx, g.leg_in_y, 0.0))
    deck = extrude(comp, sk.profiles.item(0), g.th_b).bodies.item(0)
    snap(comp, deck, 'z', g.deck_bot)

    for sy in (+1.0, -1.0):
        skl = comp.sketches.add(comp.xZConstructionPlane)
        draw_silhouette(skl, g, g.lg, g.br_hx, g.leg_shld_z, g.deck_top)
        leg = extrude(comp, biggest_profile(skl), g.th_b).bodies.item(0)
        snap(comp, leg, 'y', g.leg_in_y if sy > 0 else -g.leg_y)

    sk2 = comp.sketches.add(comp.xZConstructionPlane)
    rect(sk2, (g.rail_in, 0.0, g.deck_top), (g.br_hx, 0.0, g.rail_top))
    rect(sk2, (-g.br_hx, 0.0, g.deck_top), (-g.rail_in, 0.0, g.rail_top))
    extrude_sym(comp, all_profiles(sk2), 2 * g.leg_in_y)
    body = merge_all(comp)

    # Corner relief: the rail bend lines run along Y and the leg bend lines
    # along X.  Where they would cross, the blank must be notched or it is
    # neither foldable on a brake nor unfoldable in Fusion.
    zc = (g.deck_bot - 2 * g.th_b - g.relief + g.rail_top + 5.0) / 2.0
    skr = comp.sketches.add(xy_at(comp, zc))
    for sx in (+1.0, -1.0):
        for sy in (+1.0, -1.0):
            rect(skr, (sx * (g.rail_in - g.relief), sy * (g.leg_in_y - g.relief), zc),
                 (sx * (g.br_hx + 10.0), sy * (g.leg_y + 10.0), zc))
    extrude_sym(comp, all_profiles(skr),
                2 * ((g.rail_top + 5.0) - (g.deck_bot - 2 * g.th_b - g.relief)),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    for sx in (+1.0, -1.0):
        bend(comp, body, g.th_b, 'y', {'x': sx * g.rail_in, 'z': g.deck_top},
             "rail inner X%+.0f" % sx)
        bend(comp, body, 2 * g.th_b, 'y', {'x': sx * g.br_hx, 'z': g.deck_bot},
             "rail outer X%+.0f" % sx)
    for sy in (+1.0, -1.0):
        bend(comp, body, g.th_b, 'x', {'y': sy * g.leg_in_y, 'z': g.deck_bot},
             "leg inner Y%+.0f" % sy)
        bend(comp, body, 2 * g.th_b, 'x', {'y': sy * g.leg_y, 'z': g.deck_top},
             "leg outer Y%+.0f" % sy)

    # joint A plus the motor's own bolts, drilled through both legs
    sk3 = comp.sketches.add(comp.xZConstructionPlane)
    for x, z in g.bolt_plate_leg:
        circle(sk3, (x, 0.0, z), g.m6)
        circle(sk3, (-x, 0.0, z), g.m6)
    for bx, bz in g.motor_bolts:
        circle(sk3, (bx, 0.0, g.motor_z + bz), g.motor_bolt_d)
    circle(sk3, (0.0, 0.0, g.motor_z), g.motor_spig_d + 2.0)
    circle(sk3, (0.0, 0.0, g.axle_z), 2 * g.cut_r)      # gearbox boss passes through
    extrude_sym(comp, all_profiles(sk3), 2 * (g.leg_y + 5.0),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    # joint B: panel -> rail, through both rails
    sk4 = comp.sketches.add(comp.yZConstructionPlane)
    for y, z in g.bolt_panel_rail:
        circle(sk4, (0.0, y, z), g.m5)
    extrude_sym(comp, all_profiles(sk4), 2 * (g.br_hx + 5.0),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    # joint F: the support pad, M5 into the deck and M8 straight through it
    sk5 = comp.sketches.add(comp.xYConstructionPlane)
    for x, y in g.bolt_pad_deck:
        circle(sk5, (x, y, 0.0), g.m5)
    for x, y in g.sup_holes:
        circle(sk5, (x, y, 0.0), g.sup_bolt_d)
    extrude_sym(comp, all_profiles(sk5), 4 * g.deck_top,
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    rename_bodies(comp, "MAIN_BRIDGE")
    log("  %-14s %s" % ("MAIN_BRIDGE", fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_plate(root, g, sy, name):
    """Motor plate: carries the motor, doubles the bridge leg to 6 mm where the
    motor bolts through, and closes the side of the box.  Lips folded inboard
    down both vertical edges give the panels a bolting face; the top edge folds
    inboard for the cover."""
    comp = new_component(root, name)
    y_out = sy * g.mount_y
    y_in = sy * g.leg_y

    sk = comp.sketches.add(comp.xZConstructionPlane)
    draw_silhouette(sk, g, g.pl, g.body_hx, g.pl_shld_z, g.cover_bot)
    plate = extrude(comp, biggest_profile(sk), g.th_b).bodies.item(0)
    snap(comp, plate, 'y', min(y_in, y_out))

    # lips down both vertical edges, built and placed on their own
    for sx in (+1.0, -1.0):
        skl = comp.sketches.add(comp.yZConstructionPlane)
        rect(skl, (0.0, y_out, g.pl_shld_z + g.relief),
             (0.0, y_out - sy * g.lip_depth, g.cover_bot))
        lip = extrude(comp, skl.profiles.item(0), g.th_b).bodies.item(0)
        snap(comp, lip, 'x', (g.body_hx - g.th_b) if sx > 0 else -g.body_hx)

    # top flange for the cover
    skf = comp.sketches.add(xy_at(comp, g.cover_bot - g.th_b))
    rect(skf, (-g.pl_fl_hx, y_out, g.cover_bot - g.th_b),
         (g.pl_fl_hx, y_out - sy * g.fl_depth, g.cover_bot - g.th_b))
    fl = extrude(comp, skf.profiles.item(0), g.th_b).bodies.item(0)
    snap(comp, fl, 'z', g.cover_bot - g.th_b)
    plate = merge_all(comp)

    # Bend reliefs: every bend line that stops part way along an edge needs a
    # notch past it, or the blank cannot be folded on a brake (and Fusion
    # refuses to unfold it).
    skr = comp.sketches.add(comp.xZConstructionPlane)
    for sx in (+1.0, -1.0):
        rect(skr, (sx * (g.body_hx + 2.0), 0.0, g.pl_shld_z + g.relief),
             (sx * (g.body_hx - 2 * g.th_b - 1.0), 0.0, g.pl_shld_z + g.relief - g.th_b))
    extrude_sym(comp, all_profiles(skr), 2 * (g.mount_y + 5.0),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [plate])

    zc = g.cover_bot - g.th_b
    skr2 = comp.sketches.add(xy_at(comp, zc))
    for sx in (+1.0, -1.0):
        rect(skr2, (sx * g.pl_fl_hx, y_out + sy * 2.0, zc),
             (sx * (g.pl_fl_hx + 2 * g.th_b), y_out - sy * (g.fl_depth + 4.0), zc))
    extrude_sym(comp, all_profiles(skr2), 2 * (4 * g.th_b + 2.0),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [plate])

    for sx in (+1.0, -1.0):
        bend(comp, plate, g.th_b, 'z',
             {'x': sx * (g.body_hx - g.th_b), 'y': y_in}, "lip inner X%+.0f" % sx)
        bend(comp, plate, 2 * g.th_b, 'z',
             {'x': sx * g.body_hx, 'y': y_out}, "lip outer X%+.0f" % sx)
    bend(comp, plate, g.th_b, 'x', {'y': y_in, 'z': g.cover_bot - g.th_b}, "top flange in")
    bend(comp, plate, 2 * g.th_b, 'x', {'y': y_out, 'z': g.cover_bot}, "top flange out")

    # motor interface and joint A
    sk3 = comp.sketches.add(comp.xZConstructionPlane)
    for x, z in g.bolt_plate_leg:
        circle(sk3, (x, 0.0, z), g.m6)
        circle(sk3, (-x, 0.0, z), g.m6)
    for bx, bz in g.motor_bolts:
        circle(sk3, (bx, 0.0, g.motor_z + bz), g.motor_bolt_d)
    circle(sk3, (0.0, 0.0, g.motor_z), g.motor_spig_d + 2.0)
    circle(sk3, (0.0, 0.0, g.axle_z), 2 * g.cut_r)      # gearbox boss passes through
    extrude_sym(comp, all_profiles(sk3), 2 * (g.mount_y + 5.0),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [plate])

    # joint C: panel -> lip, drilled along X
    sk4 = comp.sketches.add(comp.yZConstructionPlane)
    for y, z in g.bolt_panel_lip:
        circle(sk4, (0.0, sy * y, z), g.m5)
    extrude_sym(comp, all_profiles(sk4), 2 * (g.body_hx + 5.0),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [plate])

    # joint E: cover -> top flange, drilled along Z
    sk5 = comp.sketches.add(comp.xYConstructionPlane)
    for x, y in g.bolt_cover_plate:
        circle(sk5, (x, sy * y, 0.0), g.m5)
    extrude_sym(comp, all_profiles(sk5), 4 * g.cover_top,
                adsk.fusion.FeatureOperations.CutFeatureOperation, [plate])

    rename_bodies(comp, name)
    log("  %-14s %s" % (name, fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_panel(root, g, sx, name):
    """Fore/aft wall of the electronics bay; the top edge folds inboard so the
    cover has something to sit on."""
    comp = new_component(root, name)
    x_out = sx * g.panel_x
    x_in = sx * g.br_hx

    sk = comp.sketches.add(comp.yZConstructionPlane)
    rect(sk, (0.0, -g.panel_hy, g.panel_bot), (0.0, g.panel_hy, g.cover_bot))
    body = extrude(comp, sk.profiles.item(0), g.th_s).bodies.item(0)
    snap(comp, body, 'x', min(x_in, x_out))

    skf = comp.sketches.add(xy_at(comp, g.cover_bot - g.th_s))
    fy = min(g.pn_fl_hy, g.panel_hy - g.relief)
    rect(skf, (x_out, -fy, g.cover_bot - g.th_s),
         (x_out - sx * g.fl_depth, fy, g.cover_bot - g.th_s))
    fl = extrude(comp, skf.profiles.item(0), g.th_s).bodies.item(0)
    snap(comp, fl, 'z', g.cover_bot - g.th_s)
    body = merge_all(comp)

    bend(comp, body, g.th_s, 'y', {'x': x_in, 'z': g.cover_bot - g.th_s}, "top flange in")
    bend(comp, body, 2 * g.th_s, 'y', {'x': x_out, 'z': g.cover_bot}, "top flange out")

    # joints B and C, drilled along X, plus the power button in the aft panel
    sk3 = comp.sketches.add(comp.yZConstructionPlane)
    for y, z in g.bolt_panel_rail:
        circle(sk3, (0.0, y, z), g.m5)
    for y, z in g.bolt_panel_lip:
        circle(sk3, (0.0, y, z), g.m5)
        circle(sk3, (0.0, -y, z), g.m5)
    if sx < 0:
        circle(sk3, (0.0, 0.0, (g.deck_top + g.cover_bot) / 2.0), g.btn_d)
    extrude_sym(comp, all_profiles(sk3), 2 * (g.body_hx + 5.0),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    # joint D: cover -> top flange, along Z
    sk4 = comp.sketches.add(comp.xYConstructionPlane)
    for x, y in g.bolt_cover_panel:
        circle(sk4, (sx * x, y, 0.0), g.m5)
    extrude_sym(comp, all_profiles(sk4), 4 * g.cover_top,
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    rename_bodies(comp, name)
    log("  %-14s %s" % (name, fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_cover(root, g):
    comp = new_component(root, "COVER_TOP")
    sk = comp.sketches.add(comp.xYConstructionPlane)
    rect(sk, (-g.panel_x, -g.mount_y, 0.0), (g.panel_x, g.mount_y, 0.0))
    body = extrude(comp, sk.profiles.item(0), g.th_c).bodies.item(0)
    snap(comp, body, 'z', g.cover_bot)

    sk2 = comp.sketches.add(comp.xYConstructionPlane)
    for x, y in g.bolt_cover_panel:
        circle(sk2, (x, y, 0.0), g.m5)
        circle(sk2, (-x, y, 0.0), g.m5)
    for x, y in g.bolt_cover_plate:
        circle(sk2, (x, y, 0.0), g.m5)
        circle(sk2, (x, -y, 0.0), g.m5)
    extrude_sym(comp, all_profiles(sk2), 4 * g.cover_top,
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    rename_bodies(comp, "COVER_TOP")
    log("  %-14s %s" % ("COVER_TOP", fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_pad(root, g):
    """Doubler bolted under the deck.  It is the interface the trolley, caster
    or whatever else bolts to, and it doubles the deck to 6 mm exactly where
    that load goes in."""
    comp = new_component(root, "SUPPORT_PAD")
    sk = comp.sketches.add(comp.xYConstructionPlane)
    rect(sk, (g.sup_x - g.sup_hx, -g.sup_hy, 0.0), (g.sup_x + g.sup_hx, g.sup_hy, 0.0))
    body = extrude(comp, sk.profiles.item(0), g.th_b).bodies.item(0)
    snap(comp, body, 'z', g.pad_bot)

    sk2 = comp.sketches.add(comp.xYConstructionPlane)
    for x, y in g.bolt_pad_deck:
        circle(sk2, (x, y, 0.0), g.m5)
    for x, y in g.sup_holes:
        circle(sk2, (x, y, 0.0), g.sup_bolt_d)
    extrude_sym(comp, all_profiles(sk2), 4 * g.deck_top,
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    rename_bodies(comp, "SUPPORT_PAD")
    log("  %-14s %s" % ("SUPPORT_PAD", fmt_bbox(comp.bRepBodies.item(0))))
    return comp


# -------------------------------------------------------------------- refs --
def build_wheel(root, g, sy, name):
    comp = new_component(root, name)
    sk = comp.sketches.add(comp.xZConstructionPlane)
    circle(sk, (0.0, 0.0, g.axle_z), g.wheel_r * 2)
    b = extrude(comp, sk.profiles.item(0), g.wheel_w).bodies.item(0)
    snap(comp, b, 'y', (g.wheel_y - g.wheel_w / 2.0) if sy > 0
         else -(g.wheel_y + g.wheel_w / 2.0))
    rename_bodies(comp, name)
    log("  %-14s %s" % (name, fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_motor(root, g, sy, name):
    comp = new_component(root, name)
    sk = comp.sketches.add(comp.xZConstructionPlane)
    circle(sk, (0.0, 0.0, g.motor_z), g.motor_case_d)
    b = extrude(comp, sk.profiles.item(0), g.motor_len).bodies.item(0)
    snap(comp, b, 'y', (g.leg_in_y - g.motor_len) if sy > 0 else -g.leg_in_y)

    sk2 = comp.sketches.add(comp.xZConstructionPlane)
    circle(sk2, (0.0, 0.0, g.axle_z), g.boss_r * 2)
    b2 = extrude(comp, sk2.profiles.item(0), 20.0).bodies.item(0)
    snap(comp, b2, 'y', (g.leg_in_y - 6.0) if sy > 0 else -(g.leg_in_y + 14.0))

    sk3 = comp.sketches.add(comp.xZConstructionPlane)
    circle(sk3, (0.0, 0.0, g.axle_z), g.motor_shaft_d)
    ln = g.wheel_in + 25.0 - g.leg_y
    b3 = extrude(comp, sk3.profiles.item(0), ln).bodies.item(0)
    snap(comp, b3, 'y', g.leg_y if sy > 0 else -(g.wheel_in + 25.0))

    rename_bodies(comp, name)
    return comp


# --------------------------------------------------------------------- run --
def run(_context):
    app = adsk.core.Application.get()
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        des.designType = adsk.fusion.DesignTypes.ParametricDesignType
        root = des.rootComponent
        p, created = get_params(des)
        g = Geo(p)

        log("params: %d created, %d total" % (created, des.userParameters.count))
        log("--- checks ---")
        log("  plate taper misses the motor axis by %6.1f mm (needs >= %.1f)"
            % (g.pl_clear, g.motor_r))
        log("  leg   taper misses the motor axis by %6.1f mm (needs >= %.1f)"
            % (g.lg_clear, g.motor_r))
        log("  joint A bolts per plate: %d" % (2 * len(g.bolt_plate_leg)))
        log("--- parts ---")
        for fn, args in ((build_bridge, ()),
                         (build_plate, (+1.0, "MOTOR_PLATE_L")),
                         (build_plate, (-1.0, "MOTOR_PLATE_R")),
                         (build_panel, (+1.0, "PANEL_FORE")),
                         (build_panel, (-1.0, "PANEL_AFT")),
                         (build_cover, ()),
                         (build_pad, ()),
                         (build_wheel, (+1.0, "REF_WHEEL_L")),
                         (build_wheel, (-1.0, "REF_WHEEL_R")),
                         (build_motor, (+1.0, "REF_MOTOR_L")),
                         (build_motor, (-1.0, "REF_MOTOR_R"))):
            try:
                fn(root, g, *args)
            except Exception:
                log("  %s FAILED:\n%s" % (getattr(fn, "__name__", "?"),
                                          traceback.format_exc()))

        log("--- geometry ---")
        log("  clearance (lowest point)     %7.1f" % g.clearance)
        log("  overall height               %7.1f" % g.cover_top)
        log("  bay  %.0f x %.0f x %.0f mm"
            % (2 * g.rail_in, 2 * g.leg_in_y, p["sb_bay_h"]))
        log("  bolts total                  %7d" % g.n_bolts())
        print("\n".join(LOG))
    except Exception:
        print("\n".join(LOG))
        print("FAILED\n" + traceback.format_exc())
