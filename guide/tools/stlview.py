"""Desk Buddy guide - make extra views from the printed-part STLs (cad/print_v3_1_stl, read only).

The STLs are in assembly coordinates (mm): x = robot's left (+) / right (-), y = up, z = front (+) / back (-).
So parts render in place, can be moved apart (explode offsets), and any point from the CAD script can be
labelled exactly. Parts are coloured from config.COLOURS, so the pictures follow the colour map.

Orthographic, painter's algorithm with Lambert shading at 2x supersampling, plus outlines where the part or
the surface direction changes (the CAD "shaded with edges" look). No SolidWorks needed.
"""
import glob
import math
import os
import struct
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))
sys.path.insert(0, HERE)
import config  # noqa: E402
import imgprep  # noqa: E402

STL_DIR = os.path.join(config.PROJECT, 'cad', 'print_v3_1_stl')
_cache = {}


def load(name):
    if name in _cache:
        return _cache[name]
    hits = [p for p in glob.glob(os.path.join(STL_DIR, name + '*.STL'))
            if os.path.basename(p)[len(name)] in ' .']
    if not hits:
        raise FileNotFoundError(name)
    b = open(hits[0], 'rb').read()
    n = struct.unpack('<I', b[80:84])[0]
    a = np.frombuffer(b[84:84 + n * 50], dtype=np.dtype([('n', '<3f4'), ('v', '<9f4'), ('a', '<u2')]))
    v = a['v'].reshape(-1, 3, 3).astype(np.float64)
    _cache[name] = v
    return v


def hex_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def colour_of(key):
    if isinstance(key, tuple):
        return key
    if key in config.COLOURS:
        return hex_rgb(config.COLOURS[key]['hex'])
    return {'bought': (150, 160, 180), 'ghost': (225, 225, 228)}.get(key, (200, 200, 200))


def subdivide(V, ID, C, max_edge=4.0, rounds=6):
    """Split long triangles into four until every edge is under max_edge mm, so the painter's sort
    (by each triangle's mean depth) does not draw a big flat face over a small part in front of it."""
    for _ in range(rounds):
        e = np.max(np.linalg.norm(V - np.roll(V, 1, axis=1), axis=2), axis=1)
        big = e > max_edge
        if not big.any():
            break
        B = V[big]
        a, b, c = B[:, 0], B[:, 1], B[:, 2]
        ab, bc, ca = (a + b) / 2, (b + c) / 2, (c + a) / 2
        new = np.concatenate([np.stack([a, ab, ca], 1), np.stack([ab, b, bc], 1), np.stack([ca, bc, c], 1),
                              np.stack([ab, bc, ca], 1)])
        V = np.concatenate([V[~big], new])
        ID = np.concatenate([ID[~big], np.tile(ID[big], 4)])
        C = np.concatenate([C[~big], np.tile(C[big], (4, 1))])
    return V, ID, C


class Camera:
    def __init__(self, direction, up=(0, 1, 0)):
        f = np.array(direction, float)
        f /= np.linalg.norm(f)
        r = np.cross(f, np.array(up, float))
        if np.linalg.norm(r) < 1e-6:
            r = np.cross(f, np.array((0, 0, 1.0)))
        r /= np.linalg.norm(r)
        u = np.cross(r, f)
        self.f, self.r, self.u = f, r, u

    def project(self, p):
        p = np.asarray(p, float)
        return np.stack([p @ self.r, -(p @ self.u), p @ self.f], -1)


