"""protocol_check.py -- every message the firmware can send, checked by the BRAIN's own validator.

It scans the firmware sources for netSend("type", fields) calls, rebuilds each message exactly the
way netSend() frames it ({"v":1,"type":..,"id":..,"ts":..,<fields>}), fills the printf conversions with
realistic values, and runs spike_brain.protocol.decode() + validate(msg, "to_brain") on it -- the same
code the laptop brain uses on every inbound frame. It also checks that the robot handles every
brain->robot type the brain can send.

v1.3 (PROTOCOL.md section 11): netSendOn(<link>, "type", fields) calls are checked the same way. The
robot -> phone types `hotspot_state` and `robot_link` exist only between the robot and a phone brain, so
the laptop brain's protocol.py (read-only here) does not know them: they are checked against the table
V13_ROBOT_TO_PHONE below, written from PROTOCOL.md 11.4 / 11.5. The phone -> robot types hotspot_join,
hotspot_leave and robot_link_ack must be handled by the screen board, and the hellos must carry "link".

Run: software\\laptop\\.venv\\Scripts\\python.exe software\\firmware\\test\\protocol_check.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)
SW = os.path.dirname(FW)
sys.path.insert(0, os.path.join(SW, "laptop"))
from spike_brain import protocol as P  # noqa: E402

SOURCES = [os.path.join(FW, "screen_board", "src", f) for f in os.listdir(os.path.join(FW, "screen_board", "src")) if f.endswith(".cpp")]
SOURCES += [os.path.join(FW, "camera_board", "src", f) for f in os.listdir(os.path.join(FW, "camera_board", "src")) if f.endswith(".cpp")]

# value for a %s by the JSON field it fills
SAMPLE = {"zone": "head", "gesture": "tap", "utt": "u17", "state": "started", "mood": "happy", "mode": "dog",
          "code": "bad_json", "device_id": "spike-7c9e2a", "fw": "0.1.0", "message": "x", "token": "t0k3n",
          "data": "AAAA", "type": "touch", "sensor": "front_left", "event": "pickup", "level": "warn", "msg": "hi",
          "brain": "ble", "wifi": "hotspot", "ip": "192.168.49.23", "reason": "auth"}

# v1.3: robot -> phone brain only (PROTOCOL.md 11.4, 11.5): field -> (types, allowed values, required)
V13_ROBOT_TO_PHONE = {
    "hotspot_state": {"state": ((str,), ("joining", "joined", "failed", "left"), True),
                      "ip": ((str,), None, False),
                      "reason": ((str,), ("not_found", "auth", "timeout", "bad_value"), False)},
    "robot_link": {"brain": ((str,), ("lan", "ble", "hotspot", "none"), True),
                   "wifi": ((str,), ("home", "hotspot", "off"), True),
                   "ip": ((str,), None, True),
                   "camera": ((bool,), None, False)},
}
V13_PHONE_TO_ROBOT = ("hotspot_join", "hotspot_leave", "robot_link_ack")


def validate_v13(msg):
    spec = V13_ROBOT_TO_PHONE[msg["type"]]
    for name, (types, allowed, required) in spec.items():
        if name not in msg:
            if required:
                raise ValueError("%s: missing '%s'" % (msg["type"], name))
            continue
        val = msg[name]
        if isinstance(val, bool) and bool not in types:
            raise ValueError("%s.%s: wrong type" % (msg["type"], name))
        if not isinstance(val, types) or (allowed is not None and val not in allowed):
            raise ValueError("%s.%s: bad value %r" % (msg["type"], name, val))
    if msg["type"] == "hotspot_state" and msg["state"] == "joined" and not msg.get("ip"):
        raise ValueError("hotspot_state joined needs ip")
    if msg["type"] == "hotspot_state" and msg["state"] == "failed" and "reason" not in msg:
        raise ValueError("hotspot_state failed needs reason")


def c_unescape(s):
    return s.encode().decode("unicode_escape")


def fill(fmt):
    out = fmt
    out = out.replace('%s%s%s', 'null')                              # "action":%s%s%s -> null
    out = out.replace('"camera":%s', '"camera":false')              # robot_link.camera (a bool)
    out = re.sub(r'"(\w+)":"%s"', lambda m: '"%s":"%s"' % (m.group(1), SAMPLE.get(m.group(1), "x")), out)
    out = re.sub(r'"(\w+)":%s', lambda m: '"%s":"%s"' % (m.group(1), SAMPLE.get(m.group(1), "x")), out)
    out = re.sub(r'%\.\d+f', '7.12', out)
    out = re.sub(r'%l?[dul]+', '1', out)
    out = out.replace('%s', 'x')
    return out


def main():
    calls = []  # (file, type, fields)
    for path in SOURCES:
        text = open(path, encoding="utf-8").read()
        last_fmt = None
        prev_fmt = None
        for m in re.finditer(r'snprintf\([^;]*?"((?:[^"\\]|\\.)*)"(?:\s*"((?:[^"\\]|\\.)*)")*|netSend(?:On)?\((?:\w+,\s*)?"(\w+)",\s*(?:"((?:[^"\\]|\\.)*)"|(\w+)|([^)]*))\)', text, re.S):
            if m.group(0).startswith("snprintf"):
                # join adjacent string literals of the format
                lits = re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(0))
                fmt = c_unescape("".join(lits))
                if fmt.startswith(",") and last_fmt:  # an optional field appended to the previous format
                    fmt = last_fmt + fmt
                prev_fmt, last_fmt = last_fmt, fmt
            else:
                typ = m.group(3)
                if m.group(4) is not None:
                    fields = c_unescape(m.group(4))
                elif m.group(5) and last_fmt is not None:
                    fields = fill(last_fmt)
                    if fields.endswith('"data":"'):     # the camera writes the base64 and the closing quote after it
                        fields += 'AAAA"'
                else:
                    fields = None
                calls.append((os.path.basename(path), typ, fields))
    ok = bad = 0
    seen = set()
    hellos = []
    for f, typ, fields in calls:
        if fields is None:
            print("skip  %-14s %-11s (fields built at run time: %s)" % (f, typ, "checked by hand"))
            continue
        # hello's optional token is appended after the fixed part
        text = '{"v":1,"type":"%s","id":1,"ts":1%s%s}' % (typ, "," if fields else "", fields)
        try:
            msg = P.decode(text)
            if typ in V13_ROBOT_TO_PHONE:
                validate_v13(msg)
            elif typ != "error":
                P.validate(msg, "to_brain")
            if typ == "hello":
                hellos.append((f, msg))
            print("ok    %-14s %-11s %s" % (f, typ, text[:110]))
            ok += 1
            seen.add(typ)
        except Exception as e:  # noqa: BLE001
            print("FAIL  %-14s %-11s %s\n      -> %s" % (f, typ, text[:160], e))
            bad += 1
    # the robot must handle every brain -> robot type the brain can send
    handled = open(os.path.join(FW, "screen_board", "src", "net.cpp"), encoding="utf-8").read()
    for t in V13_PHONE_TO_ROBOT:  # v1.3: phone brain -> robot
        present = ('!strcmp(type, "%s")' % t) in handled
        print(("ok    " if present else "FAIL  ") + "screen board handles phone message '%s' (v1.3)" % t)
        ok += present
        bad += not present
    # v1.3 hellos: over BLE with "link":"ble" and no token; over the hotspot with the token and "link":"hotspot"
    checks = [
        (lambda f, m: f == "net.cpp" and m.get("link") == "ble" and "token" not in m and m["role"] == "face",
         "screen board hello over BLE: role face, link ble, no token (11.3)"),
        (lambda f, m: f == "net.cpp" and m.get("link") == "hotspot" and "token" in m and m["role"] == "face",
         "screen board hello over the hotspot: token + link hotspot (11.5)"),
        (lambda f, m: f == "cam_net.cpp" and m.get("link") == "hotspot" and "token" in m and m["role"] == "camera",
         "camera board hello over the hotspot: role camera, token + link hotspot (11.6)"),
    ]
    for pred, what in checks:
        good = any(pred(f, m) for f, m in hellos)
        print(("ok    " if good else "FAIL  ") + what)
        ok += good
        bad += not good
    for v13 in V13_ROBOT_TO_PHONE:
        good = v13 in seen
        print(("ok    " if good else "FAIL  ") + "robot sends '%s' (v1.3)" % v13)
        ok += good
        bad += not good
    for t in P.BRAIN_TO_ROBOT:
        if t in ("pong",):
            continue
        present = ('"%s"' % t) in handled
        print(("ok    " if present else "FAIL  ") + "screen board handles brain message '%s'" % t)
        ok += present
        bad += not present
    print("\nprotocol check: %s (%d ok, %d failed); robot->brain types covered: %s" % ("PASS" if not bad else "FAIL", ok, bad, sorted(seen)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
