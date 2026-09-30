"""Small helper layer over the SOLIDWORKS COM API for building printable parts - VERSION 3.1.

v3.1 = a byte copy of swlib_v3.py (which stays untouched so v3 still rebuilds) plus, at the end:
  * stl_print_estimate(): what a slicer really lays down for an exported STL (walls, top/bottom skins, infill),
    so the printed grams in the report come from the exported file, not from one guessed FILL factor.
Everything above the "v3.1" marker is unchanged from swlib_v3.py.

This is a copy of swlib.py (which stays untouched so v1/v2 still rebuild) plus the helpers the v3 covered
design needs: rounded outlines (lines + true arcs) on all three planes, revolves, edge fillets and chamfers
picked by a point on the edge, shells, part / body / component colours, and a save that follows the
v3 folder rule. Every v3 helper is tested by swlib_v3_selftest.py against hand-computed volumes and boxes.

All sizes are millimetres. Axes: X = left/right, Y = up, Z = forward (Front Plane = XY).
Plane mapping (checked by probe_axes and the self-test):
    Front Plane  sketch (X, Y) = model (x, y)                     extrudes along +z
    Right Plane  sketch (X, Y) = model (-z, y)                    extrudes along +x
    Top Plane    sketch (X, Y) = model (x, -z * TOP_ZSIGN)        extrudes along +y
2D outlines for the v3 prisms are always given in MODEL coordinates of the plane:
    axis 'z' -> (x, y)      axis 'x' -> (z, y)      axis 'y' -> (x, z)
"""
import os, math, types, struct, re, pythoncom, win32com.client
from win32com.client import VARIANT

MM = 0.001
NOTHING = VARIANT(pythoncom.VT_DISPATCH, None)
CUT_FLIP = False          # set by probe(): which way a cut goes from its start plane
TOP_ZSIGN = 1             # Top Plane sketch Y = -model Z * TOP_ZSIGN (set by probe_axes)

# v3 colours (owner decision 2026-09-26)
WARM_WHITE = '#EEEAE3'    # lid, head, muzzle, ears, tail, leg outer halves
GRAPHITE = '#3A3E44'      # tub, side panels, bands, collar, leg inner covers and pods, wheels
BLACK = '#151515'         # the 13 hub caps, port doors, small covers


def app():
    a = win32com.client.Dispatch('SldWorks.Application')
    a.Visible = True
    return a


class FeatureFailed(RuntimeError):
    """A fillet / chamfer / shell / revolve that SOLIDWORKS refused or that changed nothing."""


