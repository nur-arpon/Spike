"""Desk Buddy Assembly Guide - build the PDF.

    python guide/build.py            # pictures + HTML + PDF (two passes for the contents page) + check sheets
    python guide/build.py --fast     # reuse pictures already in src/generated (text-only changes)
    python guide/build.py --no-check # skip the page renders and contact sheets

Reads:  src/config.py (image folder, colour names), src/data_*.py, src/steps_*.py, src/sections/*.html
Writes: src/generated/ (pictures), src/guide.html, the PDF (config.OUTPUT_PDF), check/ (page renders)
"""
import datetime
import glob
import os
import re
import shutil
import subprocess
import sys
import time

GUIDE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(GUIDE, 'src')
sys.path.insert(0, SRC)
sys.path.insert(0, os.path.join(GUIDE, 'tools'))
import config  # noqa: E402
import data_parts as DP  # noqa: E402
import data_trouble  # noqa: E402
import diagrams  # noqa: E402
import render_html as R  # noqa: E402
from steps_body import STEPS_A, STEPS_B  # noqa: E402
from steps_head import STEPS_C  # noqa: E402
from steps_legs import STEPS_D, STEPS_E, STEPS_F  # noqa: E402
from steps_close import STEPS_G, STEPS_P  # noqa: E402

GEN = os.path.join(SRC, 'generated')
CHECK = os.path.join(GUIDE, 'check')
STEPS = {'A': STEPS_A, 'B': STEPS_B, 'C': STEPS_C, 'D': STEPS_D, 'E': STEPS_E, 'F': STEPS_F, 'G': STEPS_G, 'P': STEPS_P}
FAST = '--fast' in sys.argv
LOG = []


def log(*a):
    s = ' '.join(str(x) for x in a)
    print(s, flush=True)
    LOG.append(s)


def rel(p):
    return os.path.relpath(p, SRC).replace('\\', '/')


# ------------------------------------------------------------------------------------------------ pictures
def img_file(name):
    return os.path.join(config.IMG_DIR, name)


def cropped(src_name, out_name, max_w=1800):
    import imgprep
    out = os.path.join(GEN, out_name)
    if not (FAST and os.path.exists(out)):
        imgprep.autocrop(img_file(src_name), out, max_w=max_w)
    return rel(out)


def step_image(s):
    import imgprep
    import stlview
    if not s.get('img'):
        return None
    out = os.path.join(GEN, f'step_{s["id"].replace(".", "_")}.png')
    if FAST and os.path.exists(out):
        return rel(out)
    kind = s['img'][0]
    try:
        if kind == 'sec':
            _, sec, spec = s['img']
            spec = dict(spec)
            labels = [(p, R.colours(t), side, dy) for p, t, side, dy in spec.pop('labels', [])]
            imgprep.make_step_image(out, sec, labels=labels, **spec)
        elif kind == 'stl':
            spec = dict(s['img'][1])
            az, el = spec.pop('cam')
            width = spec.pop('width', 1500)
            labels = [(p, R.colours(t), side) for p, t, side in spec.pop('labels', [])]
            stlview.render(spec.pop('parts'), stlview.iso(az, el), width=width, labels=labels, out=out, **spec)
        elif kind == 'render':
            _, name, box = s['img']
            imgprep.autocrop(img_file(name), out, box=box)
    except Exception as ex:  # a missing mask or render must not stop the whole guide
        log(f'  !! step {s["id"]}: picture failed ({ex}); using the plain section picture')
        return None
    return rel(out)


def pictures():
    os.makedirs(GEN, exist_ok=True)
    P = {}
    P['cover'] = cropped('Desk Buddy v3.1 - full assembly - iso.png', 'cover.png', 2000)
    P['iso_small'] = P['cover']
    P['bought'] = cropped('BOUGHT - every purchased part in place.png', 'bought.png')
    P['inside'] = cropped('Desk Buddy v3.1 - full assembly - inside (shells see-through).png', 'inside.png')
    for n, sec in enumerate(['1 Body', '2 Lid', '3 Head', '4 Leg'], 1):
        P[f'sec{n}'] = cropped(f'Desk Buddy v3.1 - full assembly - section {sec} (exploded).png', f'sec{n}.png')
    parts = {}
    for row in DP.PRINTED:
        parts[row[7]] = cropped(row[7], 'parts/' + re.sub(r'[^A-Za-z0-9_]+', '_', row[0]) + '.png', 520)
    for row in DP.TEST_PRINTS:
        parts[row[3]] = cropped(row[3], 'parts/' + row[0] + '.png', 520)
    P['parts'] = parts
    t0 = time.time()
    P['steps'] = {s['id']: step_image(s) for group in STEPS.values() for s in group}
    log(f'  step pictures: {len(P["steps"])} in {time.time() - t0:.0f} s')
    return P


