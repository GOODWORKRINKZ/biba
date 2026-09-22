# -*- coding: utf-8 -*-
"""BIBA2 chassis generator for Fusion 360  (document: NEW_BIBA).

Laser-cut sheet, folded on a press brake, BOLTED together.  No welding and no
part that could only be welded: every joint is two faces flat against each other
with a hole through both - which is why the panels, bulkheads and motor mounts
all carry folded flanges.

PARAMETRIC.  On the first run the script creates a set of Fusion user parameters
(visible in Modify > Change Parameters, all prefixed "biba_").  On every later
run it READS them back and rebuilds the whole model from them, bolt patterns
included.  So the workflow is:

    change biba_track / biba_bay_h / ... in Fusion  ->  re-run this script

Everything downstream follows: geometry, hole patterns, bends, and the flat
patterns from tools/cad/biba2_flatpatterns.py.

Per part the pipeline is: new component -> sketch -> solid with true bend radii
(inner = thickness, outer = 2x, concentric) -> convertToSheetMetal() in the
flat-pattern script turns it into a real sheet-metal component -> flat pattern
-> DXF with the bend lines on their own layer.  Fusion's API does not expose
FlangeFeatures for creation (the collection is read-only), so bends are modelled
as those concentric fillets, which Fusion then recognises as bends.

World frame (mm), carried over from the measured BIBA2_EXT_BAT model:
    Z  wheel axle.  The two wheels are coaxial, centred at Z = +-track/2.
    X  vertical, -X is UP.  Axle at X = 0, ground at X = +wheel_dia/2.
    Y  direction of travel (fore / aft).
"""

import adsk.core
import adsk.fusion
import math

MM = 0.1  # mm -> cm (Fusion internal units)

# ---------------------------------------------------------------------------
# User parameters: (name, default mm, comment shown in Fusion)
# ---------------------------------------------------------------------------
DEFAULTS = [
    ("biba_track",       506.0, "kolea: rasstoyanie mezhdu centrami koles"),
    ("biba_wheel_dia",   260.0, "diametr kolesa"),
    ("biba_wheel_width", 100.0, "shirina kolesa"),
    ("biba_wheel_gap",     8.0, "zazor ot torca kolesa do plity krepleniya motora"),

    ("biba_bay_h",        70.0, "vnutrennyaya vysota otseka elektroniki"),
    ("biba_bay_hw",       70.0, "vnutrennyaya polushirina otseka (mezhdu rebrami)"),
    ("biba_deck_h",       95.0, "ot osi koles vverh do niza nastila mosta"),
    ("biba_leg_gap",      12.5, "ot osi koles vverh do niza nog mosta"),
    ("biba_rail_h",       22.0, "vysota otognutyh vverh reber nastila"),

    ("biba_th_bridge",     3.0, "tolschina: most i krepleniya motora"),
    ("biba_th_side",       2.0, "tolschina: bokovye paneli i perebonki"),
    ("biba_th_cover",      1.0, "tolschina: verhnyaya kryshka"),

    ("biba_bore_r",       44.0, "radius rastochki/dugi u osi kolesa (izmereno D88)"),
    ("biba_motor_offset", 42.00, "IZMERENO: os motora vyshe osi kolesa"),
    ("biba_motor_case_d", 102.00, "IZMERENO: korpus reduktora"),
    ("biba_motor_shaft_hole", 21.00, "IZMERENO: prohod vala v plite"),
    ("biba_motor_bolt_d",  7.00, "IZMERENO: krepezh motora, 4 sht"),
    ("biba_slant_deg", 18.0849, "IZMERENO: ugol skosa nizhney kromki plity"),
    ("biba_slant_dist",  40.87, "IZMERENO: rasstoyanie ot osi kolesa do linii skosa"),
    ("biba_tip_facet",    5.00, "IZMERENO: faska na noske plity"),
    ("biba_lip_depth",    22.0, "glubina otbortovki plity krepleniya"),
    ("biba_panel_drop",   42.0, "naskolko paneli svisayut nizhe nastila"),

    ("biba_motor_len",   107.0, "dlina motora s reduktorom (REF)"),
    ("biba_motor_body_d", 101.8, "diametr korpusa reduktora (REF)"),
    ("biba_motor_spig_d",  82.8, "diametr posadochnogo bortika (REF)"),
    ("biba_motor_shaft_d", 17.0, "diametr vala (REF)"),

    ("biba_dock_hw",      52.0, "SCEPKA: polushirina gnezda u ustya"),
    ("biba_dock_h",       60.0, "SCEPKA: vnutrennyaya vysota gnezda"),
    ("biba_dock_depth",   90.0, "SCEPKA: glubina zahoda yazyka"),
    ("biba_dock_taper",    0.0, "SCEPKA: konus gnezda, grad. 0 = pryamoe gnezdo!"
                                " nenulevoy konus lomaet razvertku, klin delaetsya na yazyke"),
    ("biba_dock_slack",    0.5, "SCEPKA: naklon verhney grani yazyka - vybiraet lyuft"),
    ("biba_dock_ramp",    20.0, "SCEPKA: gde yazyk uporno prizhat k nastilu, vglub ot ustya"),
    ("biba_dock_clear",    0.2, "SCEPKA: zazor yazyk/gnezdo na storonu"),
    ("biba_dock_pin_d",   12.0, "SCEPKA: diametr stopornogo shtyrya"),
    ("biba_dock_pin_in",  45.0, "SCEPKA: shtyr, vglub ot ustya"),
    ("biba_dock_flange",  14.0, "SCEPKA: shirina polki gnezda pod bolty v nastil"),

    ("biba_bolt_m6",       6.6, "otverstie pod M6 (kreplenie motornoy plity)"),
    ("biba_bolt_m5",       5.5, "otverstie pod M5 (vsyo ostalnoe)"),
]

OWNED = ["MAIN_BRIDGE", "MOTOR_MOUNT_R", "MOTOR_MOUNT_L", "DOCK_SOCKET",
         "REF_TONGUE", "REF_DOCK_PIN",
         "PANEL_FORE", "PANEL_AFT", "COVER_TOP",
         "BULKHEAD_R", "BULKHEAD_L",
         "GUSSET_RF", "GUSSET_RA", "GUSSET_LF", "GUSSET_LA",   # only so re-runs delete them
         "REF_WHEEL_R", "REF_WHEEL_L", "REF_MOTOR_R", "REF_MOTOR_L",
         "REF_MAINBOARD"]

LOG = []


def log(m):
    LOG.append(str(m))