def iso(az_deg, el_deg):
    """Camera looking at the robot from azimuth az (0 = from the front, 90 = from the robot's left side)
    and elevation el (positive = from above)."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    eye = np.array([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])
    return Camera(-eye)


def render(parts, cam, width=1600, margin=40, labels=(), badges=(), arrows=(), hi=(), light=None,
           out=None, title=None, extra_pts=()):
    """parts: [(stl name, colour key, (dx, dy, dz) offset)]; hi: names outlined in orange.
    labels: [((x, y, z), text, 'l'|'r')]; badges: [((x, y, z), '1')]; arrows: [((x,y,z), (x,y,z))] in mm."""
    tris, ids, cols = [], [], []
    for k, (name, ckey, off) in enumerate(parts):
        v = load(name) + np.array(off, float)
        tris.append(v)
        ids.append(np.full(len(v), k))
        if ckey in config.COLOURS:            # printed part: its colour comes from config.PART_COLOUR_RULES
            ckey = config.part_colour(name)
        cols.append(np.tile(np.array(colour_of(ckey), float), (len(v), 1)))
    V = np.concatenate(tris)
    ID = np.concatenate(ids)
    C = np.concatenate(cols)
    V, ID, C = subdivide(V, ID, C)
    P = cam.project(V.reshape(-1, 3)).reshape(-1, 3, 3)
    # face normals in camera space (winding: outward for SolidWorks STL)
    n = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    ln = np.linalg.norm(n, axis=1)
    keep = ln > 1e-12
    n[keep] /= ln[keep, None]
    facing = (n @ cam.f) < 0
    sel = keep & facing
    V, P, ID, C, n = V[sel], P[sel], ID[sel], C[sel], n[sel]
    # screen scale
    pts2 = P[:, :, :2].reshape(-1, 2)
    ext = [np.asarray(cam.project(np.array(p)))[:2] for p in extra_pts]
    allp = np.vstack([pts2] + ([np.array(ext)] if ext else []))
    lo, hi_ = allp.min(0), allp.max(0)
    ss = 2
    s = (width - 2 * margin) / max(hi_[0] - lo[0], 1e-6)
    height = int((hi_[1] - lo[1]) * s + 2 * margin)
    W2, H2 = width * ss, height * ss

    def to_px(q):
        return ((q[..., 0] - lo[0]) * s + margin) * ss, ((q[..., 1] - lo[1]) * s + margin) * ss

    X, Y = to_px(P)
    depth = P[:, :, 2].mean(1)
    order = np.argsort(-depth)
    L = np.array(light, float) if light is not None else (-cam.f * 0.75 + cam.u * 0.55 - cam.r * 0.35)
    L /= np.linalg.norm(L)
    lam = np.clip(n @ L, 0, 1)
    shade = 0.42 + 0.58 * lam
    # a little rim light from the camera side keeps dark parts readable
    shade += 0.12 * np.clip(-(n @ cam.f), 0, 1)
    rgb = np.clip(C * shade[:, None], 0, 255).astype(np.uint8)
    img = Image.new('RGB', (W2, H2), 'white')
    idb = Image.new('I', (W2, H2), 0)
    nb = Image.new('RGB', (W2, H2), (0, 0, 0))
    ob = Image.new('I', (W2, H2), 0)
    d, di, dn, do = ImageDraw.Draw(img), ImageDraw.Draw(idb), ImageDraw.Draw(nb), ImageDraw.Draw(ob)
    nq = ((n * 0.5 + 0.5) * 255).astype(np.uint8)
    # plane offset (n . p) of each triangle, 0.05 mm steps: parallel faces at different heights (a pocket
    # seen straight on) get an outline even though their normals match
    off = np.round((n * V[:, 0]).sum(1) * 20).astype(np.int64)
    for i in order:
        poly = [(X[i, 0], Y[i, 0]), (X[i, 1], Y[i, 1]), (X[i, 2], Y[i, 2])]
        c = tuple(int(v) for v in rgb[i])
        d.polygon(poly, fill=c, outline=c)
        di.polygon(poly, fill=int(ID[i]) + 1, outline=int(ID[i]) + 1)
        nc = tuple(int(v) for v in nq[i])
        dn.polygon(poly, fill=nc, outline=nc)
        do.polygon(poly, fill=int(off[i]), outline=int(off[i]))
    # outlines: part boundaries and creases
    ida = np.asarray(idb).astype(np.int64)
    na = np.asarray(nb).astype(float) / 127.5 - 1
    oa = np.asarray(ob).astype(np.int64)
    e = np.zeros(ida.shape, bool)
    for ax in (0, 1):
        e |= np.diff(ida, axis=ax, prepend=np.take(ida, [0], axis=ax)) != 0
        dot = (na * np.roll(na, 1, axis=ax)).sum(2)
        e |= dot < math.cos(math.radians(35))
        e |= (dot > 0.9995) & (np.abs(oa - np.roll(oa, 1, axis=ax)) > 8)
    e[:1, :] = e[-1:, :] = False
    e[:, :1] = e[:, -1:] = False
    arr = np.asarray(img).copy()
    arr[e] = (arr[e] * 0.35).astype(np.uint8)
    # highlight outline
    names = [p[0] for p in parts]
    for h in hi:
        k = names.index(h) + 1
        m = ida == k
        grown = np.asarray(Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(11))) > 0
        ring = grown & ~m
        arr[ring] = imgprep.ACCENT
    img = Image.fromarray(arr).resize((width, height), Image.LANCZOS)

    def px(p3):
        q = cam.project(np.array(p3, float))
        x, y = to_px(q)
        return x / ss, y / ss
    # labels in side margins
    labels = [(p, t, s if s in ('l', 'r') else ('l' if px(p)[0] < width / 2 else 'r')) for p, t, s in labels]
    lw, rw = imgprep.label_margins(labels, 1)
    top = 70 if title else 0
    canvas = Image.new('RGB', (width + lw + rw, height + top), 'white')
    canvas.paste(img, (lw, top))
    dc = ImageDraw.Draw(canvas)
    for a0, a1 in arrows:
        x0, y0 = px(a0)
        x1, y1 = px(a1)
        imgprep.arrow(dc, (x0 + lw, y0 + top), (x1 + lw, y1 + top))
    place_labels(dc, [(px(p), t, side) for p, t, side in labels], lw, top, canvas.width, size=imgprep.LABEL_PX)
    for p, t in badges:
        x, y = px(p)
        imgprep.badge(dc, (x + lw, y + top), t)
    if title:
        dc.text((lw + 10, 16), title, fill=(60, 60, 60), font=imgprep.font(36, True))
    if out:
        os.makedirs(os.path.dirname(out), exist_ok=True)
        canvas.save(out, optimize=True)
    return canvas


place_labels = imgprep.place_labels
