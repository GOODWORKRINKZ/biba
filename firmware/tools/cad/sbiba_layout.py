# -*- coding: utf-8 -*-
"""SBIBA - step 1: user parameters + LAYOUT skeleton sketches.

Coordinate frame (ROS REP-103, so it matches the robot's own frame):
    X = forward,  Y = left,  Z = up
    origin = on the GROUND, under the midpoint of the wheel axle
=> ground clearance of anything is simply its Z.

Idempotent: re-running deletes the LAYOUT component and rebuilds it from the
current value of the sb_* user parameters.
"""
import math
import adsk.core, adsk.fusion, traceback

MM = 0.1  # mm -> cm (Fusion internal units)

DEFAULTS = [
    # --- running gear -------------------------------------------------------
    ("sb_track",        500.0, "BAZA: mezhdu centrami koles"),
    ("sb_wheel_dia",    254.0, "koleso 10 dyuymov"),
    ("sb_wheel_w",       85.0, "shirina kolesa"),
    ("sb_wheel_gap",      8.0, "zazor: torec kolesa -> naruzhnaya gran plity motora"),

    # --- motor MY1016Z 24V 250W, REDUKTORNYY (promereno, staraya model) -----
    # Vyhodnoy val reduktora NE sooseн s motorom. Koleso sidit na vyhodnom valu
    # cherez shponku => os kolesa = os vyhodnogo vala. Korpus motora vyshe.
    ("sb_motor_offset",  42.0, "os KORPUSA motora vyshe osi vyhodnogo vala/kolesa"),
    ("sb_gear_boss_d",   88.0, "bobyshka reduktora vokrug vyhodnogo vala"),
    ("sb_motor_case_d", 102.0, "korpus motora"),
    ("sb_motor_len",    107.0, "dlina motora s reduktorom"),
    ("sb_motor_spig_d",  82.8, "posadochnyy bortik"),
    ("sb_motor_shaft_d", 17.0, "val"),
    ("sb_motor_shaft_hole", 21.0, "prohod vala v plite"),
    ("sb_motor_bolt_d",   7.0, "krepezh motora, 4 sht (M6)"),

    # --- sheet ---------------------------------------------------------------
    ("sb_th_bridge",      3.0, "tolschina: nesuschiy most + plity motora"),
    ("sb_th_side",        2.0, "tolschina: paneli i perebonki"),
    ("sb_th_cover",       1.0, "tolschina: kryshka"),

    # --- body ----------------------------------------------------------------
    ("sb_body_len",     240.0, "DLINA korpusa vpered/nazad (naruzhnyy gabarit)"),
    ("sb_bay_h",         70.0, "VYSOTA vnutrennego otseka elektroniki"),
    ("sb_deck_gap",       2.0, "zazor: verh korpusa motora -> niz nastila"),
    ("sb_leg_clear",      0.0, "niz nog mosta vyshe niza korpusa motora"),
    ("sb_rail_h",        22.0, "vysota otognutyh vverh reber nastila"),

    # --- support / caster mount under the deck --------------------------------
    ("sb_sup_pitch_x",  200.0, "OPORA: baza mezhdu boltami M8 po X"),
    ("sb_sup_pitch_y",  200.0, "OPORA: baza mezhdu boltami M8 po Y"),
    ("sb_sup_x",          0.0, "OPORA: centr ploschadki vpered ot osi koles"),
    ("sb_sup_bolt_d",     9.0, "OPORA: otverstie pod bolt M8"),
    ("sb_sup_edge",      20.0, "OPORA: kraevoy otstup ploschadki ot centra bolta"),

    ("sb_btn_d",         22.0, "otverstie pod knopku vklyucheniya"),

    ("sb_bolt_m6",        6.6, "otverstie pod M6"),
    ("sb_bolt_m5",        5.5, "otverstie pod M5"),
]


