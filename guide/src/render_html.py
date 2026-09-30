"""Desk Buddy guide - HTML pieces (tables, steps, grids). build.py stitches them into the sections."""
import html
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'tools'))
import config  # noqa: E402
import data_parts as DP  # noqa: E402
import data_wiring as DW  # noqa: E402
import diagrams  # noqa: E402

E = html.escape


def colours(s):
    """Swap every {{white}} / {{White}} / {{swatch:white}} for the names in config.COLOURS."""
    for key, c in config.COLOURS.items():
        s = s.replace('{{' + key + '}}', c['name'])
        s = s.replace('{{' + key.capitalize() + '}}', c['name'].capitalize())
        s = s.replace('{{swatch:' + key + '}}', f'<span class="sw" style="background:{c["hex"]}"></span>')
    return s


def cname(key):
    return config.COLOURS[key]['name'] if key in config.COLOURS else 'any colour'


def swatch(key):
    if key not in config.COLOURS:
        return ''
    return f'<span class="sw" style="background:{config.COLOURS[key]["hex"]}"></span>'


def screw_li(n, size):
    label = f'{n} x {size.replace("x", " x ")}' if size != 'horn' else f'{n} x horn screw'
    return f'<li class="screw">{diagrams.screw_icon(size)}<span>{E(label)}</span></li>'


def step(s, img_src):
    need = ''.join(screw_li(n, size) if kind == 'screw' else f'<li>{E(n)}</li>'
                   for kind, *rest in s['need'] for n, size in [(rest + [None])[:2]])
    mh = f' style="max-height:{s["fig_mm"]}mm"' if s.get('fig_mm') else ''
    fig = (f'<figure><img src="{img_src}" alt="{E(s["title"])}"{mh}></figure>' if img_src else '')
    text = ''.join(f'<p>{E(t)}</p>' for t in s['text'])
    if s.get('note'):
        text = f'<div class="box info" style="margin:0 0 2.5mm"><h4>May change</h4>{E(s["note"])}</div>' + text
    boxes = ''
    if s.get('check'):
        boxes += f'<div class="box check"><h4>Check</h4>{E(s["check"])}</div>'
    if s.get('mistake'):
        boxes += f'<div class="box mistake"><h4>Common mistake</h4>{E(s["mistake"])}</div>'
    need_html = f'<div class="need"><h4>You need</h4><ul>{need}</ul></div>' if s['need'] else ''
    body_cls = 'step-body' if need_html else 'step-body nofig'
    return colours(f'''<section class="step" id="step-{s["id"]}">
<div class="step-head"><span class="step-id">{E(s["id"])}</span><h3>{E(s["title"])}</h3></div>
{fig}<div class="{body_cls}">{need_html}<div class="steps-text">{text}{boxes}</div></div></section>''')


# ---------------------------------------------------------------------------------------------------- tables
def table(head, rows, cls='t', num=()):
    th = ''.join(f'<th class="{"num" if i in num else ""}">{h}</th>' for i, h in enumerate(head))
    trs = ''.join('<tr>' + ''.join(f'<td class="{"num" if i in num else ""}">{c}</td>' for i, c in enumerate(r)) + '</tr>'
                  for r in rows)
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>'


def t_printed():
    rows = [(f'<b>{E(f)}</b><br><span style="color:#6e6e73">{E(nm)}</span>', f'{swatch(c)}{cname(c)}', E(holds),
             str(n), f'{g:.1f}', E(pl)) for f, nm, c, holds, g, pl, n, _ in DP.PRINTED]
    return table(['Part (file)', 'Colour', 'What it holds', 'Qty', 'g each', 'Plate'], rows, 't small', num=(3, 4))


def t_plates():
    rows = [(str(o), f'<b>{p}</b>', f'{swatch(c)}{cname(c)}' if c else 'any', E(parts), f'{g:.1f}', band, per)
            for o, p, c, parts, g, band, per in DP.PLATES]
    rows.append(('', '<b>Robot, plates 2-10</b>', '', '', '<b>385.7</b>', '<b>$43.00</b>', '<b>$42.43</b>'))
    rows.append(('', '<b>With the test plate</b>', '', '', '<b>412.2</b>', '<b>$47.00</b>', '<b>$45.35</b>'))
    return table(['Order', 'Plate', 'Filament', 'Parts', 'Grams', 'Band price', '$1.10 / 10 g'], rows, 't small', num=(4, 5, 6))


def t_checklist():
    by = {}
    for pl, f in DP.CHECKLIST:
        by.setdefault(pl, []).append(f)
    cells = []
    for o, pl, c, *_ in DP.PLATES:
        items = ''.join(f'<div style="display:flex;gap:1.6mm;align-items:center;margin:0.7mm 0"><span class="tick"></span>'
                        f'<span class="file" style="background:none;padding:0">{E(f)}</span></div>' for f in by.get(pl, []))
        cells.append(f'<div class="keep" style="border:0.25mm solid #e3e3e8;border-radius:2mm;padding:2mm 3mm">'
                     f'<div style="font-weight:700;margin-bottom:1mm">{pl} &nbsp;{swatch(c) if c else ""}'
                     f'<span style="font-weight:400;color:#6e6e73">{cname(c) if c else "test prints, any colour"}</span></div>{items}</div>')
    return '<div class="cols3" style="font-size:8.2pt">' + ''.join(cells) + '</div>'


