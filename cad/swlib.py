"""Small helper layer over the SOLIDWORKS COM API for building printable parts.

All sizes are millimetres. Axes: X = left/right, Y = up, Z = forward (Front Plane = XY).
Every shape is axis-aligned, which keeps the API calls simple and predictable.
"""
import os, pythoncom, win32com.client
from win32com.client import VARIANT

MM = 0.001
NOTHING = VARIANT(pythoncom.VT_DISPATCH, None)
CUT_FLIP = False          # set by probe(): which way a cut goes from its start plane
TOP_ZSIGN = 1             # Top Plane sketch Y = -model Z * TOP_ZSIGN (set by probe_axes)


def app():
    a = win32com.client.Dispatch('SldWorks.Application')
    a.Visible = True
    return a


class Part:
    def __init__(self, sw, name):
        self.sw = sw
        self.name = name
        self.m = sw.NewDocument(sw.GetUserPreferenceStringValue(8), 0, 0, 0)
        self.m.SketchManager.AddToDB = True
        self.fm = self.m.FeatureManager
        self.merge = True          # False: every solid becomes its own body (used for bought-part models)
        self.last = None

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
            f = c
        self.last = f
        return f

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


def stl_size_mm(path):
    """Bounding-box size of an STL file (binary or ASCII), in the file's units (mm)."""
    import re, struct
    b = open(path, 'rb').read()
    if b[:5].lower() == b'solid' and b'facet' in b[:400]:
        vs = [tuple(map(float, m)) for m in re.findall(rb'vertex\s+(\S+)\s+(\S+)\s+(\S+)', b)]
    else:
        n = struct.unpack('<I', b[80:84])[0]
        vs = [struct.unpack('<3f', b[84 + i * 50 + 12 + k * 12: 84 + i * 50 + 24 + k * 12])
              for i in range(n) for k in range(3)]
    return sorted((max(v[a] for v in vs) - min(v[a] for v in vs) for a in range(3)), reverse=True)


def check_stl(path, bbox):
    """Refuse to leave a wrong STL behind: its size must match the model's bounding box."""
    want = sorted((bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]), reverse=True)
    got = stl_size_mm(path)
    if any(abs(g - w) > 0.5 for g, w in zip(got, want)):
        raise RuntimeError(f'STL size {got} does not match model {want}: {path}')


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