class Part:
    def __init__(self, sw, name):
        self.sw = sw
        self.name = name
        self.m = sw.NewDocument(sw.GetUserPreferenceStringValue(8), 0, 0, 0)
        self.m.SketchManager.AddToDB = True
        self.fm = self.m.FeatureManager
        self.merge = True          # False: every solid becomes its own body (used for bought-part models)
        self.last = None
        self.skipped = []          # v3: (kind, size, point, reason) for every edge a *_safe call skipped
        self.color = None          # v3: last colour given to set_color
        self._planes = {}          # v3: (base plane, offset) -> reference plane name

    # --- sketching -------------------------------------------------------------
    def _sketch(self, plane):
        self.m.ClearSelection2(True)
        if not self.m.Extension.SelectByID2(plane, 'PLANE', 0, 0, 0, False, 0, NOTHING, 0):
            raise RuntimeError('cannot select ' + plane)
        self.m.SketchManager.InsertSketch(True)

    def _close(self):
        self.m.SketchManager.InsertSketch(True)

    def _extrude(self, a0, a1, cut):
        """Extrude the open sketch from a0 to a1 (mm) along the plane normal.
        A cut is done as: extrude a separate tool body, then subtract it from the main body
        (SOLIDWORKS' own cut-extrude refuses start offsets on the negative side)."""
        depth, start = (a1 - a0) * MM, a0 * MM
        t0 = 3 if abs(start) > 1e-12 else 0
        f = self.fm.FeatureExtrusion3(True, False, False, 0, 0, depth, 0, False, False, False, False,
                                      0, 0, False, False, False, False, (not cut) and self.merge, True, True,
                                      t0, abs(start), start < 0)
        if f is None:
            raise RuntimeError('extrude failed')
        if cut:
            f = self._subtract_tool(f)
        self.last = f
        return f

    def _subtract_tool(self, f):
        """Subtract the body made by feature f (a tool body) from the biggest other body."""
        tool = f.GetFaces[0].GetBody
        others = [bd for bd in self.m.GetBodies2(0, True) if bd.Name != tool.Name]
        if not others:
            raise RuntimeError('nothing to cut')
        main = max(others, key=lambda bd: bd.GetMassProperties(1000.0)[3])
        self.m.ClearSelection2(True)
        tools = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [tool])
        c = self.fm.InsertCombineFeature(15902, main, tools)
        if c is None:
            raise RuntimeError('subtract failed')
        return c

    def name_body(self, name):
        """Name the solid body made by the last (non-cut) extrude."""
        try:
            self.last.GetFaces[0].GetBody.Name = name
        except Exception:
            pass
        try:
            self.last.Name = name[:60]
        except Exception:
            pass

    # --- shapes ------------------------------------------------------------------
    def box(self, x0, x1, y0, y1, z0, z1, cut=False):
        self._sketch('Front Plane')
        self.m.SketchManager.CreateCornerRectangle(x0 * MM, y0 * MM, 0, x1 * MM, y1 * MM, 0)
        self._close()
        return self._extrude(min(z0, z1), max(z0, z1), cut)

    def cyl_z(self, cx, cy, r, z0, z1, cut=False):
        self._sketch('Front Plane')
        self.m.SketchManager.CreateCircleByRadius(cx * MM, cy * MM, 0, r * MM)
        self._close()
        return self._extrude(min(z0, z1), max(z0, z1), cut)

    def cyl_y(self, cx, cz, r, y0, y1, cut=False):
        # Top Plane sketch: sketch X = model X, sketch Y = model -Z (checked by probe_axes)
        self._sketch('Top Plane')
        self.m.SketchManager.CreateCircleByRadius(cx * MM, -cz * MM * TOP_ZSIGN, 0, r * MM)
        self._close()
        return self._extrude(min(y0, y1), max(y0, y1), cut)

    def box_y(self, x0, x1, z0, z1, y0, y1, cut=False):
        """Box sketched on the Top Plane, extruded along Y."""
        self._sketch('Top Plane')
        self.m.SketchManager.CreateCornerRectangle(x0 * MM, -z0 * MM * TOP_ZSIGN, 0, x1 * MM, -z1 * MM * TOP_ZSIGN, 0)
        self._close()
        return self._extrude(min(y0, y1), max(y0, y1), cut)

    def cyl_x(self, cy, cz, r, x0, x1, cut=False):
        # Right Plane sketch: sketch X = model -Z, sketch Y = model Y (verified with the wheel build)
        self._sketch('Right Plane')
        self.m.SketchManager.CreateCircleByRadius(-cz * MM, cy * MM, 0, r * MM)
        self._close()
        return self._extrude(min(x0, x1), max(x0, x1), cut)

    def box_x(self, y0, y1, z0, z1, x0, x1, cut=False):
        """Box sketched on the Right Plane (use for cuts through side walls)."""
        self._sketch('Right Plane')
        self.m.SketchManager.CreateCornerRectangle(-z0 * MM, y0 * MM, 0, -z1 * MM, y1 * MM, 0)
        self._close()
        return self._extrude(min(x0, x1), max(x0, x1), cut)

    # --- prisms (any closed outline, extruded straight) -----------------------------
    def _poly(self, plane, pts):
        sm = self.m.SketchManager
        self._sketch(plane)
        n = len(pts)
        for i in range(n):
            (a, b), (c, d) = pts[i], pts[(i + 1) % n]
            sm.CreateLine(a * MM, b * MM, 0, c * MM, d * MM, 0)
        self._close()

    def poly_z(self, pts_xy, z0, z1, cut=False):
        """Closed outline in model (x, y), extruded along Z."""
        self._poly('Front Plane', pts_xy)
        return self._extrude(min(z0, z1), max(z0, z1), cut)

    def poly_x(self, pts_zy, x0, x1, cut=False):
        """Closed outline in model (z, y), extruded along X (Right Plane: sketch X = -model Z)."""
        self._poly('Right Plane', [(-z, y) for z, y in pts_zy])
        return self._extrude(min(x0, x1), max(x0, x1), cut)

    def poly_y(self, pts_xz, y0, y1, cut=False):
        """Closed outline in model (x, z), extruded along Y (Top Plane: sketch Y = -model Z)."""
        self._poly('Top Plane', [(x, -z * TOP_ZSIGN) for x, z in pts_xz])
        return self._extrude(min(y0, y1), max(y0, y1), cut)

    # ================================================================================
    # v3: rounded outlines (lines + true arcs) extruded along x, y or z
    # ================================================================================
    def _plane_map(self, axis):
        """Sketch plane for an extrusion along `axis`, the map model(u, v) -> sketch(X, Y), and the sign of
        that map's determinant (a mirrored map turns counter-clockwise arcs into clockwise ones)."""
        if axis == 'z':
            return 'Front Plane', (lambda u, v: (u, v)), 1
        if axis == 'x':
            return 'Right Plane', (lambda u, v: (-u, v)), -1
        if axis == 'y':
            s = TOP_ZSIGN
            return 'Top Plane', (lambda u, v: (u, -v * s)), -s
        raise ValueError("axis must be 'x', 'y' or 'z'")

    def _emit(self, loops, fmap, det):
        """Draw closed loops of segments ('L' lines, 'A' arcs, 'C' circles) into the open sketch."""
        sm = self.m.SketchManager
        for loop in loops:
            for seg in loop:
                kind = seg[0]
                if kind == 'L':
                    (a, b), (c, d) = fmap(*seg[1]), fmap(*seg[2])
                    got = sm.CreateLine(a * MM, b * MM, 0, c * MM, d * MM, 0)
                elif kind == 'A':
                    (cx, cy), (a, b), (c, d) = fmap(*seg[1]), fmap(*seg[2]), fmap(*seg[3])
                    direction = (1 if seg[4] else -1) * det        # CreateArc: +1 = counter-clockwise
                    got = sm.CreateArc(cx * MM, cy * MM, 0, a * MM, b * MM, 0, c * MM, d * MM, 0, direction)
                elif kind == 'C':
                    cx, cy = fmap(*seg[1])
                    got = sm.CreateCircleByRadius(cx * MM, cy * MM, 0, seg[2] * MM)
                else:
                    raise ValueError('unknown segment ' + repr(seg))
                if got is None:
                    raise RuntimeError('sketch segment refused: ' + repr(seg))

    def prism(self, axis, loops, a0, a1, cut=False):
        """Extrude closed outline(s) along model `axis` ('x', 'y' or 'z') from a0 to a1 (mm).
        `loops` is one loop or a list of loops (from rpoly / rrect / stadium / slot / hull2 / circle, in the
        plane's model coordinates - see the module docstring). Nested loops make holes (e.g. a ring)."""
        loops = _as_loops(loops)
        plane, fmap, det = self._plane_map(axis)
        self._sketch(plane)
        self._emit(loops, fmap, det)
        self._close()
        return self._extrude(min(a0, a1), max(a0, a1), cut)

    # convenience wrappers ---------------------------------------------------------------
    def rrect_z(self, x0, x1, y0, y1, z0, z1, r=0.0, cut=False):
        """Rounded rectangle in (x, y), extruded along Z. r = one radius, or per corner in the order
        (x0,y0), (x1,y0), (x1,y1), (x0,y1) with x0 < x1, y0 < y1 (or a dict keyed '--', '+-', '++', '-+')."""
        return self.prism('z', rrect(x0, x1, y0, y1, r), z0, z1, cut)

    def rrect_x(self, z0, z1, y0, y1, x0, x1, r=0.0, cut=False):
        """Rounded rectangle in (z, y), extruded along X. Corner order (z0,y0), (z1,y0), (z1,y1), (z0,y1)."""
        return self.prism('x', rrect(z0, z1, y0, y1, r), x0, x1, cut)

    def rrect_y(self, x0, x1, z0, z1, y0, y1, r=0.0, cut=False):
        """Rounded rectangle in (x, z), extruded along Y. Corner order (x0,z0), (x1,z0), (x1,z1), (x0,z1)."""
        return self.prism('y', rrect(x0, x1, z0, z1, r), y0, y1, cut)

    def rpoly_z(self, pts_xy, radii, z0, z1, cut=False):
        return self.prism('z', rpoly(pts_xy, radii), z0, z1, cut)

    def rpoly_x(self, pts_zy, radii, x0, x1, cut=False):
        return self.prism('x', rpoly(pts_zy, radii), x0, x1, cut)

    def rpoly_y(self, pts_xz, radii, y0, y1, cut=False):
        return self.prism('y', rpoly(pts_xz, radii), y0, y1, cut)

    def hull_z(self, c1, r1, c2, r2, z0, z1, cut=False):
        """Two-circle tangent hull (capsule with unequal ends) in (x, y), extruded along Z."""
        return self.prism('z', hull2(c1, r1, c2, r2), z0, z1, cut)

    def hull_x(self, c1, r1, c2, r2, x0, x1, cut=False):
        """Two-circle tangent hull in (z, y) - e.g. a thigh outline from the hip circle to the knee drum."""
        return self.prism('x', hull2(c1, r1, c2, r2), x0, x1, cut)

    def hull_y(self, c1, r1, c2, r2, y0, y1, cut=False):
        return self.prism('y', hull2(c1, r1, c2, r2), y0, y1, cut)

    def slot_z(self, c1, c2, r, z0, z1, cut=False):
        return self.prism('z', slot(c1, c2, r), z0, z1, cut)

    def slot_x(self, c1, c2, r, x0, x1, cut=False):
        return self.prism('x', slot(c1, c2, r), x0, x1, cut)

    def slot_y(self, c1, c2, r, y0, y1, cut=False):
        return self.prism('y', slot(c1, c2, r), y0, y1, cut)

    # ================================================================================
    # v3: revolve
    # ================================================================================
    _BASE_NORMAL = {'Front Plane': (0, 0, 1), 'Right Plane': (1, 0, 0), 'Top Plane': (0, 1, 0)}

    def _plane(self, base, offset):
        """Name of a reference plane parallel to `base` at `offset` mm along the base's normal
        (Front +z, Right +x, Top +y). Made once per part and hidden so it does not show in renders."""
        if abs(offset) < 1e-9:
            return base
        key = (base, round(offset, 6))
        if key in self._planes:
            return self._planes[key]
        want = [n * offset * MM for n in self._BASE_NORMAL[base]]
        for flip in (offset < 0, offset >= 0):              # 256 = OptionFlip; checked against the plane's transform
            self.m.ClearSelection2(True)
            if not self.m.Extension.SelectByID2(base, 'PLANE', 0, 0, 0, False, 0, NOTHING, 0):
                raise RuntimeError('cannot select ' + base)
            f = self.fm.InsertRefPlane(8 | (256 if flip else 0), abs(offset) * MM, 0, 0, 0, 0)
            if f is None:
                raise RuntimeError(f'reference plane {base} {offset:+} failed')
            got = list(f.GetSpecificFeature2.Transform.ArrayData)[9:12]
            if max(abs(g - w) for g, w in zip(got, want)) < 1e-7:
                self._hide(f)
                self._planes[key] = f.Name
                return f.Name
            self._drop_feature(f)
        raise RuntimeError(f'reference plane {base} {offset:+} lands in the wrong place')

    def _hide(self, feat):
        try:
            self.m.ClearSelection2(True)
            feat.Select2(False, 0)
            self.m.BlankRefGeom()
        except Exception:
            pass
        self.m.ClearSelection2(True)

    def revolve(self, axis, center, loops, cut=False):
        """Full 360 deg solid of revolution about a line parallel to model `axis` through `center`.
        center = the axis line's other two model coordinates: axis 'x' -> (y, z), 'y' -> (x, z), 'z' -> (x, y).
        Profile loop(s) are drawn in (a, r): a = model coordinate ALONG the axis, r = distance from the axis
        (r >= 0; the profile may touch the axis). Use rpoly / rrect in (a, r) to make rims, grooves, domed caps."""
        loops = _as_loops(loops)
        for loop in loops:
            if min(p[1] for p in loop_points(loop, 0.5)) < -1e-6:
                raise ValueError('revolve profile crosses the axis (r < 0)')
        a_lo = min(p[0] for lp in loops for p in loop_points(lp, 0.5)) - 5
        a_hi = max(p[0] for lp in loops for p in loop_points(lp, 0.5)) + 5
        if axis == 'x':
            yc, zc = center
            plane, fmap, det = self._plane('Front Plane', zc), (lambda a, r: (a, yc + r)), 1
            cl = ((a_lo, yc), (a_hi, yc))
        elif axis == 'y':
            xc, zc = center
            plane, fmap, det = self._plane('Front Plane', zc), (lambda a, r: (xc + r, a)), -1
            cl = ((xc, a_lo), (xc, a_hi))
        elif axis == 'z':
            xc, yc = center
            plane, fmap, det = self._plane('Right Plane', xc), (lambda a, r: (-a, yc + r)), -1
            cl = ((-a_lo, yc), (-a_hi, yc))
        else:
            raise ValueError("axis must be 'x', 'y' or 'z'")
        self._sketch(plane)
        if self.m.SketchManager.CreateCenterLine(cl[0][0] * MM, cl[0][1] * MM, 0, cl[1][0] * MM, cl[1][1] * MM, 0) is None:
            raise RuntimeError('centerline refused')
        self._emit(loops, fmap, det)
        self._close()
        f = self.fm.FeatureRevolve2(True, True, False, False, False, False, 0, 0, 2 * math.pi, 0, False, False,
                                    0, 0, 0, 0, 0, (not cut) and self.merge, True, True)
        if f is None:
            raise FeatureFailed('revolve failed')
        if cut:
            f = self._subtract_tool(f)
        self.last = f
        return f

    # ================================================================================
    # v3: picking edges / faces by a point on them (view-independent)
    # ================================================================================
    # SelectByID2('', 'EDGE', x, y, z) picks along the VIEW ray: for a hidden edge it returns True but
    # selects the edge in front of it (measured 10-14 mm off in the self-test probe). So edges and faces
    # are found here geometrically (closest point over every edge/face of every solid body) and selected
    # with IEntity.Select4; the selection count is then checked.
    def _bodies(self):
        return list(self.m.GetBodies2(0, True) or [])

    def _ents(self, kind):
        out = []
        for b in self._bodies():
            out += list(_call(b, 'GetEdges' if kind == 'edge' else 'GetFaces') or [])
        return out

    @staticmethod
    def _nearest(ents, pt):
        q = (pt[0] * MM, pt[1] * MM, pt[2] * MM)
        best, second = (1e18, None), (1e18, None)
        for e in ents:
            d = math.dist(tuple(e.GetClosestPointOn(*q))[:3], q) / MM
            if d < best[0]:
                best, second = (d, e), best
            elif d < second[0]:
                second = (d, e)
        return best[1], best[0], second[0]

    def find_edge(self, pt, tol=0.05):
        """The edge through model point pt (mm). Returns (edge, distance mm). Raises if no edge is within
        tol, or if two edges pass through the point (a vertex: pick a point along the edge instead)."""
        return self._find('edge', pt, tol, self._ents('edge'))

    def find_face(self, pt, tol=0.05):
        """The face through model point pt (mm): (face, distance mm)."""
        return self._find('face', pt, tol, self._ents('face'))

    def _find(self, kind, pt, tol, ents):
        e, d, d2 = self._nearest(ents, pt)
        if e is None or d > tol:
            raise FeatureFailed(f'no {kind} within {tol} mm of {tuple(pt)} (nearest {d:.3f} mm)')
        if d2 - d < 1e-3:
            raise FeatureFailed(f'{tuple(pt)} is on two {kind}s (a vertex or edge?) - pick a point inside the {kind}')
        return e, d

    def select_at(self, kind, pts, mark, tol=0.05):
        """Clear the selection, then select the edge/face through each point with `mark`.
        Points on an edge already picked are skipped. Returns [(point, entity)] of what was selected;
        raises FeatureFailed on any miss (and leaves the selection clear)."""
        self.m.ClearSelection2(True)
        ents = self._ents(kind)
        sm = self.m.SelectionManager
        chosen = []
        for pt in pts:
            q = (pt[0] * MM, pt[1] * MM, pt[2] * MM)
            if any(math.dist(tuple(c.GetClosestPointOn(*q))[:3], q) / MM < 1e-4 for _, c in chosen):
                continue                                    # same edge as an earlier point
            try:
                e, _ = self._find(kind, pt, tol, ents)
            except FeatureFailed:
                self.m.ClearSelection2(True)
                raise
            sd = sm.CreateSelectData
            sd.Mark = mark
            if not e.Select4(True, sd):
                self.m.ClearSelection2(True)
                raise FeatureFailed(f'could not select the {kind} at {tuple(pt)}')
            chosen.append((tuple(pt), e))
        n = sm.GetSelectedObjectCount2(-1)
        want_type = 1 if kind == 'edge' else 2
        types_ = [sm.GetSelectedObjectType3(i, -1) for i in range(1, n + 1)]
        if n != len(chosen) or any(t != want_type for t in types_):
            self.m.ClearSelection2(True)
            raise FeatureFailed(f'selection check failed: wanted {len(chosen)} {kind}s, got {n} of types {types_}')
        return chosen

    @staticmethod
    def edge_room(edge):
        """Largest fillet / chamfer size (mm) a STRAIGHT edge between two PLANAR faces can take before it
        eats one of them: the smaller face's extent across the edge, taken from the face's bounding box
        (which can only over-estimate it, so this never rejects a radius that fits). None (= no guard) for
        curved edges or curved faces."""
        try:
            crv = _call(edge, 'GetCurve')
            if not _call(crv, 'IsLine'):
                return None
            d = list(crv.LineParams)[3:6]
            faces = [f for f in (_call(edge, 'GetTwoAdjacentFaces2') or []) if f is not None]
            if len(faces) != 2:
                return None
            room = []
            for f in faces:
                if not _call(_call(f, 'GetSurface'), 'IsPlane'):
                    return None
                n = list(f.Normal)
                w = (n[1] * d[2] - n[2] * d[1], n[2] * d[0] - n[0] * d[2], n[0] * d[1] - n[1] * d[0])
                L = math.sqrt(sum(c * c for c in w))
                b = list(_call(f, 'GetBox'))
                room.append(sum(abs(w[i] / L) * (b[i + 3] - b[i]) for i in range(3)) / MM)
            return min(room)
        except Exception:
            return None

    def _guard_room(self, picked, size, what):
        for pt, e in picked:
            room = self.edge_room(e)
            if room is not None and size >= room - 1e-3:
                self.m.ClearSelection2(True)
                raise FeatureFailed(f'{what} {size} at {pt} does not fit: an adjacent face is only {room:.2f} mm '
                                    f'across (SOLIDWORKS would overflow it and reshape the part WITHOUT an error)')

    def _drop_feature(self, feat):
        """Remove a feature this script just made (used when a feature came out empty)."""
        self.m.ClearSelection2(True)
        n0 = self.m.GetFeatureCount
        if feat.Select2(False, 0):
            self.m.Extension.DeleteSelection2(0)
        self.m.ClearSelection2(True)
        return self.m.GetFeatureCount < n0

    def _checked(self, make, what, expect_sign=0):
        """Run make() (which returns a feature or None) and prove it did something: the feature exists, the
        body count did not change and the volume changed (in the expected direction if expect_sign != 0).
        A feature that changed nothing is removed again. Always leaves the selection clear."""
        v0, n0 = self.volume_cm3(), len(self._bodies())
        try:
            f = make()
        finally:
            self.m.ClearSelection2(True)
        if f is None:
            raise FeatureFailed(what + ': SOLIDWORKS refused it')
        dv = (self.volume_cm3() - v0) * 1000.0                   # mm3
        n1 = len(self._bodies())
        bad = None
        if abs(dv) < 1e-3:
            bad = 'it changed nothing'
        elif expect_sign and dv * expect_sign < 0:
            bad = f'volume went the wrong way ({dv:+.3f} mm3)'
        elif n1 != n0:
            bad = f'body count went {n0} -> {n1}'
        if bad:
            self._drop_feature(f)
            raise FeatureFailed(f'{what}: {bad}')
        return f

    # ================================================================================
    # v3: fillets, chamfers, shell
    # ================================================================================
    def fillet(self, r, pts, propagate=True, tol=0.05):
        """Constant-radius fillet r (mm) on the edges through the model points pts (mm, one point per edge,
        anywhere along it - not on a vertex). propagate=True follows tangent edges (one point rounds a
        whole rounded outline). Raises FeatureFailed if an edge is not found, the radius is wider than an
        adjacent flat face (SOLIDWORKS would silently overflow), or the fillet fails / changes nothing."""
        self._guard_room(self.select_at('edge', pts, 1, tol), r, 'fillet R')
        opts = 2 | 64 | 128 | (1 if propagate else 0)     # uniform radius, attach edges, keep features, propagate
        return self._checked(lambda: self.fm.FeatureFillet3(opts, r * MM, 0, 0, 0, 0, 0,
                                                            None, None, None, None, None, None, None),
                             f'fillet R{r} at {list(pts)}')

    def chamfer(self, d, pts, propagate=True, tol=0.05):
        """45 deg chamfer, d (mm) on each face, on the edges through pts. (Type 1 angle-distance: the
        equal-distance type 16 makes a feature that removes nothing on this install.)"""
        self._guard_room(self.select_at('edge', pts, 1, tol), d, 'chamfer')
        opts = 4 if propagate else 0
        return self._checked(lambda: self.fm.InsertFeatureChamfer(opts, 1, d * MM, math.pi / 4, 0, 0, 0, 0),
                             f'chamfer {d} at {list(pts)}')

    def _safe(self, kind, size, pts, fn, **kw):
        try:
            fn(size, pts, **kw)
            return []
        except Exception as ex:
            if len(pts) == 1:
                self.skipped.append((kind, size, tuple(pts[0]), str(ex)))
                return [self.skipped[-1]]
        out = []
        for pt in pts:
            try:
                fn(size, [pt], **kw)
            except Exception as ex:
                self.skipped.append((kind, size, tuple(pt), str(ex)))
                out.append(self.skipped[-1])
        return out

    def fillet_safe(self, r, pts, propagate=True, tol=0.05):
        """Like fillet(), but never raises: tries all edges together, then one by one, and skips the ones
        that fail. Returns the skipped list [(kind, r, point, reason)]; also appended to self.skipped."""
        return self._safe('fillet', r, pts, self.fillet, propagate=propagate, tol=tol)

    def chamfer_safe(self, d, pts, propagate=True, tol=0.05):
        return self._safe('chamfer', d, pts, self.chamfer, propagate=propagate, tol=tol)

    def shell(self, t, open_pts, outward=False, tol=0.05):
        """Hollow the body to a wall t (mm), removing the faces through the points open_pts (mm)."""
        if not open_pts:
            raise ValueError('shell needs at least one open face')
        self.select_at('face', open_pts, 0, tol)
        n0 = self.m.GetFeatureCount

        def make():
            self.m.InsertFeatureShell(t * MM, outward)
            return self.m.FeatureByPositionReverse(0) if self.m.GetFeatureCount > n0 else None
        return self._checked(make, f'shell {t}', 1 if outward else -1)

    # ================================================================================
    # v3: colour
    # ================================================================================
    def set_color(self, rgb, glow=None, specular=None):
        """Colour of the whole part ('#RRGGBB' or (r, g, b) 0-255), shown in PNGs and the assembly.
        glow = emission (default RENDER_GLOW): SOLIDWORKS' PNG lighting draws a face at only 0.40 (facing the
        camera) / 0.61 (side) / 0.79 (top) of its colour, so warm white came out mid-grey; the glow lifts
        every face by colour x glow so the isometric render averages close to the chosen colour."""
        vals = _mpv(self.m.MaterialPropertyValues, rgb, specular, glow)
        self.m.MaterialPropertyValues = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, vals)
        back = list(self.m.MaterialPropertyValues)
        if max(abs(a - b) for a, b in zip(back[:3], vals[:3])) > 1e-3:
            raise RuntimeError(f'part colour did not stick: {back[:3]}')
        self.color = rgb
        try:
            self.m.GraphicsRedraw2()
        except Exception:
            pass
        return back

    def set_body_color(self, body, rgb, glow=None, specular=None):
        """Colour the bodies of a multibody part whose name starts with `body` (or one body object)."""
        if isinstance(body, str):
            hits = [b for b in self._bodies() if b.Name.startswith(body)]
            if not hits:
                raise RuntimeError('no body named ' + body)
        else:
            hits = [body]
        for b in hits:
            vals = _mpv(b.MaterialPropertyValues2, rgb, specular, glow)
            b.MaterialPropertyValues2 = VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, vals)
        return len(hits)

    # --- checks & output -----------------------------------------------------------
    def volume_cm3(self):
        bodies = self.m.GetBodies2(0, True) or []
        return sum(b.GetMassProperties(1000.0)[3] for b in bodies) * 1e6

    def bbox_mm(self):
        bodies = self.m.GetBodies2(0, True) or []
        xs = [b.GetBodyBox() for b in bodies]
        if not xs:
            return None
        return [round(min(b[i] for b in xs) / MM, 1) if i < 3 else round(max(b[i] for b in xs) / MM, 1)
                for i in range(6)]

    def bbox_exact(self):
        """Bounding box in mm without rounding (GetBodyBox can be slightly loose on curved faces)."""
        xs = [b.GetBodyBox() for b in self._bodies()]
        if not xs:
            return None
        return [min(b[i] for b in xs) / MM if i < 3 else max(b[i] for b in xs) / MM for i in range(6)]

    def save(self, folder, stl=True):
        self.m.SketchManager.AddToDB = False
        self.m.ShowNamedView2('*Isometric', 7)
        self.m.ViewZoomtofit2()
        e = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        w = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
        os.makedirs(folder, exist_ok=True)
        base = os.path.join(folder, self.name)
        # The last subtract leaves the tool body selected, and STL export writes only the
        # selection when there is one - which produced 1.8 mm slivers in print_v1. Always clear.
        self.m.ClearSelection2(True)
        self.m.Extension.SaveAs3(base + '.SLDPRT', 0, 1, NOTHING, NOTHING, e, w)
        if stl:
            self.m.ClearSelection2(True)
            self.m.Extension.SaveAs3(base + '.STL', 0, 1, NOTHING, NOTHING, e, w)
            check_stl(base + '.STL', self.bbox_mm())
        self.m.Extension.SaveAs3(base + '.png', 0, 1, NOTHING, NOTHING, e, w)
        return base

    def save_split(self, part_dir, stl_dir=None, png_dir=None, view='*Isometric', vol_tol=0.05):
        """v3 folder rule: .SLDPRT -> part_dir (SolidWorks files only), .STL -> stl_dir (checked: size AND
        volume must match the model), .png -> png_dir. Returns {'sldprt', 'stl', 'png'} paths."""
        self.m.SketchManager.AddToDB = False
        out = {}

        def save_as(path):
            self.m.ClearSelection2(True)
            e = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            w = VARIANT(pythoncom.VT_BYREF | pythoncom.VT_I4, 0)
            if not self.m.Extension.SaveAs3(path, 0, 1, NOTHING, NOTHING, e, w):
                raise RuntimeError(f'save failed ({e.value}): {path}')
            return path
        os.makedirs(part_dir, exist_ok=True)
        out['sldprt'] = save_as(os.path.join(part_dir, self.name + '.SLDPRT'))
        if png_dir:
            os.makedirs(png_dir, exist_ok=True)
            self.m.ShowNamedView2(view, -1)
            self.m.ViewZoomtofit2()
            out['png'] = save_as(os.path.join(png_dir, self.name + '.png'))
        if stl_dir:
            os.makedirs(stl_dir, exist_ok=True)
            out['stl'] = save_as(os.path.join(stl_dir, self.name + '.STL'))
            check_stl(out['stl'], self.bbox_mm(), self.volume_cm3() * 1000.0 if vol_tol else None, vol_tol or 0.05)
        return out