class Geo(object):
    def __init__(self, p):
        self.p = p
        self.track = p["sb_track"]
        self.wheel_r = p["sb_wheel_dia"] / 2.0
        self.wheel_w = p["sb_wheel_w"]
        self.wheel_y = self.track / 2.0
        self.wheel_in = self.wheel_y - self.wheel_w / 2.0

        self.th_b = p["sb_th_bridge"]
        self.th_s = p["sb_th_side"]
        self.th_c = p["sb_th_cover"]

        # --- vertical stack, everything measured from the ground -------------
        # gearbox output shaft = wheel axis; the motor body sits above it
        self.axle_z = self.wheel_r                          # output shaft / wheel
        self.boss_r = p["sb_gear_boss_d"] / 2.0
        self.boss_bot = self.axle_z - self.boss_r           # gearbox boss, lowest
        self.motor_r = p["sb_motor_case_d"] / 2.0
        self.motor_z = self.axle_z + p["sb_motor_offset"]   # motor body axis
        self.motor_bot = self.motor_z - self.motor_r
        self.motor_top = self.motor_z + self.motor_r
        self.clearance = min(self.boss_bot, self.motor_bot)

        self.leg_bot = self.clearance + p["sb_leg_clear"]
        self.deck_bot = self.motor_top + p["sb_deck_gap"]
        self.deck_top = self.deck_bot + self.th_b
        self.rail_top = self.deck_top + p["sb_rail_h"]
        self.cover_bot = self.deck_top + p["sb_bay_h"]
        self.cover_top = self.cover_bot + self.th_c

        # --- lateral stack (Y) ------------------------------------------------
        self.mount_y = self.wheel_in - p["sb_wheel_gap"]    # outer face, motor plate
        self.leg_y = self.mount_y - self.th_b               # bridge leg outer face

        # --- fore/aft stack (X): bay | rails | panels | plate lips ------------
        self.body_hx = p["sb_body_len"] / 2.0               # outer face of plate lips
        self.panel_x = self.body_hx - self.th_b             # outer face of panels
        self.br_hx = self.panel_x - self.th_s               # bridge deck edge
        self.rail_in = self.br_hx - self.th_b               # inner face of the rails

        # --- motor bolt circle, measured: two on PCD86, two on PCD88 ----------
        # offsets from the MOTOR axis, in the plate plane (X fore/aft, Z up)
        self.motor_bolts = [(21.50, 37.24), (-21.50, 37.24),
                            (42.32, -12.04), (-42.32, -12.04)]
        self.shaft_hole_d = p["sb_motor_shaft_hole"]
        self.motor_bolt_d = p["sb_motor_bolt_d"]
        self.motor_case_d = p["sb_motor_case_d"]
        self.motor_len = p["sb_motor_len"]
        self.motor_shaft_d = p["sb_motor_shaft_d"]
        self.motor_spig_d = p["sb_motor_spig_d"]

        # --- support mount ----------------------------------------------------
        self.sup_x = p["sb_sup_x"]
        self.sup_px = p["sb_sup_pitch_x"]
        self.sup_py = p["sb_sup_pitch_y"]
        self.sup_bolt_d = p["sb_sup_bolt_d"]
        self.sup_edge = p["sb_sup_edge"]
        self.sup_hx = self.sup_px / 2.0 + self.sup_edge
        self.sup_hy = self.sup_py / 2.0 + self.sup_edge
        self.pad_bot = self.deck_bot - self.th_b            # underside of the pad


# ------------------------------------------------------------------ params --
def get_params(des):
    vals, created = {}, 0
    ups = des.userParameters
    units = des.unitsManager.defaultLengthUnits
    for name, default, comment in DEFAULTS:
        pr = ups.itemByName(name)
        if pr is None:
            vi = adsk.core.ValueInput.createByString("%g %s" % (default, units))
            pr = ups.add(name, vi, units, comment)
            created += 1
        vals[name] = pr.value / MM  # cm -> mm
    return vals, created