def t_bought(links=True):
    rows = []
    for part, qty, where, link, store, key in DP.BOUGHT:
        l = (f'<a href="{E(link)}">{E(link.replace("https://", "").replace("www.", "")[:46])}</a>' if link else 'in store')
        rows.append((f'<span class="tick"></span>', E(part), E(qty), E(where), E(store) + ('<br>' + l if links else '')))
    return table(['', 'Part', 'Qty', 'Where it goes', 'Store and listing'], rows, 't small')


def t_screws():
    rows = [(E(w), str(n), f'<span class="pill" style="background:{diagrams.SCREW_COL[s]}">{s if s != "horn" else "horn screw"}</span>', E(note))
            for w, n, s, note in DP.SCREWS]
    rows.append(('<b>Total</b>', '', '<b>M2x4: 15, M2x6: 58, M2x8: 25</b> + 13 horn screws', 'the side panels, bands, head back, port doors, caps and plugs have no screws'))
    return table(['Where', 'Count', 'Screw', 'Note'], rows, 't small', num=(1,))


BY_CHAPTER = [
    ('A  Body', 0, 12, 2, 'hip servos 8 x M2x6, servo boards 4 x M2x6, battery clamp 2 x M2x8'),
    ('B  Lid', 4, 2, 4, 'tail servo 2 x M2x6, touch pads 4 x M2x4, collar 4 x M2x8'),
    ('C  Head', 1, 4, 8, 'screen 4 x M2x6, head touch pad 1 x M2x4, muzzle 4 x M2x8, head to collar 4 x M2x8'),
    ('D  Legs (all four)', 8, 32, 8, 'per leg: hip horn 2 x M2x4; knee servo, wheel servo, knee horn and wheel horn 2 x M2x6 each; 2 covers 1 x M2x8 each'),
    ('E  Tail', 2, 0, 1, 'tail horn 2 x M2x4, tail to root 1 x M2x8'),
    ('F  Ears', 0, 0, 2, 'one M2x8 per ear'),
    ('G  Close up', 0, 4, 0, 'lid to tub 4 x M2x6'),
    ('7  First power-on', 0, 4, 0, 'battery door 4 x M2x6'),
]


def t_by_chapter():
    rows = [(E(c), str(a) if a else '-', str(b) if b else '-', str(d) if d else '-', E(note)) for c, a, b, d, note in BY_CHAPTER]
    rows.append(('<b>Total</b>', '<b>15</b>', '<b>58</b>', '<b>25</b>', 'plus 13 horn screws from the servo bags'))
    return table(['Chapter', 'M2x4', 'M2x6', 'M2x8', 'What for'], rows, 't small', num=(1, 2, 3))


def t_power():
    return table(['', 'From', 'To', 'Wire', 'Length', 'Note'],
                 [(f'<b>{i}</b>', E(a), E(b), E(w), E(l), E(n)) for i, a, b, w, l, n in DW.POWER], 't small')


def t_signal():
    return table(['', 'From', 'To', 'Wire', 'Length', 'Note'],
                 [(f'<b>{i}</b>', E(a), E(b), E(w), E(l), E(n)) for i, a, b, w, l, n in DW.SIGNAL], 't small')


def t_servo():
    return table(['', 'Servo', 'Servo board', 'Channel', 'Lead route'],
                 [('<span class="tick"></span>', E(s), E(b), str(c), E(r)) for s, b, c, r in DW.SERVO_CH], 't small', num=(3,))


def t_laser():
    return table(['', 'Laser', 'Where', 'XSHUT to board B channel'],
                 [('<span class="tick"></span>', E(a), E(b), str(c)) for a, b, c in DW.LASER_CH], 't small', num=(3,))


def t_pinmap():
    return table(['What', 'Pin / address / channel', 'Note'],
                 [(f'<b>{E(a)}</b>', E(b), E(c)) for a, b, c in DW.PINMAP], 't small')


def wire_key():
    return '<div class="legend">' + ''.join(
        f'<span><span class="wire-sw" style="background:{css}"></span><b>{E(n)}</b> - {E(what)}</span>'
        for n, css, what in DW.WIRE_KEY) + '</div>'


def rules():
    return ''.join(f'<div class="box warn keep"><h4>Rule {i}</h4><b>{E(t)}</b> {E(d)}</div>'
                   for i, (t, d) in enumerate(DW.RULES, 1))


def parts_grid(img_for):
    cells = []
    for f, nm, c, holds, g, pl, n, pic in DP.PRINTED:
        src = img_for(pic)
        cells.append(f'<div class="p"><img src="{src}" alt=""><div class="nm">{E(f)}{" x" + str(n) if n > 1 else ""}</div>'
                     f'<div class="ds">{swatch(c)}{cname(c)} &middot; {E(nm)}</div></div>')
    return '<div class="parts-grid">' + ''.join(cells) + '</div>'


def calib_table():
    rows = [(E(s), f'{b.split(" ")[0]} / {c}', '', '' if 'Wheel' in s else '&mdash;', '' if 'Wheel' not in s else '&mdash;')
            for s, b, c, _ in DW.SERVO_CH]
    t = table(['Servo', 'Board / channel', 'Centre or straight (us)', 'Wheel stop (us)', '+ moves the foot forward? (yes / reversed)'],
              rows, 't')
    return t.replace('<td class=""></td>', '<td style="height:7mm"></td>')


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')