# ====================================================================================
# v3: 2D outline geometry (pure Python). A loop is a list of segments in the plane's model
# coordinates (u, v):  ('L', p0, p1)  line  |  ('A', centre, p0, p1, ccw)  arc  |  ('C', centre, r)  circle
# ====================================================================================
def _call(obj, name):
    """Some SOLIDWORKS getters come back as methods under dynamic dispatch (body.GetEdges), others as
    values (feature.GetFaces). Return the value either way (never calls a COM object itself)."""
    v = getattr(obj, name)
    return v() if isinstance(v, (types.MethodType, types.FunctionType)) else v


def _as_loops(loops):
    if loops and isinstance(loops[0], tuple) and isinstance(loops[0][0], str):
        return [loops]
    return list(loops)


def circle(c, r):
    return [('C', tuple(c), float(r))]


def rpoly(pts, radii=0.0):
    """Closed polygon (list of (u, v)) with a fillet radius at each vertex (one number for all, or a list).
    Arcs are tangent to both edges. Raises ValueError if two fillets overlap along one edge."""
    P = []
    for p in pts:
        if not P or math.dist(P[-1], p) > 1e-9:
            P.append((float(p[0]), float(p[1])))
    if len(P) > 1 and math.dist(P[0], P[-1]) < 1e-9:
        P.pop()
    n = len(P)
    if n < 3:
        raise ValueError('rpoly needs 3 or more distinct points')
    R = [float(radii)] * n if isinstance(radii, (int, float)) else [float(r) for r in radii]
    if len(R) != n:
        raise ValueError(f'rpoly: {n} points but {len(R)} radii')
    corners = []
    for i in range(n):
        a, p, b = P[i - 1], P[i], P[(i + 1) % n]
        din = _unit(p[0] - a[0], p[1] - a[1])
        dout = _unit(b[0] - p[0], b[1] - p[1])
        cross = din[0] * dout[1] - din[1] * dout[0]
        dot = din[0] * dout[0] + din[1] * dout[1]
        r = R[i]
        if r <= 0 or abs(cross) < 1e-12:
            corners.append((p, p, None, None, 0.0))
            continue
        phi = abs(math.atan2(cross, dot))                  # turning angle at this vertex
        t = r * math.tan(phi / 2)
        t1 = (p[0] - din[0] * t, p[1] - din[1] * t)
        t2 = (p[0] + dout[0] * t, p[1] + dout[1] * t)
        side = 1 if cross > 0 else -1                      # left turn: centre on the left of the incoming edge
        c = (t1[0] - din[1] * r * side, t1[1] + din[0] * r * side)
        corners.append((t1, t2, c, cross > 0, t))
    for i in range(n):
        L = math.dist(P[i], P[(i + 1) % n])
        if corners[i][4] + corners[(i + 1) % n][4] > L + 1e-7:
            raise ValueError(f'rpoly: radii at {P[i]} and {P[(i + 1) % n]} do not fit on that {L:.3f} long edge')
    segs = []
    for i in range(n):
        t1, t2, c, ccw, _ = corners[i]
        if c is not None:
            segs.append(('A', c, t1, t2, ccw))
        nxt = corners[(i + 1) % n][0]
        if math.dist(t2, nxt) > 1e-7:
            segs.append(('L', t2, nxt))
    return segs