# ---------------------------------------------------------------------- geo --
class Geo(object):
    """Everything the model needs, derived from the user parameters."""

    def __init__(self, p):
        self.th_b = p["biba_th_bridge"]
        self.th_s = p["biba_th_side"]
        self.th_c = p["biba_th_cover"]

        self.wheel_d = p["biba_wheel_dia"]
        self.wheel_w = p["biba_wheel_width"]
        self.wheel_z = p["biba_track"] / 2.0
        self.wheel_in = self.wheel_z - self.wheel_w / 2.0

        # mount plate sits just inboard of the wheel
        self.mount_z = self.wheel_in - p["biba_wheel_gap"]      # outer face of the leg
        self.leg_in_z = self.mount_z - self.th_b
        self.cover_z = self.mount_z + self.th_b
        # panels stop one thickness short of the mount plate: the lip's bend
        # radius lives in that corner, and the lip covers the gap from outside
        self.panel_z = self.mount_z - self.th_b

        # verticals (-X is up)
        self.deck_bot = -p["biba_deck_h"]
        self.deck_top = self.deck_bot - self.th_b
        self.leg_bot = -p["biba_leg_gap"]
        self.rail_h = p["biba_rail_h"]
        self.rail_top = self.deck_top - self.rail_h
        self.cover_x = self.deck_top - p["biba_bay_h"]          # underside of the cover
        self.mount_top = self.cover_x
        # the panel repeats the bridge silhouette: it runs from the cover down to
        # the bottom of the legs, and the bridge carries a folded flange over
        # that whole outline for it to bolt to
        self.panel_bot = self.leg_bot

        # Y stack outwards: rails | deck edge | panels | mount lips | plate edge
        self.rail_in = p["biba_bay_hw"]
        self.br_hw = self.rail_in + self.th_b
        self.panel_y = self.br_hw + self.th_s
        self.body_hw = self.panel_y + self.th_b

        self.rail_z = self.leg_in_z
        self.relief_y = self.br_hw - 8.0
        self.relief_z = self.leg_in_z - 7.0

        # --- tow coupling: wedge socket under the deck, cross pin in double shear
        self.dock_hw = p["biba_dock_hw"]
        self.dock_h = p["biba_dock_h"]
        self.dock_depth = p["biba_dock_depth"]
        self.dock_taper = math.radians(p["biba_dock_taper"])
        self.dock_pin_d = p["biba_dock_pin_d"]
        self.dock_flange = p["biba_dock_flange"]
        self.dock_y0 = self.panel_y                          # mouth, flush with the skin
        self.dock_y1 = self.dock_y0 - self.dock_depth        # inner end
        self.dock_hw1 = self.dock_hw_at(self.dock_y1)
        self.dock_floor = self.deck_bot + self.dock_h        # cavity floor
        self.dock_web = self.dock_floor + self.th_b
        self.dock_fl_x = self.deck_bot + self.th_b
        self.dock_pin_x = self.deck_bot + self.dock_h / 2.0
        self.dock_pin_y = self.dock_y0 - p["biba_dock_pin_in"]
        self.dock_wall_t = self.th_b / math.cos(self.dock_taper)
        self.dock_slack = p["biba_dock_slack"]
        self.dock_ramp = p["biba_dock_ramp"]
        self.dock_clear = p["biba_dock_clear"]
        self.dock_out_hw = self.dock_hw + self.dock_wall_t + self.dock_flange
        # bolts up through the socket flanges into the deck: (Y, |Z|)
        self.bolt_dock_deck = [
            (y, self.dock_hw_at(y) + self.dock_wall_t + self.dock_flange / 2.0)
            for y in (self.dock_y0 - 25.0, self.dock_y0 - 70.0)]

        self.bore_r = p["biba_bore_r"]
        self.lip_depth = p["biba_lip_depth"]

        # --- measured motor interface (see docs/cad/BIBA2_CHASSIS_V2.md) -----
        # The motor is NOT coaxial with the wheel: its axis sits motor_offset
        # above the wheel axis and it drives the wheel across that gap.
        self.motor_offset = p["biba_motor_offset"]
        self.motor_cx = -self.motor_offset          # motor axis, X (-X is up)
        self.motor_case_d = p["biba_motor_case_d"]
        self.shaft_hole_d = p["biba_motor_shaft_hole"]
        self.motor_bolt_d = p["biba_motor_bolt_d"]
        # bolt centres as measured, relative to the motor axis: two on PCD 86,
        # two on PCD 88
        self.motor_bolts = [(self.motor_cx - 37.24, 21.50),
                            (self.motor_cx - 37.24, -21.50),
                            (self.motor_cx + 12.04, 42.32),
                            (self.motor_cx + 12.04, -42.32)]

        # --- measured plate outline ----------------------------------------
        # slanted lower edge, then a short facet, then the arc round the axle
        sl = math.radians(p["biba_slant_deg"])
        self.slant_nx = math.sin(sl)
        self.slant_ny = math.cos(sl)
        self.slant_d = p["biba_slant_dist"]
        self.tip_facet = p["biba_tip_facet"]
        # where the facet line cuts the arc (take the solution up on the plate)
        dd = self.slant_d - self.tip_facet
        rem = self.bore_r ** 2 - dd ** 2
        h = math.sqrt(rem) if rem > 0 else 0.0
        self.arc_x = dd * self.slant_nx - h * self.slant_ny
        self.arc_y = dd * self.slant_ny + h * self.slant_nx
        self.tip_x = self.arc_x + self.tip_facet * self.slant_nx
        self.tip_y = self.arc_y + self.tip_facet * self.slant_ny
        self.arc_a = math.degrees(math.atan2(self.arc_y, self.arc_x))
        # the straight sides end where the slant reaches full width
        self.mount_shld_x = (self.slant_d - self.slant_ny * self.body_hw) / self.slant_nx
        self.lip_end_x = self.mount_shld_x - 10.0
        self.lip_relief_w = 2 * self.th_b        # notch at the lip's lower end

        # panel top flange, bulkheads
        self.pflange_x = self.cover_x + self.th_s
        self.pflange_in = self.br_hw - 12.0
        self.bulk_z = self.mount_z - 20.0
        self.bulk_in_z = self.bulk_z - self.th_s
        # keep clear of the panel top-flange bend radius
        self.bulk_top_x = self.pflange_x + self.th_s + 1.0
        self.bulk_step_x = self.rail_top - 4.0
        self.bulk_narrow = self.rail_in - 4.0
        self.bflange_d = 12.0

        # free volume the electronics get
        self.board_h = p["biba_bay_h"] - 5.0
        self.board_hw = self.rail_in - 4.0
        self.board_z = self.bulk_in_z - self.bflange_d - 3.0

        self.m6 = p["biba_bolt_m6"]
        self.m5 = p["biba_bolt_m5"]

        self.motor_len = p["biba_motor_len"]
        self.motor_shaft_d = p["biba_motor_shaft_d"]

        self._bolts()

    # -- bolt patterns, all derived so they follow the parameters -------------
    def dock_hw_at(self, y):
        """Half width of the socket cavity at depth y - it converges inward, so
        the tongue wedges and cannot rattle."""
        return self.dock_hw - math.tan(self.dock_taper) * (self.dock_y0 - y)

    def slant_y(self, x):
        """Y of the mount plate's slanted lower edge at height x."""
        return (self.slant_d - self.slant_nx * x) / self.slant_ny

    def _bolts(self):
        leg_h = self.deck_bot - self.leg_bot          # negative magnitude
        # A: motor mount -> bridge leg, along Z, (X, |Y|)
        self.bolt_mount_leg = []
        for frac in (0.06, 0.30, 0.55):
            x = self.deck_bot - leg_h * frac
            y = min(self.slant_y(x) - 10.0, self.br_hw - 11.0)
            r_min = self.bore_r + 8.0
            if abs(x) < r_min:
                y = max(y, math.sqrt(r_min ** 2 - x ** 2))
            # never land on top of a motor bolt
            if min(math.hypot(x - bx, y - abs(by)) for bx, by in self.motor_bolts) < 12.0:
                continue
            if y > 20.0:
                self.bolt_mount_leg.append((x, y))

        # B: panel -> deck rail, along Y, (X, Z)
        xr = (self.rail_top + self.deck_top) / 2.0
        span = self.rail_z - 32.0
        self.bolt_panel_rail = [(xr, -span + 2 * span * i / 6.0) for i in range(7)]

        # B2: panel -> leg flange, along Y, (X, |Z|)
        zl = self.leg_in_z - self.rail_h / 2.0
        self.bolt_panel_leg = [(self.deck_bot - leg_h * f, zl) for f in (0.20, 0.50, 0.80)]

        # C: panel -> mount lip, along Y, (X, |Z|)
        zc = self.mount_z - self.lip_depth / 2.0   # clear of the lip's bend zone
        self.bolt_panel_lip = [(self.mount_top + 0.25 * (self.lip_end_x - self.mount_top), zc),
                               (self.mount_top + 0.75 * (self.lip_end_x - self.mount_top), zc)]

        # D: cover -> panel top flange, along X, (|Y|, Z)
        yd = (self.br_hw + self.pflange_in) / 2.0
        spd = self.mount_z - 30.0
        self.bolt_cover_panel = [(yd, -spd + 2 * spd * i / 6.0) for i in range(7)]

        # E: bulkhead side flange -> panel, along Y, (X, |Z|)
        ze = self.bulk_in_z - self.bflange_d / 2.0
        self.bolt_bulk_panel = [
            (self.bulk_top_x + 0.30 * (self.bulk_step_x - self.bulk_top_x), ze),
            (self.bulk_top_x + 0.75 * (self.bulk_step_x - self.bulk_top_x), ze)]

    def n_bolts(self):
        return (len(self.bolt_mount_leg) * 2 * 2
                + len(self.bolt_panel_leg) * 2 * 2 * 2
                + len(self.bolt_panel_rail) * 2
                + len(self.bolt_panel_lip) * 2 * 2 * 2
                + len(self.bolt_cover_panel) * 2
                + len(self.bolt_bulk_panel) * 2 * 2 * 2)