# ----------------------------------------------------------------- helpers --
def new_component(root, name):
    for i in range(root.occurrences.count - 1, -1, -1):
        occ = root.occurrences.item(i)
        if occ.component.name == name:
            occ.deleteMe()
    m = adsk.core.Matrix3D.create()
    occ = root.occurrences.addNewComponent(m)
    occ.component.name = name
    return occ.component


def sk_pt(sk, x, y, z):
    """Model-space mm -> sketch-space point."""
    p = adsk.core.Point3D.create(x * MM, y * MM, z * MM)
    return sk.modelToSketchSpace(p)


def line(sk, a, b, constr=True):
    ln = sk.sketchCurves.sketchLines.addByTwoPoints(a, b)
    ln.isConstruction = constr
    return ln


def poly(sk, pts, constr=True):
    for i in range(len(pts)):
        line(sk, pts[i], pts[(i + 1) % len(pts)], constr)


def circ(sk, c, dia, constr=True):
    ci = sk.sketchCurves.sketchCircles.addByCenterRadius(c, dia / 2.0 * MM)
    ci.isConstruction = constr
    return ci


def cross(sk, c, r_mm):
    """Small axis cross so an axis centre is visible in the sketch."""
    a = adsk.core.Point3D.create(c.x - r_mm * MM, c.y, 0)
    b = adsk.core.Point3D.create(c.x + r_mm * MM, c.y, 0)
    line(sk, a, b)
    a = adsk.core.Point3D.create(c.x, c.y - r_mm * MM, 0)
    b = adsk.core.Point3D.create(c.x, c.y + r_mm * MM, 0)
    line(sk, a, b)


# ---------------------------------------------------------------- sketches --
def lay_side(comp, g):
    """Side view, on XZ (Y=0): X forward, Z up."""
    sk = comp.sketches.add(comp.xZConstructionPlane)
    sk.name = "LAY_SIDE"
    sk.isComputeDeferred = True
    P = lambda x, z: sk_pt(sk, x, 0.0, z)

    line(sk, P(-320, 0), P(320, 0))                        # ground
    circ(sk, P(0, g.axle_z), g.wheel_r * 2)                # wheel
    circ(sk, P(0, g.axle_z), g.boss_r * 2)                 # gearbox boss
    cross(sk, P(0, g.axle_z), 20)
    circ(sk, P(0, g.motor_z), g.motor_case_d)              # motor case
    circ(sk, P(0, g.motor_z), g.motor_spig_d)
    cross(sk, P(0, g.motor_z), 20)
    line(sk, P(-320, g.clearance), P(320, g.clearance))    # clearance line
    line(sk, P(-g.body_hx, g.leg_bot), P(g.body_hx, g.leg_bot))
    poly(sk, [P(-g.br_hx, g.deck_bot), P(g.br_hx, g.deck_bot),
              P(g.br_hx, g.deck_top), P(-g.br_hx, g.deck_top)])
    line(sk, P(-g.br_hx, g.rail_top), P(g.br_hx, g.rail_top))
    poly(sk, [P(-g.rail_in, g.deck_top), P(g.rail_in, g.deck_top),
              P(g.rail_in, g.cover_bot), P(-g.rail_in, g.cover_bot)])
    poly(sk, [P(-g.panel_x, g.leg_bot), P(g.panel_x, g.leg_bot),
              P(g.panel_x, g.cover_top), P(-g.panel_x, g.cover_top)])
    # SUPPORT_PAD: separate 3 mm plate bolted under the deck, M8 grid on it
    poly(sk, [P(g.sup_x - g.sup_hx, g.deck_bot), P(g.sup_x + g.sup_hx, g.deck_bot),
              P(g.sup_x + g.sup_hx, g.pad_bot), P(g.sup_x - g.sup_hx, g.pad_bot)])
    for sx in (-1, 1):
        line(sk, P(g.sup_x + sx * g.sup_px / 2.0, g.deck_bot + 6.0),
                 P(g.sup_x + sx * g.sup_px / 2.0, g.pad_bot - 6.0))
    sk.isComputeDeferred = False
    return sk