# ------------------------------------------------------------------------------------------------ HTML
TOC = [  # (number, title, search text on the target page, indent)
    ('1', 'Before you start', 'CHAPTER 1', 0), ('', 'Tools and safety', '1.3 Safety', 1),
    ('2', 'Printing', 'CHAPTER 2', 0), ('', 'The test plate, T1', '2.3 The test plate, T1', 1),
    ('', 'Printed parts checklist', '2.6 Printed parts checklist', 1),
    ('3', 'Parts check', 'CHAPTER 3', 0), ('', 'Screw chart, actual size', '3.3 Screw chart, actual size', 1),
    ('4', 'Wiring', 'CHAPTER 4', 0), ('', 'The power path', '4.2 The power path', 1), ('', 'The signals', '4.4 The signals', 1),
    ('', 'Build the hub', '4.5 Build the hub', 1), ('', 'Every connection', '4.8 Every connection', 1),
    ('5', 'Bench test', 'CHAPTER 5', 0), ('', 'Centre every servo', '5.4 Centre every servo', 1),
    ('6', 'Assembly', 'CHAPTER 6', 0),
    ('A', 'Body', 'SECTION A', 1), ('B', 'Lid', 'SECTION B', 1), ('C', 'Head', 'SECTION C', 1), ('D', 'Legs', 'SECTION D', 1),
    ('', 'Joint limits', 'Range check and joint limits', 1), ('E', 'Tail', 'SECTION E', 1), ('F', 'Ears', 'SECTION F', 1),
    ('G', 'Close up', 'SECTION G', 1),
    ('7', 'First power-on and calibration', 'CHAPTER 7', 0), ('', 'Calibration table', '7.8 Calibration table', 1),
    ('8', 'Troubleshooting', 'CHAPTER 8', 0),
    ('9', 'Appendix', 'CHAPTER 9', 0), ('', 'Bought parts, with store listings', '9.1 Bought parts, with store listings', 1),
    ('', 'Printed parts, colours and plates', '9.2 Printed parts, colours and plates', 1), ('', 'Screws, where each one goes', '9.3 Screws, where each one goes', 1), ('', 'Firmware pin and channel map', '9.4 Firmware pin and channel map', 1), ('', 'Wiring tables', '9.5 Wiring tables', 1),
]


def toc_html(pages):
    rows = []
    for (n, t, key, ind), pg in zip(TOC, pages):
        cls = 'row ch' if ind == 0 else 'row sub'
        rows.append(f'<div class="{cls}"><span class="n">{n}</span><span class="t">{R.E(t)}</span><span class="pg">{pg}</span></div>')
    return '<div class="toc">' + ''.join(rows) + '</div>'


def screw_chart():
    cells = ''
    for size in ('M2x4', 'M2x6', 'M2x8'):
        cells += (f'<div class="cell"><div class="size" style="color:{diagrams.SCREW_COL[size]}">{size.replace("x", " x ")}</div>'
                  f'<div class="cnt">{DP.SCREW_TOTALS[size]} in the robot</div>{diagrams.screw_actual(size)}'
                  f'<div class="cnt">lay the screw on the outline</div></div>')
    return (f'<div class="screw-sort">{cells}</div><div style="margin:2mm 0 4mm"><b>Check ruler, 50 mm:</b><br>'
            f'{diagrams.ruler(50)}</div>')


def screw_strip():
    return ('<div style="display:flex;gap:10mm;align-items:flex-end">' + ''.join(
        f'<div style="text-align:center"><b style="color:{diagrams.SCREW_COL[s]}">{s}</b>{diagrams.screw_actual(s)}</div>'
        for s in ('M2x4', 'M2x6', 'M2x8')) + f'<div>{diagrams.ruler(50)}</div></div>')


def trouble():
    return '<div class="trouble">' + ''.join(
        f'<div class="tr"><div class="sym">{R.E(a)}</div><div><span class="k">Likely cause: </span>{R.E(b)}</div>'
        f'<div style="margin-top:1mm"><span class="k">Fix: </span>{R.E(c)}</div></div>' for a, b, c in data_trouble.TROUBLE) + '</div>'


