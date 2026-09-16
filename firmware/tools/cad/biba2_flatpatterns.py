# -*- coding: utf-8 -*-
"""BIBA2: solids -> sheet metal -> flat patterns -> DXF for the laser.

Run this AFTER tools/cad/biba2_chassis.py has built the model.  For every
manufactured part it:

  1. BRepBody.convertToSheetMetal(baseFace, rule)  - turns the solid into a real
     sheet-metal body; Fusion recognises the fillets as bends and the flat
     lengths come out with the rule's K-factor applied.
  2. Component.createFlatPattern(stationaryFace)   - unfolds it.
  3. ExportManager.createDXFFlatPatternExportOptions(...) - writes the DXF.

Caveat worth knowing: convertToSheetMetal CONSUMES the rule you hand it - the
rule is renamed "<name> (Convert)" and bound to that component - so a rule can
only be spent once.  ensure_rule() below re-materialises whatever is missing.

Bend lines end up on their own DXF layer, so the press brake operator gets the
fold positions with the blank.
"""

import adsk.core
import adsk.fusion
import os
import traceback

MM = 0.1

OUT_DIR = r"D:\PROGECTS\biba\firmware\docs\cad\dxf"

# component -> nominal thickness (mm); must match tools/cad/biba2_chassis.py
JOBS = [
    ("MAIN_BRIDGE",   3.0),
    ("MOTOR_MOUNT_R", 3.0),
    ("MOTOR_MOUNT_L", 3.0),
    ("DOCK_SOCKET",   3.0),
    ("PANEL_FORE",    2.0),
    ("PANEL_AFT",     2.0),
    ("BULKHEAD_R",    2.0),
    ("BULKHEAD_L",    2.0),
    ("COVER_TOP",     1.0),
]

LOG = []


def log(m):
    LOG.append(str(m))


def ensure_rule(des, th):
    """A usable design rule of the given thickness, recreated if a previous
    conversion has already eaten it."""
    want = "BIBA Steel %gmm" % th
    for r in des.designSheetMetalRules:
        if r.name == want:
            return r
    src = None
    for r in des.designSheetMetalRules:
        src = r
        break
    if src is None:
        src = des.librarySheetMetalRules.item(0)
    r = des.designSheetMetalRules.addByCopy(src, want)
    r.thickness.value = th * MM
    try:
        r.bendRadius.expression = "%g mm" % th        # inner radius = thickness
    except Exception:
        pass
    return r


def biggest_planar(body):
    """The face the part lies flat on: biggest planar face wins."""
    best, ba = None, -1.0
    for f in body.faces:
        if isinstance(f.geometry, adsk.core.Plane) and f.area > ba:
            best, ba = f, f.area
    return best


def find_component(root, name):
    for occ in root.occurrences:
        if occ.component.name == name:
            return occ.component
    return None


def blank_size(fp):
    b = fp.flatBody.boundingBox
    return ((b.maxPoint.x - b.minPoint.x) / MM,
            (b.maxPoint.y - b.minPoint.y) / MM)


def bend_report(fp):
    try:
        info = fp.getBendInfo()
    except Exception:
        return ""
    try:
        n = len(info[0]) if info and info[0] else 0
    except Exception:
        n = 0
    return "bends=%d" % n


def run(_context):
    app = adsk.core.Application.get()
    des = adsk.fusion.Design.cast(app.activeProduct)
    root = des.rootComponent
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)

    ok_n = 0
    for name, th in JOBS:
        comp = find_component(root, name)
        if comp is None:
            log("%-14s NOT FOUND" % name)
            continue
        if comp.bRepBodies.count == 0:
            log("%-14s no bodies" % name)
            continue
        try:
            body = comp.bRepBodies.item(0)
            if not body.isSheetMetal:
                rule = ensure_rule(des, th)
                converted = body.convertToSheetMetal(biggest_planar(body), rule)
                body = comp.bRepBodies.item(0)
                if not converted or not body.isSheetMetal:
                    log("%-14s convert refused (converted=%s)" % (name, converted))
                    continue
            fp = comp.flatPattern
            if fp is None:
                fp = comp.createFlatPattern(biggest_planar(body))
            w, h = blank_size(fp)
            path = os.path.join(OUT_DIR, name + ".dxf")
            opts = des.exportManager.createDXFFlatPatternExportOptions(path, fp)
            wrote = des.exportManager.execute(opts)
            real_th = comp.activeSheetMetalRule.thickness.value / MM
            log("%-14s %.1f mm  blank %6.1f x %6.1f mm  %-9s DXF=%s"
                % (name, real_th, w, h, bend_report(fp), wrote))
            ok_n += 1
        except Exception as e:
            log("%-14s FAILED: %s" % (name, e))
            log("               %s" % traceback.format_exc().strip().splitlines()[-1][:160])

    log("")
    log("%d/%d parts exported to %s" % (ok_n, len(JOBS), OUT_DIR))
    print("\n".join(LOG))