def get_params(des):
    """Create the user parameters on first run; read them back on every run."""
    vals = {}
    created = 0
    for name, default, comment in DEFAULTS:
        p = des.userParameters.itemByName(name)
        if p is None:
            p = des.userParameters.add(
                name, adsk.core.ValueInput.createByString("%g mm" % default), "mm", comment)
            created += 1
        vals[name] = p.value / MM
    log("  %d parameters (%d created, %d already set by you)"
        % (len(DEFAULTS), created, len(DEFAULTS) - created))
    return vals


# ------------------------------------------------------------------ helpers --
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


def polyline(sk, pts):
    sp = sk_pts(sk, pts)
    lines = sk.sketchCurves.sketchLines
    for i in range(len(sp)):
        lines.addByTwoPoints(sp[i], sp[(i + 1) % len(sp)])


def rect(sk, p0, p1):
    sp = sk_pts(sk, [p0, p1])
    return sk.sketchCurves.sketchLines.addTwoPointRectangle(sp[0], sp[1])


def circle(sk, centre, dia):
    return sk.sketchCurves.sketchCircles.addByCenterRadius(sk_pts(sk, [centre])[0], dia / 2.0 * MM)


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


def plane_at(comp, base, offset_mm):
    if abs(offset_mm) < 1e-9:
        return base
    inp = comp.constructionPlanes.createInput()
    inp.setByOffset(base, adsk.core.ValueInput.createByReal(offset_mm * MM))
    return comp.constructionPlanes.add(inp)


def bbox(body):
    b = body.boundingBox
    return (b.minPoint.x / MM, b.maxPoint.x / MM, b.minPoint.y / MM,
            b.maxPoint.y / MM, b.minPoint.z / MM, b.maxPoint.z / MM)


def fmt_bbox(body):
    return "X %7.1f..%7.1f  Y %6.1f..%6.1f  Z %6.1f..%6.1f" % bbox(body)


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
    """Extrude direction follows the sketch plane normal; rather than guess the
    sign, put the finished body where it belongs."""
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
    """Collapse a component down to one body.  An extrude with JoinFeature-
    Operation quietly leaves a separate body when the new material only touches
    the parent across a face, which is exactly what a folded flange does - so
    boolean them together explicitly instead of trusting the extrude."""
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


def join_body(comp, target, tool):
    """Boolean-join a body that had to be built and positioned on its own."""
    tools = adsk.core.ObjectCollection.create()
    tools.add(tool)
    cf = comp.features.combineFeatures
    inp = cf.createInput(target, tools)
    inp.operation = adsk.fusion.FeatureOperations.JoinFeatureOperation
    inp.isKeepToolBodies = False
    inp.isNewComponent = False
    return cf.add(inp)


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