def assemble(P, toc_pages):
    parts = []
    for f in sorted(glob.glob(os.path.join(SRC, 'sections', '*.html'))):
        parts.append(open(f, encoding='utf-8').read())
    body = '\n'.join(parts)
    note = R.colours(config.RENDER_NOTE.replace('{white}', '{{white}}').replace('{graphite}', '{{graphite}}')
                     .replace('{black}', '{{black}}')) if config.RENDERS_SHOW_OLD_COLOURS else ''
    screwkey = ''.join(R.screw_li(n, s).replace(f'{n} x ', '') for n, s in ((0, 'M2x4'), (0, 'M2x6'), (0, 'M2x8'), (0, 'horn')))
    subs = {
        '{{toc}}': toc_html(toc_pages), '{{render_note}}': note, '{{screwkey}}': screwkey,
        '{{TITLE}}': config.TITLE, '{{SUBTITLE}}': config.SUBTITLE, '{{VERSION}}': config.VERSION, '{{EDITION}}': config.EDITION,
        '{{rules}}': R.rules(), '{{svg:power}}': diagrams.power(), '{{svg:signals}}': diagrams.signals(), '{{svg:hub}}': diagrams.hub(),
        '{{table:plates}}': R.t_plates(), '{{table:checklist}}': R.t_checklist(), '{{table:printed}}': R.t_printed(),
        '{{table:bought}}': R.t_bought(True), '{{table:bought_nolinks}}': R.t_bought(False),
        '{{table:screws}}': R.t_screws(), '{{table:bychapter}}': R.t_by_chapter(),
        '{{table:power}}': R.t_power(), '{{table:signal}}': R.t_signal(), '{{table:servo}}': R.t_servo(),
        '{{table:laser}}': R.t_laser(), '{{table:pinmap}}': R.t_pinmap(), '{{table:wirekey}}': R.wire_key(), '{{calib}}': R.calib_table(),
        '{{trouble}}': trouble(), '{{screwchart}}': screw_chart(), '{{screwstrip}}': screw_strip(),
        '{{partsgrid}}': R.parts_grid(lambda pic: P['parts'][pic]),
        '{{testgrid}}': '<div class="parts-grid" style="grid-template-columns:1fr 1fr">' + ''.join(
            f'<div class="p"><img src="{P["parts"][pic]}" alt=""><div class="nm">{R.E(f)}</div><div class="ds">{R.E(d)}</div></div>'
            for f, d, g, pic in DP.TEST_PRINTS) + '</div>',
    }
    for k in ('cover', 'iso_small', 'bought', 'inside', 'sec1', 'sec2', 'sec3', 'sec4'):
        subs['{{img:' + k + '}}'] = P[k]
    for letter, group in STEPS.items():
        subs['{{steps:' + letter + '}}'] = '\n'.join(R.step(s, P['steps'].get(s['id'])) for s in group)
        subs['{{steps:' + letter + ':rest}}'] = '\n'.join(R.step(s, P['steps'].get(s['id'])) for s in group[1:])
        for s in group:
            subs['{{step:' + s['id'] + '}}'] = R.step(s, P['steps'].get(s['id']))
    for k, v in subs.items():
        body = body.replace(k, v)
    body = R.colours(body)
    # section kicker for the contents search ("SECTION A" etc.)
    body = re.sub(r'<div class="(sub-opener[^"]*)" id="sec([A-G])">', r'<div class="\1" id="sec\2"><div class="kicker">Section \2</div>', body)
    body = body.replace('<div id="secF" style="margin-top:6mm">', '<div id="secF" style="margin-top:6mm"><div class="kicker">Section F</div>')
    left = re.findall(r'\{\{[^}]+\}\}', body)
    if left:
        log('  !! unreplaced placeholders:', sorted(set(left)))
    css = open(os.path.join(SRC, 'style.css'), encoding='utf-8').read()
    doc = (f'<!DOCTYPE html><html lang="en-AU"><head><meta charset="utf-8"><title>{config.TITLE} {config.SUBTITLE} {config.VERSION}</title>'
           f'<style>{css}</style></head><body>{body}</body></html>')
    path = os.path.join(SRC, 'guide.html')
    open(path, 'w', encoding='utf-8').write(doc)
    return path


