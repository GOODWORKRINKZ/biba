# -*- coding: utf-8 -*-
"""SBIBA - interference check: boolean-intersect every pair of bodies in the
assembly and report any pair that actually shares volume."""
import adsk.core, adsk.fusion, traceback

MM = 0.1
SKIP_PAIRS = [("REF_MOTOR", "REF_WHEEL")]   # the shaft is meant to enter the wheel


def run(_context):
    app = adsk.core.Application.get()
    out = []
    try:
        des = adsk.fusion.Design.cast(app.activeProduct)
        root = des.rootComponent
        tmp = adsk.fusion.TemporaryBRepManager.get()

        items = []
        for occ in root.occurrences:
            c = occ.component
            if c.name == "LAYOUT":
                continue
            for i in range(c.bRepBodies.count):
                b = c.bRepBodies.item(i)
                items.append((c.name, b.name, tmp.copy(b), b.boundingBox))

        out.append("bodies: %d" % len(items))
        hits = 0
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                ci, bi, gi, xi = items[i]
                cj, bj, gj, xj = items[j]
                if ci == cj:
                    continue
                if any((a in ci and b in cj) or (a in cj and b in ci)
                       for a, b in SKIP_PAIRS):
                    continue
                if not xi.intersects(xj):
                    continue
                g = tmp.copy(gi)
                try:
                    ok = tmp.booleanOperation(
                        g, tmp.copy(gj),
                        adsk.fusion.BooleanTypes.IntersectionBooleanType)
                except Exception:
                    ok = False
                if ok and g.volume > 1e-4:
                    hits += 1
                    b = g.boundingBox
                    out.append("  CLASH %-14s x %-14s  %8.1f mm3  at X %.0f..%.0f "
                               "Y %.0f..%.0f Z %.0f..%.0f"
                               % (ci, cj, g.volume / (MM ** 3),
                                  b.minPoint.x / MM, b.maxPoint.x / MM,
                                  b.minPoint.y / MM, b.maxPoint.y / MM,
                                  b.minPoint.z / MM, b.maxPoint.z / MM))
        out.append("clashes: %d" % hits)

        # mass of the steel parts
        tot = 0.0
        for cname, bname, g, bb in items:
            if cname.startswith("REF_"):
                continue
            m = g.volume / (MM ** 3) * 7.85e-6   # mm3 -> kg for steel
            tot += m
            out.append("  %-16s %6.3f kg" % (cname, m))
        out.append("steel total: %.2f kg" % tot)
        print("\n".join(out))
    except Exception:
        print("\n".join(out))
        print("FAILED\n" + traceback.format_exc())