def bend_at(comp, body, radius, pt, label, tol=2.0):
    """Like bend(), but selects the edge by its midpoint - the tow socket tapers,
    so its bend lines are not parallel to any axis."""
    px, py, pz = pt
    edges = []
    for e in body.edges:
        gg = e.geometry
        if not isinstance(gg, adsk.core.Line3D):
            continue
        a, b = gg.startPoint, gg.endPoint
        m = ((a.x + b.x) / 2 / MM, (a.y + b.y) / 2 / MM, (a.z + b.z) / 2 / MM)
        if abs(m[0] - px) < tol and abs(m[1] - py) < tol and abs(m[2] - pz) < tol:
            edges.append(e)
    if not edges:
        log("    bend %-22s r%.0f: no edge at (%.1f, %.1f, %.1f)"
            % (label, radius, px, py, pz))
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
        log("    bend %-22s r%.0f FAILED: %s" % (label, radius, str(ex)[:80]))
        return False


def chamfer_at(comp, body, dist, pt, label, tol=2.0):
    px, py, pz = pt
    col = adsk.core.ObjectCollection.create()
    for e in body.edges:
        gg = e.geometry
        if not isinstance(gg, adsk.core.Line3D):
            continue
        a, b = gg.startPoint, gg.endPoint
        m = ((a.x + b.x) / 2 / MM, (a.y + b.y) / 2 / MM, (a.z + b.z) / 2 / MM)
        if abs(m[0] - px) < tol and abs(m[1] - py) < tol and abs(m[2] - pz) < tol:
            col.add(e)
    if col.count == 0:
        log("    chamfer %-18s: no edge" % label)
        return
    try:
        ch = comp.features.chamferFeatures
        inp = ch.createInput2()
        inp.chamferEdgeSets.addEqualDistanceChamferEdgeSet(
            col, adsk.core.ValueInput.createByReal(dist * MM), False)
        ch.add(inp)
    except Exception as ex:
        log("    chamfer %-18s FAILED: %s" % (label, str(ex)[:70]))


def bend(comp, body, radius, along, fixed, label):
    """One press-brake bend: inner radius = thickness, outer = 2x, concentric."""
    edges = straight_edges(body, along, fixed)
    if not edges:
        log("    bend %-20s r%.0f: no edge" % (label, radius))
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
        log("    bend %-20s r%.0f FAILED: %s" % (label, radius, str(ex)[:80]))
        return False


# -------------------------------------------------------------- sheet rules --
def ensure_rules(des, g):
    """A brand-new document has no sheet-metal data root, so the design rule
    collection throws until something seeds it - fall back to the library."""
    try:
        have = dict((r.name, r) for r in des.designSheetMetalRules)
    except Exception:
        have = {}
    src = None
    for r in have.values():
        src = r
        break
    if src is None:
        lib = des.librarySheetMetalRules
        for i in range(lib.count):
            if lib.item(i).name == "Steel (mm)":
                src = lib.item(i)
        if src is None:
            src = lib.item(0)
    for th in sorted(set([g.th_b, g.th_s, g.th_c]), reverse=True):
        nm = "BIBA Steel %gmm" % th
        r = have.get(nm)
        if r is None:
            r = None
            for attempt in (1, 2):
                try:
                    r = des.designSheetMetalRules.addByCopy(src, nm)
                    break
                except Exception as e:
                    if attempt == 2:
                        log("  rule %-16s FAILED: %s" % (nm, str(e)[:70]))
            if r is None:
                continue
        try:
            r.thickness.value = th * MM
            r.bendRadius.expression = "%g mm" % th
            log("  rule %-16s = %.1f mm, inner bend radius %.1f mm" % (nm, th, th))
        except Exception as e:
            log("  rule %-16s thickness: %s" % (nm, str(e)[:70]))