def rrect(u0, u1, v0, v1, r=0.0):
    """Rounded rectangle. r = one radius or 4 corner radii in the order (u0,v0), (u1,v0), (u1,v1), (u0,v1)
    (after sorting so u0 < u1, v0 < v1), or a dict {'--': r, '+-': r, '++': r, '-+': r} keyed by the sign
    of (u, v). A radius of half the short side gives a stadium."""
    u0, u1 = sorted((u0, u1))
    v0, v1 = sorted((v0, v1))
    if isinstance(r, dict):
        r = [r.get(k, 0.0) for k in ('--', '+-', '++', '-+')]
    return rpoly([(u0, v0), (u1, v0), (u1, v1), (u0, v1)], r)


def stadium(u0, u1, v0, v1):
    """Pill / stadium filling the box (round ends on the short sides)."""
    return rrect(u0, u1, v0, v1, min(abs(u1 - u0), abs(v1 - v0)) / 2)


def hull2(c1, r1, c2, r2):
    """Outline of the convex hull of two circles (centre, radius) - a capsule with unequal ends."""
    d = math.dist(c1, c2)
    if d <= abs(r1 - r2) + 1e-9:
        raise ValueError('hull2: one circle is inside the other')
    e = ((c2[0] - c1[0]) / d, (c2[1] - c1[1]) / d)
    k = (r1 - r2) / d
    s = math.sqrt(1 - k * k)
    nl = (k * e[0] - s * e[1], k * e[1] + s * e[0])       # left tangent normal
    nr = (k * e[0] + s * e[1], k * e[1] - s * e[0])       # right tangent normal
    P = lambda c, r, n: (c[0] + r * n[0], c[1] + r * n[1])
    return [('L', P(c1, r1, nr), P(c2, r2, nr)),
            ('A', tuple(c2), P(c2, r2, nr), P(c2, r2, nl), True),
            ('L', P(c2, r2, nl), P(c1, r1, nl)),
            ('A', tuple(c1), P(c1, r1, nl), P(c1, r1, nr), True)]


