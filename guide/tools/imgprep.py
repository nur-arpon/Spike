"""Desk Buddy guide - picture tools.

Everything here works on the SolidWorks renders in config.IMG_DIR and never writes there.
Output goes to guide/src/generated/.

  python guide/tools/imgprep.py --survey     # writes check/mask_survey_<section>.png (which flat colour is where)

Used by build.py:
  Section(name)            the real exploded picture of one body section, with its label masks lined up
  Section.mask(part)       boolean mask of a part's visible pixels (printed or bought)
  make_step_image(...)     highlight parts (orange outline, the rest faded), arrows, labels, crop
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))
import config  # noqa: E402

GEN = os.path.join(config.GUIDE, 'src', 'generated')
CHECK = os.path.join(config.GUIDE, 'check')
REG_CACHE = os.path.join(GEN, 'registration.json')
ACCENT = (242, 120, 30)          # "fit this now" orange
ACCENT2 = (30, 120, 220)         # second highlight (bought part), blue
TARGET_ASPECT = 1.05             # step pictures: width / height they aim for
LABEL_PX = 42                    # label text size in picture pixels
FONT_DIR = r'C:\Windows\Fonts'


def font(size, bold=False):
    for f in (('seguisb.ttf' if bold else 'segoeui.ttf'), ('arialbd.ttf' if bold else 'arial.ttf')):
        try:
            return ImageFont.truetype(os.path.join(FONT_DIR, f), size)
        except OSError:
            continue
    return ImageFont.load_default()


def real_path(sec):
    return os.path.join(config.IMG_DIR, f'Desk Buddy v3.1 - full assembly - section {sec} (exploded).png')


def mask_path(sec, kind):
    tag = {'printed': 'id colours', 'bought': 'id colours B - bought'}[kind]
    return os.path.join(config.MASK_DIR, f'Desk Buddy v3.1 - full assembly - section {sec} ({tag}).png')


# ---------------------------------------------------------------------------------------------------
# registration: the masks were rendered at a different zoom; find scale + shift that lines them up
# ---------------------------------------------------------------------------------------------------
def _edges_real(im):
    g = np.asarray(im.convert('L').filter(ImageFilter.GaussianBlur(1))).astype(float)
    gx = np.abs(np.diff(g, axis=1, prepend=g[:, :1]))
    gy = np.abs(np.diff(g, axis=0, prepend=g[:1]))
    return ((gx + gy) > 18).astype(float)


def _sat(a):
    a = a.astype(int)
    mx, mn = a.max(2), a.min(2)
    return ((mx - mn) / np.maximum(mx, 1) > 0.35) & (mx > 60)


def _edges_mask(a):
    a = a.astype(int)
    d = (np.abs(np.diff(a, axis=1, prepend=a[:, :1])).sum(2) > 60) | \
        (np.abs(np.diff(a, axis=0, prepend=a[:1])).sum(2) > 60)
    return (d & _sat(a)).astype(float)


def _xcorr(A, B):
    c = np.fft.irfft2(np.fft.rfft2(A) * np.conj(np.fft.rfft2(B, s=A.shape)), s=A.shape)
    i = np.unravel_index(np.argmax(c), c.shape)
    return c[i], i


def _register(real, m, scales, k):
    R = _edges_real(real.resize((real.width // k, real.height // k)))
    best = None
    for sc in scales:
        ma = np.asarray(m.resize((int(m.width * sc / k), int(m.height * sc / k)), Image.NEAREST))
        E = _edges_mask(ma)
        H, W = max(R.shape[0], E.shape[0]) * 2, max(R.shape[1], E.shape[1]) * 2
        A = np.zeros((H, W))
        A[:R.shape[0], :R.shape[1]] = R
        v, (dy, dx) = _xcorr(A, E)
        v /= max(E.sum(), 1)
        if best is None or v > best[0]:
            best = (v, sc, dy if dy < H / 2 else dy - H, dx if dx < W / 2 else dx - W)
    return best


def register(sec, kind):
    rp, mp = real_path(sec), mask_path(sec, kind)
    key = f'{sec}|{kind}|{os.path.getsize(rp)}|{os.path.getmtime(rp):.0f}|{os.path.getsize(mp)}|{os.path.getmtime(mp):.0f}'
    cache = json.load(open(REG_CACHE)) if os.path.exists(REG_CACHE) else {}
    if key in cache:
        return cache[key]
    real, m = Image.open(rp).convert('RGB'), Image.open(mp).convert('RGB')
    v, sc, dy, dx = _register(real, m, np.arange(0.70, 1.90, 0.01), 4)
    v, sc, dy, dx = _register(real, m, np.arange(sc - 0.015, sc + 0.015, 0.002), 2)
    T = dict(scale=float(sc), dx=int(dx * 2), dy=int(dy * 2), score=round(float(v), 3))
    cache[key] = T
    os.makedirs(GEN, exist_ok=True)
    json.dump(cache, open(REG_CACHE, 'w'), indent=1)
    return T


def warp(m, T, size):
    sc, dx, dy = T['scale'], T['dx'], T['dy']
    mw, mh = int(m.width * sc), int(m.height * sc)
    ma = np.asarray(m.resize((mw, mh), Image.NEAREST))
    W, H = size
    out = np.full((H, W, 3), 255, np.uint8)
    ys = slice(max(0, dy), min(H, dy + mh))
    xs = slice(max(0, dx), min(W, dx + mw))
    out[ys, xs] = ma[ys.start - dy:ys.stop - dy, xs.start - dx:xs.stop - dx]
    return out


# ---------------------------------------------------------------------------------------------------
class Section:
    """One exploded body section: the real picture plus lined-up masks."""
    _cache = {}

    def __new__(cls, sec):
        if sec not in cls._cache:
            o = super().__new__(cls)
            o._init(sec)
            cls._cache[sec] = o
        return cls._cache[sec]

    def _init(self, sec):
        self.sec = sec
        self.real = Image.open(real_path(sec)).convert('RGB')
        self.size = self.real.size
        self.warped, self.reg = {}, {}
        for kind in ('printed', 'bought'):
            mp = mask_path(sec, kind)
            if os.path.exists(mp):
                self.reg[kind] = register(sec, kind)
                self.warped[kind] = warp(Image.open(mp).convert('RGB'), self.reg[kind], self.size).astype(int)

    def _palette(self, kind):
        """Flat colours of this mask (the configured parts first, then any other big flat colour),
        so a pixel goes to the closest one: shaded faces keep their hue but get darker."""
        key = '_pal_' + kind
        if not hasattr(self, key):
            w = self.warped[kind]
            pal = [tuple(c) for c in config.MASK_PARTS.get(self.sec, {}).get(kind, {}).values()]
            sat = _sat(w)
            cols, counts = np.unique(w[sat], axis=0, return_counts=True)
            for c, n in zip(cols, counts):
                if n > 1500 and max(c) >= 150 and all(np.abs(np.array(c) - q).max() > 12 for q in pal):
                    pal.append(tuple(int(v) for v in c))
            setattr(self, key, pal)
        return getattr(self, key)

    def mask(self, part):
        """Visible pixels of a part named in config.MASK_PARTS[sec] (same hue as its flat colour,
        any shade; each pixel goes to the closest palette colour), closed by 2 px."""
        spec = config.MASK_PARTS.get(self.sec, {})
        for kind in ('printed', 'bought'):
            if part in spec.get(kind, {}) and kind in self.warped:
                w = self.warped[kind].astype(float)
                mx = w.max(2)
                chroma = w / np.maximum(mx, 1)[..., None]
                ok = _sat(self.warped[kind])
                best, bestk = np.full(mx.shape, 9.0), np.full(mx.shape, -1)
                for k, c in enumerate(self._palette(kind)):
                    c = np.array(c, float)
                    cd = np.abs(chroma - c / c.max()).max(2)
                    br = mx / c.max()
                    score = cd + 0.12 * np.abs(np.log(np.maximum(br, 1e-3)))
                    good = ok & (cd < 0.07) & (br > 0.2) & (br < 1.15) & (score < best)
                    best[good], bestk[good] = score[good], k
                target = self._palette(kind).index(tuple(spec[kind][part]))
                m = bestk == target
                img = Image.fromarray((m * 255).astype(np.uint8))
                img = img.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
                return np.asarray(img) > 0
        raise KeyError(f'no mask for {part!r} in section {self.sec!r}')

    def content_box(self, pad=40):
        """Bounding box of everything drawn (edges in the real picture), plus a margin."""
        e = _edges_real(self.real)
        ys, xs = np.nonzero(e)
        W, H = self.size
        return (max(int(np.percentile(xs, 0.2)) - pad, 0), max(int(np.percentile(ys, 0.2)) - pad, 0),
                min(int(np.percentile(xs, 99.8)) + pad, W), min(int(np.percentile(ys, 99.8)) + pad, H))


# ---------------------------------------------------------------------------------------------------
# drawing helpers
# ---------------------------------------------------------------------------------------------------
def _outline(mask, width):
    img = Image.fromarray((mask * 255).astype(np.uint8))
    grown = np.asarray(img.filter(ImageFilter.MaxFilter(2 * width + 1))) > 0
    return grown & ~mask


def arrow(d, p0, p1, colour=ACCENT, width=12, head=38):
    """Thick arrow from p0 to p1 with a white edge."""
    (x0, y0), (x1, y1) = p0, p1
    ang = math.atan2(y1 - y0, x1 - x0)
    bx, by = x1 - head * 0.9 * math.cos(ang), y1 - head * 0.9 * math.sin(ang)
    tri = [(x1, y1), (bx + head * 0.6 * math.sin(ang), by - head * 0.6 * math.cos(ang)),
           (bx - head * 0.6 * math.sin(ang), by + head * 0.6 * math.cos(ang))]
    d.line([(x0, y0), (bx, by)], fill='white', width=width + 8)
    d.polygon(tri, fill='white', outline='white', width=6)
    d.line([(x0, y0), (bx, by)], fill=colour, width=width)
    d.polygon(tri, fill=colour)


def badge(d, xy, text, colour=ACCENT, r=30):
    x, y = xy
    d.ellipse([x - r - 4, y - r - 4, x + r + 4, y + r + 4], fill='white')
    d.ellipse([x - r, y - r, x + r, y + r], fill=colour)
    f = font(int(r * 1.2), True)
    d.text((x, y), text, fill='white', font=f, anchor='mm')


def label(d, anchor, text_xy, text, colour=(40, 40, 40), size=34):
    """Leader line from a part pixel to a text label (text_xy = left or right end of the text)."""
    f = font(size, True)
    ax, ay = anchor
    tx, ty = text_xy
    w = d.textlength(text, font=f)
    left = tx > ax
    x_text = tx if left else tx - w
    d.line([(ax, ay), (tx - (8 if left else -8), ty)], fill='white', width=7)
    d.line([(ax, ay), (tx - (8 if left else -8), ty)], fill=colour, width=3)
    d.ellipse([ax - 7, ay - 7, ax + 7, ay + 7], fill=colour, outline='white', width=2)
    pad = 8
    d.rounded_rectangle([x_text - pad, ty - size * 0.62 - pad / 2, x_text + w + pad, ty + size * 0.62 + pad / 2],
                        radius=8, fill=(255, 255, 255))
    d.text((x_text, ty), text, fill=colour, font=f, anchor='lm')


def wrap(t, n=18):
    """Break a label into lines of about n characters (keeps the label columns narrow)."""
    words, lines, cur = t.split(), [], ''
    for w in words:
        if cur and len(cur) + 1 + len(w) > n:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + ' ' + w).strip()
    lines.append(cur)
    return '\n'.join(lines)


def place_labels(d, items, lw, top, cw, size=40, gap=None):
    """items: [((x, y) picture px, text, 'l'|'r')]. Labels (wrapped to short lines) sit in the side margins
    (lw wide on the left, the rest of the canvas cw on the right), stacked so they never overlap."""
    f = font(size, True)
    line_h = int(size * 1.18)
    for side in ('l', 'r'):
        grp = sorted([(x + lw, y + top, wrap(t)) for (x, y), t, s in items if s == side], key=lambda q: q[1])
        ys, prev_h = [], 0
        for _, y, t in grp:
            h = line_h * (t.count('\n') + 1)
            ys.append(max(y, ys[-1] + prev_h / 2 + h / 2 + size * 0.5) if ys else y)
            prev_h = h
        for (ax, ay, t), ty in zip(grp, ys):
            w = max(d.textlength(line, font=f) for line in t.split('\n'))
            tx = 16 if side == 'l' else cw - 16 - w
            lx = tx + w + 12 if side == 'l' else tx - 12
            col = (40, 40, 40)
            d.line([(ax, ay), (lx, ty)], fill='white', width=7)
            d.line([(ax, ay), (lx, ty)], fill=col, width=3)
            d.ellipse([ax - 7, ay - 7, ax + 7, ay + 7], fill=col, outline='white', width=2)
            nl = t.count('\n') + 1
            d.multiline_text((tx, ty - nl * line_h / 2), t, fill=col, font=f, anchor='la',
                             spacing=line_h - size, align='right' if side == 'l' else 'left')


def label_margins(labels, side_index):
    """Width of the left and right label columns: the longest wrapped label line on that side plus room for the leader."""
    f = font(LABEL_PX, True)
    d = ImageDraw.Draw(Image.new('RGB', (10, 10)))

    def width(side):
        ws = [d.textlength(line, font=f) for l in labels if l[2] == side for line in wrap(l[1]).split('\n')]
        return int(max(ws) + 80) if ws else 0
    return width('l'), width('r')


def anchor_of(mask):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return None
    cx, cy = xs.mean(), ys.mean()
    i = np.argmin((xs - cx) ** 2 + (ys - cy) ** 2)
    return int(xs[i]), int(ys[i])


def bbox_of(mask, pad=0):
    ys, xs = np.nonzero(mask)
    return int(xs.min()) - pad, int(ys.min()) - pad, int(xs.max()) + pad, int(ys.max()) + pad


# ---------------------------------------------------------------------------------------------------
# step pictures
# ---------------------------------------------------------------------------------------------------
def make_step_image(out, sec, hi=(), hi2=(), fade=0.55, arrows=(), labels=(), badges=(), crop=None,
                    max_w=1800):
    """Real exploded picture of `sec` with:
      hi      parts outlined in orange (the part fitted in this step), hi2 outlined in blue
      fade    how much the other pixels are lightened toward white (0 = not at all)
      arrows  [(part, (dx, dy))]: arrow starting at the part's anchor, pointing along (dx, dy) in px
              or [((x0, y0), (x1, y1))] in picture pixels
      labels  [(part or (x, y), text, 'l'|'r', dy)]: leader line to a label at the left/right edge
      badges  [(part or (x, y), '1')]
      crop    None (whole drawing), 'hi' (around the highlighted parts), or (x0, y0, x1, y1)
    Returns the output path, or None if a part mask is missing (the caller falls back)."""
    S = Section(sec)
    base = np.asarray(S.real).astype(float)
    keep = np.zeros(base.shape[:2], bool)
    masks = {}
    for p in list(hi) + list(hi2):
        masks[p] = S.mask(p)
        keep |= masks[p]
    if fade and (hi or hi2):
        base[~keep] = base[~keep] * (1 - fade) + 255 * fade
    img = base.astype(np.uint8)
    for p in hi:
        img[_outline(masks[p], 5)] = ACCENT
    for p in hi2:
        img[_outline(masks[p], 5)] = ACCENT2
    im = Image.fromarray(img)
    d = ImageDraw.Draw(im)

    def where(x):
        if isinstance(x, str):
            return anchor_of(masks[x] if x in masks else S.mask(x))
        return x
    for a in arrows:
        if isinstance(a[0], str):
            p0 = where(a[0])
            p1 = (p0[0] + a[1][0], p0[1] + a[1][1])
        else:
            p0, p1 = a
        arrow(d, p0, p1)
    # crop first so labels can sit at the crop edges
    if crop is None:
        box = S.content_box()
    elif isinstance(crop, list):
        u = np.zeros_like(keep)
        for p in crop:
            u |= masks[p] if p in masks else S.mask(p)
        x0, y0, x1, y1 = bbox_of(u, 90)
        box = (max(x0, 0), max(y0, 0), min(x1, S.size[0]), min(y1, S.size[1]))
    elif crop == 'hi':
        u = np.zeros_like(keep)
        for m in masks.values():
            u |= m
        x0, y0, x1, y1 = bbox_of(u, 170)
        box = (max(x0, 0), max(y0, 0), min(x1, S.size[0]), min(y1, S.size[1]))
    else:
        box = crop
    x0, y0, x1, y1 = box
    labels = [(p, t, (s if s in ('l', 'r') else ('l' if where(p)[0] < (x0 + x1) / 2 else 'r')), dy)
              for p, t, s, dy in labels]
    # widen for labels
    lw, rw = label_margins(labels, 1)
    want_h = int((x1 - x0 + lw + rw) / TARGET_ASPECT)
    if y1 - y0 < want_h:                      # show more of the scene above and below, never less
        extra = want_h - (y1 - y0)
        y0 = max(0, y0 - extra // 2)
        y1 = min(S.size[1], y0 + want_h)
        y0 = max(0, y1 - want_h)
        box = (x0, y0, x1, y1)
    canvas = Image.new('RGB', (x1 - x0 + lw + rw, y1 - y0), 'white')
    canvas.paste(im.crop(box), (lw, 0))
    d2 = ImageDraw.Draw(canvas)
    items = []
    for part, text, side, dy in labels:
        ax, ay = where(part)
        items.append(((ax - x0, ay - y0), text, side))
    place_labels(d2, items, lw, 0, canvas.width, size=LABEL_PX)
    for part, text in badges:
        bx, by = where(part)
        badge(d2, (bx - x0 + lw, by - y0), text)
    if canvas.width > max_w:
        canvas = canvas.resize((max_w, int(canvas.height * max_w / canvas.width)), Image.LANCZOS)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    canvas.save(out, optimize=True)
    return out


def autocrop(path, out, pad=30, max_w=1800, box=None):
    """Crop a render to its drawing (edges), keep the gradient background."""
    im = Image.open(path).convert('RGB')
    if box is None:
        e = _edges_real(im)
        ys, xs = np.nonzero(e)
        box = (max(int(np.percentile(xs, 0.1)) - pad, 0), max(int(np.percentile(ys, 0.1)) - pad, 0),
               min(int(np.percentile(xs, 99.9)) + pad, im.width), min(int(np.percentile(ys, 99.9)) + pad, im.height))
    im = im.crop(box)
    if im.width > max_w:
        im = im.resize((max_w, int(im.height * max_w / im.width)), Image.LANCZOS)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    im.save(out, optimize=True)
    return out


# ---------------------------------------------------------------------------------------------------
def survey():
    """Write check/mask_survey_<n>.png: every flat colour in each mask, numbered on the real picture."""
    os.makedirs(CHECK, exist_ok=True)
    for sec in config.MASK_PARTS:
        S = Section(sec)
        panels = []
        for kind in ('printed', 'bought'):
            if kind not in S.warped:
                continue
            w = S.warped[kind]
            flat = w.reshape(-1, 3)
            sat = _sat(w).reshape(-1)
            cols, counts = np.unique(flat[sat], axis=0, return_counts=True)
            order = [i for i in np.argsort(-counts) if counts[i] > 150]
            base = (np.asarray(S.real).astype(float) * 0.35 + 255 * 0.65).astype(np.uint8)
            im = Image.fromarray(base)
            d = ImageDraw.Draw(im)
            print(f'{sec} [{kind}] registration {S.reg[kind]}')
            n = 0
            for i in order:
                c = cols[i]
                m = np.abs(w - c).max(2) <= 10
                if m.sum() < 150:
                    continue
                arr = np.asarray(im).copy()
                arr[m] = c
                im = Image.fromarray(arr)
                d = ImageDraw.Draw(im)
                a = anchor_of(m)
                d.text((a[0] + 8, a[1]), f'{n}', fill='black', font=font(40, True), stroke_width=4, stroke_fill='white')
                print(f'   {n:2d}  rgb {tuple(int(v) for v in c)}  {int(m.sum()):6d} px  at {a}')
                n += 1
            panels.append(im.crop(S.content_box()))
        W = sum(p.width for p in panels)
        H = max(p.height for p in panels)
        sheet = Image.new('RGB', (W, H), 'white')
        x = 0
        for p in panels:
            sheet.paste(p, (x, 0))
            x += p.width
        sheet.save(os.path.join(CHECK, f'mask_survey_{sec.split()[0]}.png'))


if __name__ == '__main__':
    if '--survey' in sys.argv:
        survey()