# ----------------------------------------------------------------- geometry --
def build_bridge(root, g):
    """3 mm U-section: deck from wheel to wheel, legs folded down at both ends
    for the motor mounts, rails folded up along both long edges so the deck
    works as a channel instead of a flat plate."""
    comp = new_component(root, "MAIN_BRIDGE")

    sk = comp.sketches.add(comp.xZConstructionPlane)
    polyline(sk, [(g.deck_top, 0.0, -g.mount_z), (g.deck_top, 0.0, g.mount_z),
                  (g.leg_bot, 0.0, g.mount_z), (g.leg_bot, 0.0, g.leg_in_z),
                  (g.deck_bot, 0.0, g.leg_in_z), (g.deck_bot, 0.0, -g.leg_in_z),
                  (g.leg_bot, 0.0, -g.leg_in_z), (g.leg_bot, 0.0, -g.mount_z)])
    body = extrude_sym(comp, sk.profiles.item(0), 2 * g.br_hw).bodies.item(0)

    sk2 = comp.sketches.add(comp.xYConstructionPlane)
    rect(sk2, (g.rail_top, g.rail_in, 0.0), (g.deck_top, g.br_hw, 0.0))
    rect(sk2, (g.rail_top, -g.br_hw, 0.0), (g.deck_top, -g.rail_in, 0.0))
    extrude_sym(comp, all_profiles(sk2), 2 * g.rail_z)

    # The same folded edge continues down both legs, so the bolting flange runs
    # along the entire U outline and the panel has something to grab everywhere.
    for sz in (+1.0, -1.0):
        for sy in (+1.0, -1.0):
            skl = comp.sketches.add(comp.xZConstructionPlane)
            # starts where the corner relief ends, so the flange never butts
            # into the deck: that contact is not a bend and Fusion refuses to
            # unfold it (SM_NON_SHEET_METAL_EDGE)
            rect(skl, (g.deck_bot + 5.0, 0.0, sz * g.leg_in_z),
                 (g.leg_bot, 0.0, sz * (g.leg_in_z - g.rail_h)))
            fl = extrude(comp, skl.profiles.item(0), g.th_b).bodies.item(0)
            snap(comp, fl, 'y', g.rail_in if sy > 0 else -g.br_hw)
    body = merge_all(comp)

    # Corner relief: the leg bend lines run along Y and the rail bend lines
    # along Z; where they would cross, the blank must be notched or it is
    # neither foldable on a brake nor unfoldable in Fusion.
    for sz in (+1.0, -1.0):
        skr = comp.sketches.add(plane_at(comp, comp.xYConstructionPlane, sz * g.relief_z))
        rect(skr, (g.rail_top - 5.0, g.relief_y, sz * g.relief_z),
             (g.deck_bot + 5.0, g.br_hw + 5.0, sz * g.relief_z))
        rect(skr, (g.rail_top - 5.0, -(g.br_hw + 5.0), sz * g.relief_z),
             (g.deck_bot + 5.0, -g.relief_y, sz * g.relief_z))
        extrude(comp, all_profiles(skr), sz * 25.0,
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    for sy in (+1.0, -1.0):
        bend(comp, body, g.th_b, 'z', {'x': g.deck_top, 'y': sy * g.rail_in}, "rail inner Y%+.0f" % sy)
        bend(comp, body, 2 * g.th_b, 'z', {'x': g.deck_bot, 'y': sy * g.br_hw}, "rail outer Y%+.0f" % sy)
    for sz in (+1.0, -1.0):
        for sy in (+1.0, -1.0):
            bend(comp, body, g.th_b, 'x',
                 {'y': sy * g.rail_in, 'z': sz * g.leg_in_z}, "legflange in Z%+.0fY%+.0f" % (sz, sy))
            bend(comp, body, 2 * g.th_b, 'x',
                 {'y': sy * g.br_hw, 'z': sz * g.mount_z}, "legflange out Z%+.0fY%+.0f" % (sz, sy))
    for sz in (+1.0, -1.0):
        bend(comp, body, g.th_b, 'y', {'x': g.deck_bot, 'z': sz * g.leg_in_z}, "leg inner Z%+.0f" % sz)
        bend(comp, body, 2 * g.th_b, 'y', {'x': g.deck_top, 'z': sz * g.mount_z}, "leg outer Z%+.0f" % sz)

    # motor clearance through both legs + joint A (mount -> leg)
    sk3 = comp.sketches.add(comp.xYConstructionPlane)
    circle(sk3, (0.0, 0.0, 0.0), 2 * g.bore_r)          # axle opening
    for x, y in g.bolt_mount_leg:
        circle(sk3, (x, y, 0.0), g.m6)
        circle(sk3, (x, -y, 0.0), g.m6)
    circle(sk3, (g.motor_cx, 0.0, 0.0), g.shaft_hole_d)  # measured: shaft
    for x, y in g.motor_bolts:                           # measured: 4 motor bolts
        circle(sk3, (x, y, 0.0), g.motor_bolt_d)
    extrude_sym(comp, all_profiles(sk3), 2 * (g.mount_z + 5),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    # joint B (panel -> rail), drilled through both rails
    sk4 = comp.sketches.add(comp.xZConstructionPlane)
    for x, z in g.bolt_panel_rail:
        circle(sk4, (x, 0.0, z), g.m5)
    for x, z in g.bolt_panel_leg:
        circle(sk4, (x, 0.0, z), g.m5)
        circle(sk4, (x, 0.0, -z), g.m5)
    extrude_sym(comp, all_profiles(sk4), 2 * (g.br_hw + 5),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    # tow socket bolts up into the deck
    sk5 = comp.sketches.add(comp.yZConstructionPlane)
    for y, z in g.bolt_dock_deck:
        circle(sk5, (0.0, y, z), g.m5)
        circle(sk5, (0.0, y, -z), g.m5)
    extrude_sym(comp, all_profiles(sk5), 2 * (abs(g.deck_bot) + 10),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    rename_bodies(comp, "MAIN_BRIDGE")
    log("  %-14s %s" % ("MAIN_BRIDGE", fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_mount(root, g, sz, name):
    """End plate that carries the motor and closes the end of the box.  Lips
    folded down both straight sides give the panels a bolting face; the lower
    edge is an open arc that clears the motor."""
    comp = new_component(root, name)
    z0 = sz * g.mount_z
    zo = sz * (g.mount_z + g.th_b)
    pl = plane_at(comp, comp.xYConstructionPlane, z0)

    sk = comp.sketches.add(pl)
    p = sk_pts(sk, [(g.mount_top, g.body_hw, z0), (g.mount_top, -g.body_hw, z0),
                    (g.mount_shld_x, -g.body_hw, z0), (g.tip_x, -g.tip_y, z0),
                    (g.arc_x, -g.arc_y, z0), (g.arc_x, g.arc_y, z0),
                    (g.tip_x, g.tip_y, z0), (g.mount_shld_x, g.body_hw, z0)])
    lines = sk.sketchCurves.sketchLines
    for i, j in ((0, 1), (1, 2), (2, 3), (3, 4), (5, 6), (6, 7), (7, 0)):
        lines.addByTwoPoints(p[i], p[j])
    ctr = sk_pts(sk, [(0.0, 0.0, z0)])[0]
    sweep = math.radians(2 * (180.0 - g.arc_a))
    arc = sk.sketchCurves.sketchArcs.addByCenterStartSweep(ctr, p[5], sweep)
    if arc.endSketchPoint.geometry.distanceTo(p[4]) > 0.05:
        arc.deleteMe()
        sk.sketchCurves.sketchArcs.addByCenterStartSweep(ctr, p[5], -sweep)

    plate = extrude(comp, biggest_profile(sk), g.th_b).bodies.item(0)
    snap(comp, plate, 'z', min(z0, zo))

    # lips folded inboard; they stop short of the shoulder and that gap is
    # their bend relief
    sk2 = comp.sketches.add(pl)
    for s in (1.0, -1.0):
        rect(sk2, (g.mount_top, s * g.body_hw, z0), (g.lip_end_x, s * (g.body_hw - g.th_b), z0))
    extrude(comp, all_profiles(sk2), -sz * g.lip_depth)
    plate = merge_all(comp)

    # Bend relief: each lip stops part-way along a straight edge, so the blank
    # needs a notch cut past the bend line at that end or it will not fold on a
    # brake (and Fusion refuses to unfold it).
    skr = comp.sketches.add(pl)
    for s in (1.0, -1.0):
        rect(skr, (g.lip_end_x, s * (g.body_hw + 2.0), z0),
             (g.lip_end_x + g.lip_relief_w, s * (g.body_hw - 2 * g.th_b - 1.0), z0))
    extrude_sym(comp, all_profiles(skr), 4 * (g.lip_depth + g.th_b),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [plate])

    for sy in (+1.0, -1.0):
        bend(comp, plate, g.th_b, 'x',
             {'y': sy * (g.body_hw - g.th_b), 'z': z0}, "lip inner Y%+.0f" % sy)
        bend(comp, plate, 2 * g.th_b, 'x', {'y': sy * g.body_hw, 'z': zo}, "lip outer Y%+.0f" % sy)

    sk3 = comp.sketches.add(pl)
    for x, y in g.bolt_mount_leg:                       # joint A: mount -> leg
        circle(sk3, (x, y, z0), g.m6)
        circle(sk3, (x, -y, z0), g.m6)
    circle(sk3, (g.motor_cx, 0.0, z0), g.shaft_hole_d)  # measured: shaft
    for x, y in g.motor_bolts:                          # measured: 4 motor bolts
        circle(sk3, (x, y, z0), g.motor_bolt_d)
    extrude_sym(comp, all_profiles(sk3), 6 * g.th_b,
                adsk.fusion.FeatureOperations.CutFeatureOperation, [plate])

    sk4 = comp.sketches.add(comp.xZConstructionPlane)
    for x, z in g.bolt_panel_lip:
        circle(sk4, (x, 0.0, sz * z), g.m5)
    extrude_sym(comp, all_profiles(sk4), 2 * (g.body_hw + 5),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [plate])

    rename_bodies(comp, name)
    log("  %-14s %s" % (name, fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_panel(root, g, sy, name):
    """Side wall of the electronics bay; the top edge folds inboard so the cover
    has something to sit on and bolt into."""
    comp = new_component(root, name)
    y_in = sy * g.br_hw
    y_out = sy * g.panel_y

    sk = comp.sketches.add(comp.xZConstructionPlane)
    rect(sk, (g.panel_bot, 0.0, -g.panel_z), (g.cover_x, 0.0, g.panel_z))
    body = extrude(comp, sk.profiles.item(0), g.th_s).bodies.item(0)
    snap(comp, body, 'y', min(y_in, y_out))

    sk2 = comp.sketches.add(comp.xYConstructionPlane)
    rect(sk2, (g.cover_x, sy * g.pflange_in, 0.0), (g.pflange_x, y_in, 0.0))
    extrude_sym(comp, all_profiles(sk2), 2 * g.panel_z)
    body = merge_all(comp)

    bend(comp, body, g.th_s, 'z', {'x': g.pflange_x, 'y': y_in}, "top flange inner")
    bend(comp, body, 2 * g.th_s, 'z', {'x': g.cover_x, 'y': y_out}, "top flange outer")

    sk3 = comp.sketches.add(comp.xZConstructionPlane)
    for x, z in g.bolt_panel_rail:
        circle(sk3, (x, 0.0, z), g.m5)
    for x, z in g.bolt_panel_leg:
        circle(sk3, (x, 0.0, z), g.m5)
        circle(sk3, (x, 0.0, -z), g.m5)
    for x, z in g.bolt_panel_lip:
        circle(sk3, (x, 0.0, z), g.m5)
        circle(sk3, (x, 0.0, -z), g.m5)
    for x, z in g.bolt_bulk_panel:
        circle(sk3, (x, 0.0, z), g.m5)
        circle(sk3, (x, 0.0, -z), g.m5)
    extrude_sym(comp, all_profiles(sk3), 2 * (g.panel_y + 5),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    if sy > 0:                                   # mouth of the tow coupling
        sk5 = comp.sketches.add(comp.xZConstructionPlane)
        rect(sk5, (g.deck_bot - 1.0, 0.0, -(g.dock_out_hw + 1.0)),
             (g.dock_web + 1.0, 0.0, g.dock_out_hw + 1.0))
        extrude_sym(comp, all_profiles(sk5), 2 * (g.panel_y + 5),
                    adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    sk4 = comp.sketches.add(comp.yZConstructionPlane)
    for y, z in g.bolt_cover_panel:
        circle(sk4, (0.0, sy * y, z), g.m5)
    extrude_sym(comp, all_profiles(sk4), 2 * (abs(g.cover_x) + 10),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    rename_bodies(comp, name)
    log("  %-14s %s" % (name, fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_cover(root, g):
    comp = new_component(root, "COVER_TOP")
    sk = comp.sketches.add(comp.yZConstructionPlane)
    rect(sk, (0.0, g.panel_y, -g.cover_z), (0.0, -g.panel_y, g.cover_z))
    body = extrude(comp, sk.profiles.item(0), g.th_c).bodies.item(0)
    snap(comp, body, 'x', g.cover_x - g.th_c)

    sk2 = comp.sketches.add(comp.yZConstructionPlane)
    for y, z in g.bolt_cover_panel:
        circle(sk2, (0.0, y, z), g.m5)
        circle(sk2, (0.0, -y, z), g.m5)
    extrude_sym(comp, all_profiles(sk2), 2 * (abs(g.cover_x) + 10),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    rename_bodies(comp, "COVER_TOP")
    log("  %-14s %s" % ("COVER_TOP", fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_bulkhead(root, g, sz, name):
    """Transverse rib: ties both side panels together and frames the mainboard.
    Notched at the bottom to saddle over the deck rails; side edges folded
    outboard into bolting flanges."""
    comp = new_component(root, name)
    z_out = sz * g.bulk_z
    z_in = sz * g.bulk_in_z
    pl = plane_at(comp, comp.xYConstructionPlane, z_in)

    sk = comp.sketches.add(pl)
    polyline(sk, [(g.bulk_top_x, g.br_hw, z_in), (g.bulk_top_x, -g.br_hw, z_in),
                  (g.bulk_step_x, -g.br_hw, z_in), (g.bulk_step_x, -g.bulk_narrow, z_in),
                  (g.deck_top, -g.bulk_narrow, z_in), (g.deck_top, g.bulk_narrow, z_in),
                  (g.bulk_step_x, g.bulk_narrow, z_in), (g.bulk_step_x, g.br_hw, z_in)])
    body = extrude(comp, sk.profiles.item(0), g.th_s).bodies.item(0)
    snap(comp, body, 'z', min(z_in, z_out))

    # Side flanges: the profile lives in the XZ plane, so each one is built on
    # its own, slid out to its Y and then boolean-joined back in.
    for s in (1.0, -1.0):
        sk2 = comp.sketches.add(comp.xZConstructionPlane)
        rect(sk2, (g.bulk_top_x, 0.0, z_in),
             (g.bulk_step_x, 0.0, sz * (g.bulk_in_z - g.bflange_d)))
        fl = extrude(comp, sk2.profiles.item(0), g.th_s).bodies.item(0)
        snap(comp, fl, 'y', s * g.br_hw if s < 0 else g.br_hw - g.th_s)
    body = merge_all(comp)

    for sy in (+1.0, -1.0):
        bend(comp, body, g.th_s, 'x',
             {'y': sy * (g.br_hw - g.th_s), 'z': z_in}, "flange inner Y%+.0f" % sy)
        bend(comp, body, 2 * g.th_s, 'x', {'y': sy * g.br_hw, 'z': z_out}, "flange outer Y%+.0f" % sy)

    mid = (g.bulk_top_x + g.bulk_step_x) / 2.0
    sk3 = comp.sketches.add(pl)
    circle(sk3, (mid, 0.0, z_in), 45.0)
    circle(sk3, (mid, 48.0, z_in), 30.0)
    circle(sk3, (mid, -48.0, z_in), 30.0)
    extrude_sym(comp, all_profiles(sk3), 6 * g.th_s,
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    sk4 = comp.sketches.add(comp.xZConstructionPlane)
    for x, z in g.bolt_bulk_panel:
        circle(sk4, (x, 0.0, sz * z), g.m5)
    extrude_sym(comp, all_profiles(sk4), 2 * (g.br_hw + 5),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    rename_bodies(comp, name)
    log("  %-14s %s" % (name, fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def _cyl(comp, dia, z_lo, z_hi, cx=0.0, cy=0.0):
    sk = comp.sketches.add(plane_at(comp, comp.xYConstructionPlane, z_lo))
    circle(sk, (cx, cy, z_lo), dia)
    b = extrude(comp, sk.profiles.item(0), z_hi - z_lo).bodies.item(0)
    snap(comp, b, 'z', min(z_lo, z_hi))
    return b


def build_dock_socket(root, g):
    """Tow coupling socket: a tapered hat channel bolted up under the deck.

    The taper is the whole point - the trolley's tongue wedges into it, so the
    joint has zero play and stays tight as it wears.  The cross pin sits in
    double shear through both walls and carries NO working load: it only stops
    the tongue backing out.  A latch that carries load wears, gains play and
    then lets go on its own."""
    comp = new_component(root, "DOCK_SOCKET")
    t = g.dock_wall_t

    # floor web: trapezoid in the YZ plane, extruded down along X
    sk = comp.sketches.add(comp.yZConstructionPlane)
    polyline(sk, [(0.0, g.dock_y0, g.dock_hw), (0.0, g.dock_y1, g.dock_hw1),
                  (0.0, g.dock_y1, -g.dock_hw1), (0.0, g.dock_y0, -g.dock_hw)])
    web = extrude(comp, sk.profiles.item(0), g.th_b).bodies.item(0)
    snap(comp, web, 'x', g.dock_floor)

    # side walls and the flanges that bolt them to the deck
    for sy in (1.0, -1.0):
        skw = comp.sketches.add(comp.yZConstructionPlane)
        polyline(skw, [(0.0, g.dock_y0, sy * g.dock_hw),
                       (0.0, g.dock_y1, sy * g.dock_hw1),
                       (0.0, g.dock_y1, sy * (g.dock_hw1 + t)),
                       (0.0, g.dock_y0, sy * (g.dock_hw + t))])
        w = extrude(comp, skw.profiles.item(0), g.dock_h + g.th_b).bodies.item(0)
        snap(comp, w, 'x', g.deck_bot)

        skf = comp.sketches.add(comp.yZConstructionPlane)
        polyline(skf, [(0.0, g.dock_y0, sy * (g.dock_hw + t)),
                       (0.0, g.dock_y1, sy * (g.dock_hw1 + t)),
                       (0.0, g.dock_y1, sy * (g.dock_hw1 + t + g.dock_flange)),
                       (0.0, g.dock_y0, sy * (g.dock_hw + t + g.dock_flange))])
        f = extrude(comp, skf.profiles.item(0), g.th_b).bodies.item(0)
        snap(comp, f, 'x', g.deck_bot)

    body = merge_all(comp)

    ym = (g.dock_y0 + g.dock_y1) / 2.0
    hwm = g.dock_hw_at(ym)
    for sy in (1.0, -1.0):
        bend_at(comp, body, g.th_b, (g.dock_floor, ym, sy * hwm), "web-wall in %+.0f" % sy)
        bend_at(comp, body, 2 * g.th_b, (g.dock_web, ym, sy * (hwm + t)), "web-wall out %+.0f" % sy)
        bend_at(comp, body, 2 * g.th_b, (g.deck_bot, ym, sy * hwm), "wall-flange out %+.0f" % sy)
        bend_at(comp, body, g.th_b, (g.dock_fl_x, ym, sy * (hwm + t)), "wall-flange in %+.0f" % sy)

    # cross pin, double shear through both walls
    sk3 = comp.sketches.add(comp.xYConstructionPlane)
    circle(sk3, (g.dock_pin_x, g.dock_pin_y, 0.0), g.dock_pin_d)
    extrude_sym(comp, all_profiles(sk3), 2 * (g.dock_out_hw + 10),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    # bolts up into the deck
    sk4 = comp.sketches.add(comp.yZConstructionPlane)
    for y, z in g.bolt_dock_deck:
        circle(sk4, (0.0, y, z), g.m5)
        circle(sk4, (0.0, y, -z), g.m5)
    extrude_sym(comp, all_profiles(sk4), 2 * (abs(g.deck_bot) + 10),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [body])

    rename_bodies(comp, "DOCK_SOCKET")
    log("  %-14s %s" % ("DOCK_SOCKET", fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_ref_tongue(root, g):
    """Reference only - the trolley's tongue, i.e. the envelope the cart must be
    built to.  THE WEDGE LIVES HERE, not in the socket: the top face is dock_slack
    lower than the cavity for most of its length and rises to full height near the
    mouth, so driving it home jams it against the underside of the deck and the
    joint has no play.  Putting the taper on this cheap, replaceable part (rather
    than on the folded socket) also means wear is taken up by re-shimming it."""
    comp = new_component(root, "REF_TONGUE")
    c = g.dock_clear
    y_out = g.dock_y0 + 120.0                    # drawbar sticking out to the cart
    y_deep = g.dock_y1 + 4.0                     # never bottoms out at the back

    sk = comp.sketches.add(comp.xYConstructionPlane)
    polyline(sk, [(g.dock_floor - c, y_deep, 0.0),
                  (g.dock_floor - c, y_out, 0.0),
                  (g.deck_bot, y_out, 0.0),
                  (g.deck_bot, g.dock_y0 - g.dock_ramp, 0.0),
                  (g.deck_bot + g.dock_slack, g.dock_y0 - g.dock_ramp - 30.0, 0.0),
                  (g.deck_bot + g.dock_slack, y_deep, 0.0)])
    b = extrude_sym(comp, sk.profiles.item(0), 2 * (g.dock_hw - c)).bodies.item(0)

    ym = (y_deep + y_out) / 2.0
    for sy in (1.0, -1.0):                       # clear the socket's bend radii
        chamfer_at(comp, b, g.th_b + 1.0,
                   (g.dock_floor - c, ym, sy * (g.dock_hw - c)), "tongue bottom %+.0f" % sy)

    sk2 = comp.sketches.add(comp.xYConstructionPlane)
    circle(sk2, (g.dock_pin_x, g.dock_pin_y, 0.0), g.dock_pin_d)
    extrude_sym(comp, all_profiles(sk2), 2 * (g.dock_hw + 10),
                adsk.fusion.FeatureOperations.CutFeatureOperation, [b])

    rename_bodies(comp, "REF_TONGUE")
    comp.opacity = 0.5
    log("  %-14s %s" % ("REF_TONGUE", fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_ref_pin(root, g):
    comp = new_component(root, "REF_DOCK_PIN")
    sk = comp.sketches.add(comp.xYConstructionPlane)
    circle(sk, (g.dock_pin_x, g.dock_pin_y, 0.0), g.dock_pin_d)
    # long enough for a handle and an R-clip, short enough to clear the motors
    extrude_sym(comp, sk.profiles.item(0),
                2 * (g.dock_hw + g.dock_wall_t + 14.0))
    rename_bodies(comp, "REF_DOCK_PIN")
    comp.opacity = 0.7
    log("  %-14s %s" % ("REF_DOCK_PIN", fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_wheel(root, g, sz, name):
    comp = new_component(root, name)
    _cyl(comp, g.wheel_d, sz * g.wheel_in, sz * (g.wheel_in + g.wheel_w))
    rename_bodies(comp, name)
    comp.opacity = 0.35
    log("  %-14s %s" % (name, fmt_bbox(comp.bRepBodies.item(0))))
    return comp


def build_motor(root, g, sz, name):
    """MEASURED: the motor is NOT coaxial with the wheel.  Its housing sits
    inboard, bolted flat against the bridge leg, with its axis motor_offset
    above the wheel axis; only the shaft comes through the plate.  What bridges
    the gap to the wheel (belt / gears) is still an open question."""
    comp = new_component(root, name)
    face = sz * g.leg_in_z
    cx = g.motor_cx
    _cyl(comp, g.motor_case_d, sz * (g.leg_in_z - g.motor_len), face, cx, 0.0)
    # shaft only reaches the inner face of the wheel: there is just
    # (wheel_in - mount_z - th_bridge) mm of room out there for a drive
    _cyl(comp, g.motor_shaft_d, face, sz * g.wheel_in, cx, 0.0)
    for i, suffix in enumerate(("_CASE", "_SHAFT")):
        if i < comp.bRepBodies.count:
            comp.bRepBodies.item(i).name = name + suffix
    comp.opacity = 0.55
    log("  %-14s %d bodies" % (name, comp.bRepBodies.count))
    return comp


def build_mainboard(root, g):
    comp = new_component(root, "REF_MAINBOARD")
    sk = comp.sketches.add(comp.xYConstructionPlane)
    rect(sk, (g.deck_top - g.board_h, g.board_hw, 0.0), (g.deck_top, -g.board_hw, 0.0))
    body = extrude_sym(comp, sk.profiles.item(0), 2 * g.board_z).bodies.item(0)
    rename_bodies(comp, "REF_MAINBOARD")
    comp.opacity = 0.3
    log("  %-14s %s" % ("REF_MAINBOARD", fmt_bbox(body)))
    return comp


def drop_stale(root):
    for i in range(root.occurrences.count - 1, -1, -1):
        occ = root.occurrences.item(i)
        if occ.component.name.startswith("GUSSET_"):
            occ.deleteMe()


# --------------------------------------------------------------------- main --
def run(_context):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent

    log("document: %s" % app.activeDocument.name)
    log("parameters:")
    g = Geo(get_params(des))
    log("sheet metal rules:")
    ensure_rules(des, g)
    log("components:")
    drop_stale(root)
    build_bridge(root, g)
    build_mount(root, g, +1.0, "MOTOR_MOUNT_R")
    build_mount(root, g, -1.0, "MOTOR_MOUNT_L")
    build_panel(root, g, +1.0, "PANEL_FORE")
    build_panel(root, g, -1.0, "PANEL_AFT")
    build_cover(root, g)
    build_dock_socket(root, g)
    build_ref_tongue(root, g)
    build_ref_pin(root, g)
    build_bulkhead(root, g, +1.0, "BULKHEAD_R")
    build_bulkhead(root, g, -1.0, "BULKHEAD_L")
    build_wheel(root, g, +1.0, "REF_WHEEL_R")
    build_wheel(root, g, -1.0, "REF_WHEEL_L")
    build_motor(root, g, +1.0, "REF_MOTOR_R")
    build_motor(root, g, -1.0, "REF_MOTOR_L")
    build_mainboard(root, g)

    log("")
    log("track %.0f mm (centre to centre), clear span between wheels %.0f mm"
        % (2 * g.wheel_z, 2 * g.wheel_in))
    log("overall  %.0f (Z) x %.0f (Y) x %.1f (X) mm"
        % (2 * g.cover_z, 2 * g.body_hw, abs(g.cover_x - g.th_c) - abs(g.leg_bot)))
    log("electronics bay  %.0f (X) x %.0f (Y) x %.0f (Z) mm free"
        % (g.board_h, 2 * g.board_hw, 2 * g.board_z))
    log("fasteners %d: M6 x %d hold the motor mounts, the rest are M5"
        % (g.n_bolts(), len(g.bolt_mount_leg) * 2 * 2))
    log("MEASURED motor: axis %.0f mm above the wheel axis, case D%.1f, 4 x D%.1f bolts"
        % (g.motor_offset, g.motor_case_d, g.motor_bolt_d))
    log("  clearance case top -> deck underside : %.1f mm"
        % (abs(g.deck_bot) - g.motor_offset - g.motor_case_d / 2.0))
    log("tow coupling: socket %.0f x %.0f mm, %.0f deep; wedge is on the tongue"
        % (2 * g.dock_hw, g.dock_h, g.dock_depth))
    if g.dock_taper > 1e-6:
        log("  WARNING: biba_dock_taper != 0 - a tapered socket will NOT unfold")
    log("  D%.0f cross pin in double shear %.0f mm inboard; socket bolts into the 3 mm deck"
        % (g.dock_pin_d, g.dock_y0 - g.dock_pin_y))
    log("  room outboard of the plate for a drive: %.1f mm  <-- OPEN QUESTION"
        % (g.wheel_in - g.mount_z - g.th_b))
    print("\n".join(LOG))