def slot(c1, c2, r):
    """Straight slot: round ends of radius r centred on c1 and c2."""
    return hull2(c1, r, c2, r)


def _unit(x, y):
    L = math.hypot(x, y)
    return (x / L, y / L)


def _arc_sweep(c, p0, p1, ccw):
    a0 = math.atan2(p0[1] - c[1], p0[0] - c[0])
    a1 = math.atan2(p1[1] - c[1], p1[0] - c[0])
    sw = (a1 - a0) % (2 * math.pi) if ccw else -((a0 - a1) % (2 * math.pi))
    if abs(sw) < 1e-12:
        sw = 2 * math.pi if ccw else -2 * math.pi
    return a0, sw


def loop_area(loop):
    """Signed area (mm2) of a closed loop, counter-clockwise positive (Green's theorem on lines + arcs)."""
    s = 0.0
    for seg in loop:
        if seg[0] == 'L':
            (x0, y0), (x1, y1) = seg[1], seg[2]
            s += x0 * y1 - x1 * y0
        elif seg[0] == 'A':
            c, p0, p1 = seg[1], seg[2], seg[3]
            r = math.dist(c, p0)
            _, sw = _arc_sweep(c, p0, p1, seg[4])
            s += r * r * sw + c[0] * (p1[1] - p0[1]) - c[1] * (p1[0] - p0[0])
        else:
            return math.pi * seg[2] ** 2
    return s / 2