def lay_front(comp, g):
    """Front view, on YZ (X=0): Y left, Z up."""
    sk = comp.sketches.add(comp.yZConstructionPlane)
    sk.name = "LAY_FRONT"
    sk.isComputeDeferred = True
    P = lambda y, z: sk_pt(sk, 0.0, y, z)

    line(sk, P(-380, 0), P(380, 0))                        # ground
    line(sk, P(-380, g.clearance), P(380, g.clearance))    # clearance
    line(sk, P(-380, g.axle_z), P(380, g.axle_z))          # axle
    for s in (1, -1):
        poly(sk, [P(s * (g.wheel_y - g.wheel_w / 2.0), g.axle_z - g.wheel_r),
                  P(s * (g.wheel_y + g.wheel_w / 2.0), g.axle_z - g.wheel_r),
                  P(s * (g.wheel_y + g.wheel_w / 2.0), g.axle_z + g.wheel_r),
                  P(s * (g.wheel_y - g.wheel_w / 2.0), g.axle_z + g.wheel_r)])
        cross(sk, P(s * g.wheel_y, g.axle_z), 20)
        poly(sk, [P(s * g.mount_y, g.motor_bot),
                  P(s * (g.mount_y - g.motor_len), g.motor_bot),
                  P(s * (g.mount_y - g.motor_len), g.motor_top),
                  P(s * g.mount_y, g.motor_top)])
        cross(sk, P(s * g.wheel_y, g.motor_z), 12)
        line(sk, P(s * g.mount_y, g.leg_bot), P(s * g.mount_y, g.cover_bot))
        line(sk, P(s * g.leg_y, g.leg_bot), P(s * g.leg_y, g.deck_bot))
    poly(sk, [P(-g.leg_y, g.deck_bot), P(g.leg_y, g.deck_bot),
              P(g.leg_y, g.deck_top), P(-g.leg_y, g.deck_top)])
    poly(sk, [P(-g.leg_y, g.deck_top), P(g.leg_y, g.deck_top),
              P(g.leg_y, g.cover_bot), P(-g.leg_y, g.cover_bot)])
    line(sk, P(-g.mount_y, g.cover_top), P(g.mount_y, g.cover_top))
    sk.isComputeDeferred = False
    return sk


def lay_top(comp, g):
    """Plan view, on XY at ground level: X forward, Y left."""
    sk = comp.sketches.add(comp.xYConstructionPlane)
    sk.name = "LAY_TOP"
    sk.isComputeDeferred = True
    P = lambda x, y: sk_pt(sk, x, y, 0.0)

    for s in (1, -1):
        poly(sk, [P(-g.wheel_r, s * (g.wheel_y - g.wheel_w / 2.0)),
                  P(g.wheel_r, s * (g.wheel_y - g.wheel_w / 2.0)),
                  P(g.wheel_r, s * (g.wheel_y + g.wheel_w / 2.0)),
                  P(-g.wheel_r, s * (g.wheel_y + g.wheel_w / 2.0))])
    poly(sk, [P(-g.body_hx, -g.mount_y), P(g.body_hx, -g.mount_y),
              P(g.body_hx, g.mount_y), P(-g.body_hx, g.mount_y)])
    poly(sk, [P(-g.rail_in, -g.leg_y), P(g.rail_in, -g.leg_y),
              P(g.rail_in, g.leg_y), P(-g.rail_in, g.leg_y)])
    # SUPPORT_PAD outline + the four M8 holes, projected to the ground
    poly(sk, [P(g.sup_x - g.sup_hx, -g.sup_hy), P(g.sup_x + g.sup_hx, -g.sup_hy),
              P(g.sup_x + g.sup_hx, g.sup_hy), P(g.sup_x - g.sup_hx, g.sup_hy)])
    for sx in (-1, 1):
        for sy in (-1, 1):
            circ(sk, P(g.sup_x + sx * g.sup_px / 2.0, sy * g.sup_py / 2.0), g.sup_bolt_d)
    line(sk, P(0, -380), P(0, 380))
    line(sk, P(-320, 0), P(320, 0))
    sk.isComputeDeferred = False
    return sk


