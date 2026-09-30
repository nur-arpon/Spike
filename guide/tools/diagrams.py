"""Desk Buddy guide - vector diagrams (inline SVG strings): power path, signals, hub layout, screw outlines.
User units are about 1 mm at the printed width; the HTML sets the printed width."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

RED, RED2, BLACK, ORANGE, BLUE, YELLOW = '#d62828', '#e63946', '#222222', '#f4a261', '#1d6fd8', '#d4a017'
GREEN, WHITE, PURPLE, GREY, BROWN = '#2a9d8f', '#9a9a9a', '#7b2cbf', '#8d99ae', '#8b5a2b'
INK, MUTED, PANEL, ACC = '#1d1d1f', '#6e6e73', '#f3f3f5', '#f2781e'
FONT = "font-family:'Segoe UI',Arial,sans-serif"


class Svg:
    def __init__(self, w, h):
        self.w, self.h, self.items = w, h, []

    def box(self, x, y, w, h, title, sub='', fill=PANEL, stroke='#c7c7cc', tsize=4.0, bold=True, tcol=INK, scol=MUTED,
            ssize=2.9, align='middle'):
        self.items.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="2" fill="{fill}" stroke="{stroke}" stroke-width="0.4"/>')
        lines = sub.split('\n') if sub else []
        total = tsize + len(lines) * (ssize * 1.3)
        ty = y + (h - total) / 2 + tsize * 0.85
        tx = x + w / 2 if align == 'middle' else x + 2.5
        self.text(tx, ty, title, tsize, align, tcol, bold)
        for i, line in enumerate(lines):
            self.text(tx, ty + tsize * 0.35 + (i + 1) * ssize * 1.3, line, ssize, align, scol, False)

    def text(self, x, y, s, size=3.4, anchor='start', fill=INK, bold=False):
        s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        self.items.append(f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" fill="{fill}" '
                          f'font-weight="{600 if bold else 400}" style="{FONT}">{s}</text>')

    def wire(self, pts, colour, width=1.1, dash=None):
        d = ' '.join(f'{"M" if i == 0 else "L"}{x},{y}' for i, (x, y) in enumerate(pts))
        da = f' stroke-dasharray="{dash}"' if dash else ''
        self.items.append(f'<path d="{d}" fill="none" stroke="{colour}" stroke-width="{width}" stroke-linejoin="round" '
                          f'stroke-linecap="round"{da}/>')

    def dot(self, x, y, colour=INK, r=0.9):
        self.items.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{colour}"/>')

    def gnd(self, x, y, label=True):
        """Ground symbol hanging from (x, y)."""
        self.wire([(x, y), (x, y + 2.2)], BLACK, 0.7)
        for i, w in enumerate((4.0, 2.6, 1.2)):
            yy = y + 2.2 + i * 0.9
            self.wire([(x - w / 2, yy), (x + w / 2, yy)], BLACK, 0.5)
        if label:
            self.text(x + 2.8, y + 3.6, 'GND', 2.3, 'start', MUTED, True)

    def tag(self, x, y, s, colour=INK, size=2.7, anchor='start'):
        self.text(x, y, s, size, anchor, colour, True)

    def raw(self, s):
        self.items.append(s)

    def svg(self):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" style="width:100%;height:auto">'
                + ''.join(self.items) + '</svg>')


def power():
    s = Svg(180, 126)
    # row 1: cells -> protection -> fuse -> node -> charger / switch
    s.box(2, 10, 30, 32, '2 x 18650', 'Samsung 35E\nin series\n(battery door)')
    s.box(46, 10, 34, 32, 'Protection board', '2S 20 A\n(tub floor)')
    for lab, col, y in (('B-', BLACK, 18), ('BM', WHITE, 26), ('B+', RED, 34)):
        s.wire([(32, y), (46, y)], col, 1.3)
        s.tag(39, y - 1.3, lab, col, 2.5, 'middle')
    s.box(92, 12, 22, 12, 'Fuse 7.5 A', 'blade fuse', tsize=3.4, ssize=2.3)
    s.wire([(80, 18), (92, 18)], RED, 1.8)
    s.tag(86, 16.4, 'P+', RED, 2.5, 'middle')
    s.wire([(114, 18), (126, 18)], RED, 1.8)
    s.dot(126, 18, RED, 1.1)
    s.box(136, 8, 42, 20, 'USB-C charger', '2S boost, 5 V in\n(rump socket)', tsize=3.6)
    s.wire([(126, 18), (136, 18)], RED, 1.8)
    s.tag(131, 16.4, 'BAT+', RED, 2.3, 'middle')
    s.gnd(157, 28)
    s.text(162, 34.5, '(BAT-)', 2.3, 'start', MUTED)
    s.gnd(63, 42)
    s.text(68, 48.5, '(P-: thick black to the hub, P8)', 2.3, 'start', MUTED)
    s.wire([(126, 18), (126, 40)], RED, 1.8)
    s.box(108, 40, 36, 13, 'Power switch', 'KCD1, front of the belly', tsize=3.6, ssize=2.4)
    s.wire([(126, 53), (126, 62)], RED, 1.8)
    # hub
    s.raw('<rect x="22" y="57" width="138" height="37" rx="3" fill="#fff7ef" stroke="#f2781e" stroke-width="0.5" stroke-dasharray="1.6 1"/>')
    s.text(25, 60.4, 'HUB (under the lid)', 2.6, 'start', ACC, True)
    s.wire([(40, 62), (150, 62)], RED, 1.8)
    s.dot(126, 62, RED, 1.1)
    s.text(62, 60.4, 'BATT-SW  7.4 V, only when switched on', 2.5, 'start', RED, True)
    for x in (48, 94, 137):
        s.wire([(x, 62), (x, 67)], RED, 1.4 if x != 137 else 0.8)
        s.dot(x, 62, RED, 0.9)
    s.box(30, 67, 38, 18, 'Mini560 #1', '5 V for the SERVOS\n+ 1000 uF', tsize=3.6)
    s.box(76, 67, 38, 18, 'Mini560 #2', '5 V for the BOARDS\n+ 1000 uF', tsize=3.6)
    s.box(122, 67, 30, 18, 'Divider', '10 k / 4.7 k\nbattery level', tsize=3.4)
    s.wire([(152, 76), (166, 76)], WHITE, 1.0)
    s.text(167, 77, 'to IO5', 2.6, 'start', MUTED, True)
    # outputs
    s.wire([(49, 85), (49, 98)], RED, 1.8)
    s.wire([(22, 98), (68, 98)], RED, 1.8)
    s.wire([(22, 98), (22, 102)], RED, 1.8)
    s.wire([(68, 98), (68, 102)], RED, 1.8)
    s.wire([(95, 85), (95, 98)], RED2, 1.1)
    s.wire([(112, 98), (157, 98)], RED2, 1.1)
    s.wire([(95, 98), (112, 98)], RED2, 1.1)
    s.wire([(112, 98), (112, 102)], RED2, 1.1)
    s.wire([(157, 98), (157, 102)], RED2, 1.1)
    s.box(2, 102, 40, 13, 'Servo board A', 'green V+ terminal', tsize=3.4, ssize=2.4)
    s.box(48, 102, 40, 13, 'Servo board B', 'green V+ terminal', tsize=3.4, ssize=2.4)
    s.box(92, 102, 40, 13, 'Screen board P1', '5 V + GND only', tsize=3.4, ssize=2.4)
    s.box(137, 102, 41, 13, 'Camera board', '5V + GND pins', tsize=3.4, ssize=2.4)
    s.text(2, 122, 'Every GND symbol is the same wire: the thick black ground that starts at the protection board\'s P- and '
                   'meets at the hub.', 2.6, 'start', MUTED)
    s.text(2, 3.5, 'Red = + (thick where the servo current flows)   Black = ground   White = battery level', 2.6, 'start', MUTED)
    return s.svg()


def signals():
    s = Svg(180, 156)
    s.text(2, 3.5, 'One I2C bus from the screen board to every sensor and both servo boards, wired as a star at the hub.',
           2.6, 'start', MUTED)
    # devices along the top
    devs = [('Servo board A', '0x40\nleft wall'), ('Servo board B', '0x41\nA0 bridged'), ('MPU6050', '0x68\nmotion'),
            ('MPR121', '0x5A\ntouch'), ('APDS-9960', '0x39\ngesture'), ('7 lasers', '0x29, woken\none by one')]
    rails = [(ORANGE, 30, '3.3 V'), (BLACK, 34, 'GND'), (BLUE, 38, 'SDA'), (YELLOW, 42, 'SCL')]
    for i, (t, sub) in enumerate(devs):
        x = 56 + i * 20.4
        s.box(x, 8, 19, 15, t, sub, tsize=2.8, ssize=2.3)
        for k, (col, y, _) in enumerate(rails):
            xx = x + 3.5 + k * 4
            s.wire([(xx, 23), (xx, y)], col, 0.7)
            s.dot(xx, y, col, 0.65)
    for col, y, lab in rails:
        s.wire([(46, y), (178, y)], col, 1.2)
    s.text(48, 46.5, 'hub rails: 3.3 V, GND, SDA, SCL', 2.4, 'start', MUTED, True)
    # screen board with its pins on the right edge
    s.text(2, 20, 'Screen board', 4.0, 'start', INK, True)
    s.text(2, 24.5, 'the brain, in the head', 2.6, 'start', MUTED)
    s.raw('<rect x="2" y="27" width="44" height="80" rx="2" fill="#f3f3f5" stroke="#c7c7cc" stroke-width="0.4"/>')
    pins = [('P4  3.3 V', ORANGE, 30), ('P4  GND', BLACK, 34), ('P4  IO17 = SDA', BLUE, 38), ('P4  IO18 = SCL', YELLOW, 42),
            ('IO14  wheel stop', GREEN, 54), ('IO5  battery level', WHITE, 66), ('P3  IO6 / IO7 / IO15', BROWN, 80),
            ('Speak', GREY, 96)]
    for lab, col, y in pins:
        s.text(44, y + 1, lab, 2.6, 'end', INK if col not in (WHITE,) else MUTED, True)
        s.dot(46, y, col, 1.0)
    s.text(4, 104, 'Guition ESP32-S3 4.3 inch', 2.4, 'start', MUTED)
    # wheel stop
    s.wire([(46, 54), (120, 54)], GREEN, 1.2)
    s.text(122, 55, 'to OE on servo boards A and B', 2.6, 'start', GREEN, True)
    s.wire([(70, 54), (70, 58)], GREEN, 0.8)
    s.box(58, 58, 30, 7, '2.2 kOhm to 3.3 V', '', fill='#eef8f6', stroke=GREEN, tsize=2.6)
    s.text(92, 63, 'pulls OE high when the brain is not running: every servo stops', 2.4, 'start', MUTED)
    # battery level
    s.wire([(46, 66), (60, 66), (60, 72)], WHITE, 1.1)
    s.box(50, 72, 52, 6, 'from the hub divider (10 k / 4.7 k)', '', tsize=2.5)
    # mics
    s.wire([(46, 80), (62, 80), (62, 83)], BROWN, 1.2)
    s.box(50, 83, 72, 12, '2 x MS3625 microphone',
          'IO6 = SCK, IO7 = WS, IO15 = SD, shared by both\nL/R pin: left mic to GND, right mic to 3.3 V',
          tsize=2.8, ssize=2.2)
    # speaker
    s.wire([(46, 96), (50, 96), (50, 100)], GREY, 1.2)
    s.box(48, 100, 36, 7, 'Speaker 3 W, "Speak" port', '', tsize=2.6)
    # outputs of the servo boards
    s.box(2, 112, 86, 26, 'Servo board A outputs', 'ch 0, 1, 2   front-left hip, knee, wheel\nch 4, 5, 6   back-left hip, knee, wheel\n'
          'ch 8   tail', tsize=3.2, ssize=2.7, align='start')
    s.box(92, 112, 86, 26, 'Servo board B outputs', 'ch 0, 1, 2   front-right hip, knee, wheel\nch 4, 5, 6   back-right hip, knee, wheel\n'
          'ch 9 to 15   laser XSHUT (purple wires)', tsize=3.2, ssize=2.7, align='start')
    s.box(126, 68, 52, 26, 'MPR121 touch pads', 'E0 back-left     E1 back-right\nE2 rump-left     E3 rump-right\nE4 head',
          tsize=3.0, ssize=2.5, align='start')
    s.text(2, 145, 'Every sensor, and the VCC pin of each servo board: 3.3 V.', 3.0, 'start', RED, True)
    s.text(2, 150, 'Only the servo boards\' green V+ screw terminal gets 5 V.', 3.0, 'start', RED, True)
    return s.svg()


def hub():
    s = Svg(180, 84)
    s.raw('<rect x="30" y="4" width="120" height="74" rx="2" fill="#e9f2e1" stroke="#7a9a5a" stroke-width="0.5"/>')
    for i in range(24):
        for j in range(15):
            s.raw(f'<circle cx="{33 + i * 5}" cy="{7 + j * 5}" r="0.55" fill="#b9c9a6"/>')
    dark = dict(fill='#1f2a44', stroke='#1f2a44', tcol='#ffffff', scol='#c9d1e0')
    s.box(36, 8, 36, 24, 'Mini560 #1', 'SERVOS\nIN+ IN-  |  OUT+ OUT-', tsize=3.6, **dark)
    s.box(78, 8, 36, 24, 'Mini560 #2', 'BOARDS\nIN+ IN-  |  OUT+ OUT-', tsize=3.6, **dark)
    cap = dict(fill='#2b2d42', stroke='#2b2d42', tcol='#ffffff', scol='#c9d1e0')
    s.box(118, 8, 29, 11, '1000 uF, flat', 'across #1 OUT', tsize=2.8, ssize=2.4, **cap)
    s.box(118, 21, 29, 11, '1000 uF, flat', 'across #2 OUT', tsize=2.8, ssize=2.4, **cap)
    s.box(36, 37, 52, 9, '10 k + 4.7 k divider  ->  VBAT pad', '', tsize=2.8)
    s.box(92, 37, 55, 9, '2.2 k from the OE pad to the 3V3 rail', '', tsize=2.8)
    s.box(36, 50, 111, 24, 'Sensor rails: 3V3 / GND / SDA / SCL', 'one row of 4 header pins per device (13 rows)\n'
          'the lead from the screen board\'s P4 lands on one row', tsize=3.3)
    s.text(1, 14, 'BATT-SW', 3.0, 'start', RED, True)
    s.text(1, 24, 'GND', 3.0, 'start', BLACK, True)
    s.wire([(16, 13), (38, 13)], RED, 1.6)
    s.wire([(9, 23), (38, 23)], BLACK, 1.6)
    s.dot(38, 13, RED, 1.0)
    s.dot(38, 23, BLACK, 1.0)
    for i, t in enumerate(['Thick battery and servo', 'wires solder straight to', 'the module pads, and a', 'short thick link runs',
                           'on to #2. The perfboard', 'only holds the parts.']):
        s.text(153, 12 + i * 4, t, 2.6, 'start', MUTED)
    return s.svg()


SCREW_COL = {'M2x4': '#0f9d8a', 'M2x6': '#2b6cd4', 'M2x8': '#8a3ffc', 'horn': '#8d99ae'}


def screw_icon(size, px=22):
    """Small side-view screw icon (not to scale) in the size's colour."""
    L = {'M2x4': 4, 'M2x6': 6, 'M2x8': 8, 'horn': 5}[size]
    c = SCREW_COL[size]
    threads = ''.join(f'<path d="M-1,{1.6 + t} L1,{2.2 + t}" stroke="#fff" stroke-width="0.35"/>' for t in range(0, L, 1))
    return (f'<svg class="screw-ico" viewBox="-2.2 -0.2 4.4 {L + 2.4}" style="height:{px}px;width:auto">'
            f'<rect x="-1.9" y="0" width="3.8" height="1.4" rx="0.5" fill="{c}"/>'
            f'<path d="M-1,1.4 L1,1.4 L1,{1.4 + L - 0.6} L0,{1.4 + L} L-1,{1.4 + L - 0.6} Z" fill="{c}"/>{threads}</svg>')