def loop_points(loop, step=0.5):
    """Points along a loop about `step` mm apart (for clearance sweeps and checks)."""
    pts = []
    for seg in loop:
        if seg[0] == 'L':
            (x0, y0), (x1, y1) = seg[1], seg[2]
            n = max(1, int(math.dist(seg[1], seg[2]) / step))
            pts += [(x0 + (x1 - x0) * k / n, y0 + (y1 - y0) * k / n) for k in range(n)]
        elif seg[0] == 'A':
            c, p0 = seg[1], seg[2]
            r = math.dist(c, p0)
            a0, sw = _arc_sweep(c, p0, seg[3], seg[4])
            n = max(2, int(abs(sw) * r / step))
            pts += [(c[0] + r * math.cos(a0 + sw * k / n), c[1] + r * math.sin(a0 + sw * k / n)) for k in range(n)]
        else:
            c, r = seg[1], seg[2]
            n = max(8, int(2 * math.pi * r / step))
            pts += [(c[0] + r * math.cos(2 * math.pi * k / n), c[1] + r * math.sin(2 * math.pi * k / n)) for k in range(n)]
    return pts


# ====================================================================================
# v3: colour helpers
# ====================================================================================
def rgb01(rgb):
    """'#RRGGBB' or (r, g, b) 0-255 -> (r, g, b) 0-1."""
    if isinstance(rgb, str):
        h = rgb.lstrip('#')
        return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return tuple(v / 255.0 for v in rgb)


