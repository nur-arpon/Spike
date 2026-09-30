"""compare.py -- golden-image test, compare side.

Compares the JS renders (test/out/raw/js) with the C++ renders (test/out/raw/cpp) case by case and writes
  test/out/golden_report.txt        one line per case + the verdict
  test/out/diff_sheet_NN.png        side-by-side sheets: JS | C++ | diff (every case, half size)
  test/out/diff_worst.png           the 8 worst cases at full size
Metrics per case (8-bit RGB, max over channels):
  mean      mean absolute difference over all pixels
  aa        pixels differing by more than 24 levels (anti-aliasing and sub-pixel differences land here)
  shape     pixels that differ by more than 40 levels from EVERY pixel of the other image's 3x3
            neighbourhood -- a shape or position error, not explained by a <= 1 px edge shift. This is
            the pass/fail metric.
PASS when shape <= SHAPE_MAX pixels for every case.

Needs Pillow + numpy (software/laptop/.venv has both). Run:
  software\\laptop\\.venv\\Scripts\\python.exe software\\firmware\\test\\compare.py
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

W, H = 480, 272
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
JS = os.path.join(OUT, "raw", "js")
CPP = os.path.join(OUT, "raw", "cpp")
SHAPE_TOL = 40
AA_TOL = 24
SHAPE_MAX = 40  # pixels per 130,560-pixel frame (0.03 %)


def load(path):
    a = np.frombuffer(open(path, "rb").read(), dtype=np.uint8)
    return a.reshape(H, W, 3).astype(np.int16)


def neighbourhood_min_diff(a, b):
    """For each pixel of a: min over the 3x3 neighbourhood in b of the max-channel |a - b|."""
    pad = np.pad(b, ((1, 1), (1, 1), (0, 0)), mode="edge")
    best = None
    for dy in range(3):
        for dx in range(3):
            d = np.abs(a - pad[dy:dy + H, dx:dx + W]).max(axis=2)
            best = d if best is None else np.minimum(best, d)
    return best


def metrics(js, cpp):
    d = np.abs(js - cpp).max(axis=2)
    shape = (neighbourhood_min_diff(js, cpp) > SHAPE_TOL) | (neighbourhood_min_diff(cpp, js) > SHAPE_TOL)
    return {
        "mean": float(d.mean()),
        "aa": int((d > AA_TOL).sum()),
        "shape": int(shape.sum()),
        "diff": d,
        "shape_mask": shape,
    }


def diff_image(m):
    d = np.clip(m["diff"].astype(np.float32) * 4, 0, 255).astype(np.uint8)
    img = np.zeros((H, W, 3), np.uint8)
    img[..., 0] = d
    img[..., 1] = (d // 3)
    img[m["shape_mask"]] = (255, 0, 255)
    return Image.fromarray(img)


def to_img(a):
    return Image.fromarray(a.astype(np.uint8))


def main():
    names = sorted(f[:-4] for f in os.listdir(JS) if f.endswith(".rgb"))
    if not names:
        print("no JS renders; run test/js_cases.js first")
        return 2
    order = []
    with open(os.path.join(OUT, "cases.txt")) as f:
        for line in f:
            if line.startswith("#") or not line.strip():
                continue
            order.append(line.split(" ", 1)[0])
    names = [n for n in order if n in set(names)]
    results = []
    missing = []
    for n in names:
        cp = os.path.join(CPP, n + ".rgb")
        if not os.path.exists(cp):
            missing.append(n)
            continue
        js, cpp = load(os.path.join(JS, n + ".rgb")), load(cp)
        m = metrics(js, cpp)
        results.append((n, js, cpp, m))

    # ---- report ----
    fails = [r for r in results if r[3]["shape"] > SHAPE_MAX]
    lines = []
    lines.append("golden-image test: JS face_v2 renderer (@napi-rs/canvas) vs C++ spike_face (VectorGfx)")
    lines.append("cases: %d   missing C++ renders: %d   shape tolerance: %d levels, >%d px fails"
                 % (len(results), len(missing), SHAPE_TOL, SHAPE_MAX))
    means = [r[3]["mean"] for r in results]
    shapes = [r[3]["shape"] for r in results]
    aas = [r[3]["aa"] for r in results]
    lines.append("mean abs diff: avg %.3f, max %.3f levels | AA pixels (>%d): avg %.0f, max %d | shape pixels: avg %.2f, max %d"
                 % (np.mean(means), np.max(means), AA_TOL, np.mean(aas), np.max(aas), np.mean(shapes), np.max(shapes)))
    lines.append("VERDICT: %s (%d of %d cases over the shape limit)"
                 % ("PASS" if not fails and not missing else "FAIL", len(fails), len(results)))
    lines.append("")
    lines.append("%-40s %8s %7s %6s" % ("case", "mean", "aa_px", "shape"))
    for n, _, _, m in results:
        lines.append("%-40s %8.3f %7d %6d%s" % (n, m["mean"], m["aa"], m["shape"], "  FAIL" if m["shape"] > SHAPE_MAX else ""))
    for n in missing:
        lines.append("%-40s   MISSING C++ RENDER" % n)
    open(os.path.join(OUT, "golden_report.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines[:4]))

    # ---- sheets ----
    for f in os.listdir(OUT):
        if f.startswith("diff_sheet_") and f.endswith(".png"):
            os.remove(os.path.join(OUT, f))
    cw, ch = W // 2, H // 2
    per_row, rows = 2, 10
    label_h, gap = 14, 10
    case_w = cw * 3 + 4
    per_sheet = per_row * rows
    for s in range(0, len(results), per_sheet):
        chunk = results[s:s + per_sheet]
        sheet = Image.new("RGB", (per_row * case_w + (per_row + 1) * gap, 24 + rows * (ch + label_h + gap)), (27, 30, 36))
        dr = ImageDraw.Draw(sheet)
        dr.text((gap, 6), "JS | C++ | diff x4 (magenta = shape error)   sheet %d" % (s // per_sheet + 1), fill=(230, 230, 230))
        for i, (n, js, cpp, m) in enumerate(chunk):
            x = gap + (i % per_row) * (case_w + gap)
            y = 24 + (i // per_row) * (ch + label_h + gap)
            sheet.paste(to_img(js).resize((cw, ch), Image.LANCZOS), (x, y + label_h))
            sheet.paste(to_img(cpp).resize((cw, ch), Image.LANCZOS), (x + cw + 2, y + label_h))
            sheet.paste(diff_image(m).resize((cw, ch), Image.BOX), (x + 2 * cw + 4, y + label_h))
            col = (255, 90, 90) if m["shape"] > SHAPE_MAX else (170, 178, 190)
            dr.text((x, y), "%s  mean %.2f  shape %d" % (n, m["mean"], m["shape"]), fill=col)
        sheet.save(os.path.join(OUT, "diff_sheet_%02d.png" % (s // per_sheet + 1)), optimize=True)

    worst = sorted(results, key=lambda r: (r[3]["shape"], r[3]["mean"]), reverse=True)[:8]
    sheet = Image.new("RGB", (W * 3 + 4 * 10, 10 + len(worst) * (H + 26)), (27, 30, 36))
    dr = ImageDraw.Draw(sheet)
    for i, (n, js, cpp, m) in enumerate(worst):
        y = 10 + i * (H + 26)
        dr.text((10, y), "%s   mean %.3f   aa %d   shape %d   (JS | C++ | diff x4)" % (n, m["mean"], m["aa"], m["shape"]), fill=(230, 230, 230))
        sheet.paste(to_img(js), (10, y + 14))
        sheet.paste(to_img(cpp), (20 + W, y + 14))
        sheet.paste(diff_image(m), (30 + 2 * W, y + 14))
    sheet.save(os.path.join(OUT, "diff_worst.png"), optimize=True)
    print("sheets written to", OUT)
    return 1 if (fails or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