# ------------------------------------------------------------------------------------------------ PDF
def print_pdf(html_path, pdf_path):
    profile = os.path.join(GUIDE, '.edge-profile')
    os.makedirs(profile, exist_ok=True)
    tmp = pdf_path + '.tmp.pdf'
    if os.path.exists(tmp):
        os.remove(tmp)
    url = 'file:///' + html_path.replace('\\', '/')
    cmd = [config.EDGE, '--headless', '--disable-gpu', '--no-first-run', '--disable-extensions',
           '--no-pdf-header-footer', '--print-to-pdf-no-header', f'--user-data-dir={profile}',
           '--virtual-time-budget=30000', f'--print-to-pdf={tmp}', url]
    t0 = time.time()
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=240)
    if not os.path.exists(tmp) or os.path.getsize(tmp) < 10000:
        raise RuntimeError('Edge did not write the PDF')
    os.replace(tmp, pdf_path)
    log(f'  printed with Edge in {time.time() - t0:.0f} s -> {os.path.basename(pdf_path)}')


def find_pages(pdf_path):
    import fitz
    doc = fitz.open(pdf_path)
    texts = [p.get_text() for p in doc]
    out = []
    for n, t, key, ind in TOC:
        pg = next((i + 1 for i in range(2, len(texts)) if key in texts[i]), None)
        out.append(pg if pg else '?')
    return out, len(texts)


def check(pdf_path):
    import fitz
    from PIL import Image, ImageDraw
    os.makedirs(CHECK, exist_ok=True)
    for f in glob.glob(os.path.join(CHECK, 'contact_*.png')) + glob.glob(os.path.join(CHECK, 'pages', '*.png')):
        os.remove(f)
    os.makedirs(os.path.join(CHECK, 'pages'), exist_ok=True)
    doc = fitz.open(pdf_path)
    thumbs, issues = [], []
    W, H = doc[0].rect.width, doc[0].rect.height
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=110)
        p = os.path.join(CHECK, 'pages', f'page_{i + 1:02d}.png')
        pix.save(p)
        im = Image.open(p).convert('RGB')
        import numpy as np
        a = np.asarray(im.convert('L'))
        if (a < 245).mean() < 0.01:
            issues.append(f'page {i + 1}: nearly empty')
        for b in page.get_text('blocks'):
            x0, y0, x1, y1 = b[:4]
            if x1 > W - 20 or x0 < 20 or y1 > H - 10:
                issues.append(f'page {i + 1}: text near the edge at ({x0:.0f},{y0:.0f})-({x1:.0f},{y1:.0f}): {b[4][:40]!r}')
        t = im.resize((300, int(300 * im.height / im.width)))
        thumbs.append(t)
    per = 12
    for k in range(0, len(thumbs), per):
        grp = thumbs[k:k + per]
        cols, rows = 4, (len(grp) + 3) // 4
        th = grp[0].height
        sheet = Image.new('RGB', (cols * 310 + 10, rows * (th + 30) + 10), (90, 90, 96))
        d = ImageDraw.Draw(sheet)
        for j, t in enumerate(grp):
            x, y = 10 + (j % cols) * 310, 10 + (j // cols) * (th + 30)
            sheet.paste(t, (x, y))
            d.text((x + 2, y + th + 4), f'page {k + j + 1}', fill='white')
        sheet.save(os.path.join(CHECK, f'contact_{k // per + 1:02d}.png'))
    log(f'  check: {len(thumbs)} pages rendered, {len(glob.glob(os.path.join(CHECK, "contact_*.png")))} contact sheets')
    for s in issues:
        log('  check:', s)
    return issues


def main():
    t0 = time.time()
    log(f'Desk Buddy guide build {datetime.datetime.now():%Y-%m-%d %H:%M}  (images from {config.IMG_DIR})')
    P = pictures()
    html_path = assemble(P, ['00'] * len(TOC))
    pdf = config.OUTPUT_PDF
    print_pdf(html_path, pdf)
    pages, n = find_pages(pdf)
    html_path = assemble(P, pages)
    print_pdf(html_path, pdf)
    pages2, n2 = find_pages(pdf)
    if pages2 != pages:
        log('  contents moved on the second pass; printing once more')
        html_path = assemble(P, pages2)
        print_pdf(html_path, pdf)
        pages2, n2 = find_pages(pdf)
    missing = [TOC[i][1] for i, p in enumerate(pages2) if p == '?']
    log(f'  PDF: {n2} pages; contents entries not found: {missing or "none"}')
    if '--no-check' not in sys.argv:
        check(pdf)
    shutil.rmtree(os.path.join(GUIDE, '.edge-profile'), ignore_errors=True)
    log(f'done in {time.time() - t0:.0f} s')
    open(os.path.join(GUIDE, 'check', 'build_log.txt'), 'w', encoding='utf-8').write('\n'.join(LOG) + '\n')


if __name__ == '__main__':
    main()