def lay_plate(comp, g):
    """Motor mount plate plane (Y = mount_y): the measured motor interface."""
    pl = comp.constructionPlanes.createInput()
    pl.setByOffset(comp.xZConstructionPlane,
                   adsk.core.ValueInput.createByReal(g.mount_y * MM))
    plane = comp.constructionPlanes.add(pl)
    plane.name = "PL_MOUNT_L"
    sk = comp.sketches.add(plane)
    sk.name = "LAY_MOTOR_IFACE"
    sk.isComputeDeferred = True
    P = lambda x, z: sk_pt(sk, x, g.mount_y, z)

    cross(sk, P(0, g.axle_z), 30)
    circ(sk, P(0, g.axle_z), 88.0)                    # bore round the axle
    cross(sk, P(0, g.motor_z), 30)
    circ(sk, P(0, g.motor_z), g.motor_case_d)
    circ(sk, P(0, g.motor_z), g.motor_spig_d)
    circ(sk, P(0, g.motor_z), g.shaft_hole_d)
    circ(sk, P(0, g.motor_z), 86.0)
    for bx, bz in g.motor_bolts:
        circ(sk, P(bx, g.motor_z + bz), g.motor_bolt_d)
    sk.isComputeDeferred = False
    return sk


# --------------------------------------------------------------------- run --
def run(_context):
    app = adsk.core.Application.get()
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        des.designType = adsk.fusion.DesignTypes.ParametricDesignType
        root = des.rootComponent
        p, created = get_params(des)
        g = Geo(p)

        comp = new_component(root, "LAYOUT")
        lay_side(comp, g)
        lay_front(comp, g)
        lay_top(comp, g)
        lay_plate(comp, g)

        print("params: %d created, %d total" % (created, des.userParameters.count))
        print("--- vertical stack, mm above ground ---")
        for k, v in [("ground", 0.0),
                     ("CLEARANCE (lowest point)", g.clearance),
                     ("gearbox boss bottom", g.boss_bot),
                     ("motor case bottom", g.motor_bot),
                     ("bridge leg bottom", g.leg_bot),
                     ("wheel axle = output shaft", g.axle_z),
                     ("motor body axis", g.motor_z),
                     ("motor case top", g.motor_top),
                     ("deck bottom", g.deck_bot),
                     ("deck top", g.deck_top),
                     ("rail top", g.rail_top),
                     ("cover bottom", g.cover_bot),
                     ("cover top = OVERALL HEIGHT", g.cover_top)]:
            print("  %-32s %8.1f" % (k, v))
        print("--- lateral (Y), mm from centreline ---")
        print("  wheel centre                     %8.1f" % g.wheel_y)
        print("  wheel inner face                 %8.1f" % g.wheel_in)
        print("  motor plate outer face           %8.1f" % g.mount_y)
        print("  bridge leg outer face            %8.1f" % g.leg_y)
        print("  clear span between wheels        %8.1f" % (2 * g.wheel_in))
        print("  motor sticks inboard to Y=       %8.1f" % (g.mount_y - g.motor_len))
        print("--- fore/aft (X), mm from centre ---")
        print("  body half length                 %8.1f" % g.body_hx)
        print("  bay half length                  %8.1f" % g.rail_in)
        print("  support pad                      %.0f x %.0f, M8 grid %.0f x %.0f"
              % (2 * g.sup_hx, 2 * g.sup_hy, g.sup_px, g.sup_py))
        print("--- free volume for electronics (L x W x H) ---")
        print("  %.0f x %.0f x %.0f mm" % (2 * g.rail_in, 2 * g.leg_y, p["sb_bay_h"]))
    except Exception:
        print("FAILED\n" + traceback.format_exc())