RENDER_GLOW = 0.35      # emission used by the colour helpers (see Part.set_color); 0 = plain SOLIDWORKS look


def _mpv(current, rgb, specular=None, glow=None):
    """MaterialPropertyValues: [R, G, B, ambient, diffuse, specular, shininess, transparency, emission]."""
    vals = list(current) if current else [0.79, 0.82, 0.93, 1.0, 1.0, 0.5, 0.3125, 0.0, 0.0]
    vals[0:3] = rgb01(rgb)
    if specular is not None:
        vals[5] = float(specular)
    vals[8] = float(RENDER_GLOW if glow is None else glow)
    return [float(v) for v in vals]


def set_component_color(comp, rgb, glow=None, specular=None):
    """Colour one assembly component (all configurations). Parts already carry their own colour into the
    assembly, so this is only needed to override one instance."""
    vals = _mpv(comp.MaterialPropertyValues, rgb, specular, glow)
    comp.SetMaterialPropertyValues2(VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, vals), 2, None)
    return list(comp.MaterialPropertyValues or [])


# ====================================================================================
# STL checks
# ====================================================================================
def _stl_triangles(path):
    b = open(path, 'rb').read()
    if b[:5].lower() == b'solid' and b'facet' in b[:400]:
        vs = [tuple(map(float, m)) for m in re.findall(rb'vertex\s+(\S+)\s+(\S+)\s+(\S+)', b)]
        return [vs[i:i + 3] for i in range(0, len(vs) - 2, 3)]
    n = struct.unpack('<I', b[80:84])[0]
    return [[struct.unpack('<3f', b[84 + i * 50 + 12 + k * 12: 84 + i * 50 + 24 + k * 12]) for k in range(3)]
            for i in range(n)]


def stl_size_mm(path):
    """Bounding-box size of an STL file (binary or ASCII), in the file's units (mm)."""
    vs = [v for t in _stl_triangles(path) for v in t]
    return sorted((max(v[a] for v in vs) - min(v[a] for v in vs) for a in range(3)), reverse=True)


def stl_volume_mm3(path):
    """Enclosed volume of an STL mesh (signed tetrahedra; mm3 when the file is in mm)."""
    s = 0.0
    for (ax, ay, az), (bx, by, bz), (cx, cy, cz) in _stl_triangles(path):
        s += ax * (by * cz - bz * cy) - ay * (bx * cz - bz * cx) + az * (bx * cy - by * cx)
    return abs(s) / 6.0


def check_stl(path, bbox, vol_mm3=None, vol_tol=0.05):
    """Refuse to leave a wrong STL behind: its size must match the model's bounding box (0.5 mm), and, when
    vol_mm3 is given, its volume must be within vol_tol (fraction) of the model's (tessellation shaves a
    little off curved faces)."""
    want = sorted((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), reverse=True)
    got = stl_size_mm(path)
    if any(abs(g - w) > 0.5 for g, w in zip(got, want)):
        raise RuntimeError(f'STL size {got} does not match model {want}: {path}')
    if vol_mm3:
        v = stl_volume_mm3(path)
        if abs(v - vol_mm3) > vol_tol * vol_mm3:
            raise RuntimeError(f'STL volume {v:.1f} mm3 does not match model {vol_mm3:.1f} mm3: {path}')


def probe(sw):
    """Find which way FeatureCut4 cuts, by cutting a known pocket and checking the volume."""
    global CUT_FLIP
    for flip in (False, True):
        CUT_FLIP = flip
        p = Part(sw, 'probe')
        p.box(0, 20, 0, 20, 0, 20)
        before = p.volume_cm3()
        try:
            p.box(5, 15, 5, 15, 10, 30, cut=True)      # should remove 10 x 10 x 10 = 1 cm3
            removed = before - p.volume_cm3()
        except Exception:
            removed = 0
        sw.CloseDoc(p.m.GetTitle)
        if abs(removed - 1.0) < 0.01:
            return flip
    raise RuntimeError('could not work out cut direction')


def probe_axes(sw):
    """Check which way the Top Plane sketch maps to model Z, using a body's bounding box."""
    global TOP_ZSIGN
    for sign in (1, -1):
        TOP_ZSIGN = sign
        p = Part(sw, 'axes')
        p.cyl_y(0, 10, 2, 0, 5)
        bb = p.bbox_mm()
        sw.CloseDoc(p.m.GetTitle)
        if bb and abs((bb[2] + bb[5]) / 2 - 10) < 0.2:
            return sign
    raise RuntimeError('could not work out Top Plane orientation')


# ====================================================================================
# v3.1: PRINTED-MASS ESTIMATE FROM THE EXPORTED STL (a small voxel "slicer")
# ====================================================================================
# The slicer settings the v3.1 grams assume (Cura, Ultimaker 2+ Connect, 0.4 nozzle, PLA). The README repeats
# them; change them here and the report follows.
SLICER = dict(layer=0.2, line=0.4, walls=3, top_bottom=0.8, infill=0.15, pattern='gyroid', density=1.24)