def screw_actual(size):
    """Actual-size side outline (1 unit = 1 mm) of an M2 pan-head self-tapper; length is under the head."""
    L = {'M2x4': 4, 'M2x6': 6, 'M2x8': 8}[size]
    c = SCREW_COL[size]
    W, H = 12, L + 5
    th = ''.join(f'<line x1="5" y1="{2.4 + t * 0.8}" x2="7" y2="{2.8 + t * 0.8}" stroke="{c}" stroke-width="0.12"/>'
                 for t in range(int((L - 0.8) / 0.8)))
    return (f'<svg viewBox="0 0 {W} {H}" style="width:{W}mm;height:{H}mm">'
            f'<rect x="4.1" y="1" width="3.8" height="1.4" rx="0.5" fill="none" stroke="{c}" stroke-width="0.18"/>'
            f'<path d="M5,2.4 L5,{2.4 + L - 0.6} L6,{2.4 + L} L7,{2.4 + L - 0.6} L7,2.4" fill="none" stroke="{c}" stroke-width="0.18"/>'
            f'{th}<line x1="9" y1="2.4" x2="9" y2="{2.4 + L}" stroke="#999" stroke-width="0.1"/>'
            f'<line x1="8.6" y1="2.4" x2="9.4" y2="2.4" stroke="#999" stroke-width="0.1"/>'
            f'<line x1="8.6" y1="{2.4 + L}" x2="9.4" y2="{2.4 + L}" stroke="#999" stroke-width="0.1"/></svg>')


def ruler(mm=50):
    ticks = ''.join(f'<line x1="{i}" y1="0" x2="{i}" y2="{3 if i % 10 == 0 else (2 if i % 5 == 0 else 1.2)}" '
                    f'stroke="#1d1d1f" stroke-width="0.15"/>' for i in range(mm + 1))
    labels = ''.join(f'<text x="{i}" y="6" font-size="2.2" text-anchor="middle" style="{FONT}">{i}</text>'
                     for i in range(0, mm + 1, 10))
    return (f'<svg viewBox="-2 -0.5 {mm + 4} 7" style="width:{mm + 4}mm;height:7mm">'
            f'<line x1="0" y1="0" x2="{mm}" y2="0" stroke="#1d1d1f" stroke-width="0.2"/>{ticks}{labels}</svg>')