def stl_print_estimate(path, axis='z', res=0.25, s=None):
    """Estimate what a slicer lays down for an STL printed with `axis` ('x', 'y' or 'z') as the build direction.

    The mesh is voxelised (columns along the build axis, `res` mm in the layer plane, one voxel per layer).
    In each layer, everything within walls x line of the layer outline is WALL; everything within top_bottom of
    an empty voxel straight above or below is SKIN; the rest is INFILL at s['infill']. The voxel total is scaled
    to the STL's exact volume, so the voxel size only moves material between wall and infill, never the total.
    Returns dict(solid_mm3, printed_mm3, fill, grams, wall_frac, infill_frac)."""
    import numpy as np
    from scipy import ndimage
    s = dict(SLICER, **(s or {}))
    T = np.asarray(_stl_triangles(path), dtype=np.float64)                 # (n, 3 vertices, 3 coords)
    exact = stl_volume_mm3(path)
    order = {'x': (1, 2, 0), 'y': (2, 0, 1), 'z': (0, 1, 2)}[axis]
    T = T[:, :, order]                                                     # build axis last
    lo = T.reshape(-1, 3).min(0) - 3 * res + np.array([1.2345e-4, 2.7183e-4, 0.0])   # odd offsets: rays miss vertices and diagonals
    hi = T.reshape(-1, 3).max(0) + 3 * res
    dz = s['layer']
    nx = int(math.ceil((hi[0] - lo[0]) / res)); ny = int(math.ceil((hi[1] - lo[1]) / res))
    nz = int(math.ceil((hi[2] - lo[2]) / dz)) + 1
    a, b, c = T[:, 0], T[:, 1], T[:, 2]
    den = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    keep = np.abs(den) > 1e-12                                             # walls parallel to the rays add nothing
    a, b, c, den = a[keep], b[keep], c[keep], den[keep]
    xs = np.stack([a[:, 0], b[:, 0], c[:, 0]], 1); ys = np.stack([a[:, 1], b[:, 1], c[:, 1]], 1)
    i0 = np.ceil((xs.min(1) - lo[0]) / res - 0.5).astype(np.int64); i1 = np.floor((xs.max(1) - lo[0]) / res - 0.5).astype(np.int64)
    j0 = np.ceil((ys.min(1) - lo[1]) / res - 0.5).astype(np.int64); j1 = np.floor((ys.max(1) - lo[1]) / res - 0.5).astype(np.int64)
    ni, nj = np.clip(i1 - i0 + 1, 0, None), np.clip(j1 - j0 + 1, 0, None)
    cnt = ni * nj
    tot = int(cnt.sum())
    t = np.repeat(np.arange(len(cnt)), cnt)
    off = np.arange(tot) - np.repeat(np.cumsum(cnt) - cnt, cnt)
    ii = i0[t] + off // nj[t]; jj = j0[t] + off % nj[t]
    px = lo[0] + (ii + 0.5) * res; py = lo[1] + (jj + 0.5) * res
    A, B, C, D = a[t], b[t], c[t], den[t]
    wb = ((px - A[:, 0]) * (C[:, 1] - A[:, 1]) - (py - A[:, 1]) * (C[:, 0] - A[:, 0])) / D
    wc = ((B[:, 0] - A[:, 0]) * (py - A[:, 1]) - (B[:, 1] - A[:, 1]) * (px - A[:, 0])) / D
    wa = 1.0 - wb - wc
    ok = (wa >= 0) & (wb >= 0) & (wc >= 0)
    zhit = (wa * A[:, 2] + wb * B[:, 2] + wc * C[:, 2])[ok]
    col = (ii * ny + jj)[ok]
    o = np.lexsort((zhit, col))                                            # sort by column, then height
    col, zhit = col[o], zhit[o]
    dup = np.r_[False, (col[1:] == col[:-1]) & (np.abs(zhit[1:] - zhit[:-1]) < 1e-6)]   # a ray through a shared edge
    col, zhit = col[~dup], zhit[~dup]
    starts = np.flatnonzero(np.r_[True, col[1:] != col[:-1]])
    rank = np.arange(len(col)) - np.repeat(starts, np.diff(np.r_[starts, len(col)]))
    nxt_same = np.r_[col[1:] == col[:-1], False]
    enter = (rank % 2 == 0) & nxt_same                                     # even-odd rule along each column
    zin, zout, cc = zhit[enter], zhit[np.flatnonzero(enter) + 1], col[enter]
    k0 = np.clip(np.ceil((zin - lo[2]) / dz - 0.5).astype(np.int64), 0, nz)
    k1 = np.clip(np.floor((zout - lo[2]) / dz - 0.5).astype(np.int64) + 1, 0, nz)
    run = k1 > k0
    diff = np.zeros((nx * ny, nz + 1), np.int16)
    np.add.at(diff, (cc[run], k0[run]), 1)
    np.add.at(diff, (cc[run], k1[run]), -1)
    occ = (np.cumsum(diff, axis=1)[:, :nz] > 0).reshape(nx, ny, nz)
    n_occ = int(occ.sum())
    if n_occ == 0:
        raise RuntimeError(f'voxelising found nothing: {path}')
    # skin: within top_bottom of an empty voxel above or below
    kt = max(1, int(round(s['top_bottom'] / dz)))
    csum = np.concatenate([np.zeros((nx, ny, 1), np.int32), np.cumsum(occ, axis=2, dtype=np.int32)], axis=2)
    full = np.zeros_like(occ)
    for k in range(nz):
        lo_k, hi_k = max(0, k - kt), min(nz, k + kt + 1)
        if k - kt >= 0 and k + kt < nz:
            full[:, :, k] = (csum[:, :, hi_k] - csum[:, :, lo_k]) == (hi_k - lo_k)
    skin = occ & ~full
    # walls: within walls x line of the layer outline (2D distance inside each layer)
    wall_w = s['walls'] * s['line']
    wall = np.zeros_like(occ)
    for k in range(nz):
        lay = occ[:, :, k]
        if lay.any():
            wall[:, :, k] = lay & (ndimage.distance_transform_edt(lay) * res <= wall_w + 0.5 * res)
    solid = wall | skin
    n_solid = int(solid.sum())
    n_inf = n_occ - n_solid
    scale = exact / (n_occ * res * res * dz)
    printed = (n_solid + s['infill'] * n_inf) * res * res * dz * scale
    return dict(solid_mm3=exact, printed_mm3=printed, fill=printed / exact, grams=printed * s['density'] / 1000.0,
                wall_frac=n_solid / n_occ, infill_frac=n_inf / n_occ, voxel_scale=scale)


def write_box_stl(path, x0, x1, y0, y1, z0, z1):
    """Binary STL of an axis-aligned box (used to prove stl_print_estimate against hand numbers)."""
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    f = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6),
         (3, 0, 4), (3, 4, 7)]
    with open(path, 'wb') as fh:
        fh.write(b'\0' * 80 + struct.pack('<I', len(f)))
        for t in f:
            fh.write(struct.pack('<3f', 0, 0, 0))
            for k in t:
                fh.write(struct.pack('<3f', *v[k]))
            fh.write(b'\0\0')


def stl_shells(path):
    """Number of separate pieces (connected triangle shells) in an exported STL - the body count as the printer
    will see it. Vertices are matched to 1e-4 mm."""
    import numpy as np
    T = np.asarray(_stl_triangles(path), dtype=np.float64).reshape(-1, 3)
    if len(T) == 0:
        return 0
    key = np.round(T / 1e-4).astype(np.int64)
    _, vid = np.unique(key, axis=0, return_inverse=True)
    vid = vid.reshape(-1, 3)
    parent = np.arange(vid.max() + 1)

    def find(a):
        root = a
        while parent[root] != root:
            root = parent[root]
        while parent[a] != root:
            parent[a], a = root, parent[a]
        return root
    for a, b, c in vid:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[find(rc)] = ra
    return len({find(v) for v in np.unique(vid)})
