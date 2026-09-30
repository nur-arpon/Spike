"""check_pinmap.py -- fails if the firmware's pins, addresses or channels drift from the assembly guide.

The single source is PINMAP in guide/src/data_wiring.py (printed as guide/OPEN_QUESTIONS.md section D and
guide Appendix 9.4; guide/tools/servo_center uses the same values). This script READS that file and
compares it with screen_board/src/config.h and lib/spike_body/src/spike_body.cpp.

Run: python software/firmware/tools/check_pinmap.py
"""
import importlib.util
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FW = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(FW))
WIRING = os.path.join(ROOT, "guide", "src", "data_wiring.py")


def load_pinmap():
    spec = importlib.util.spec_from_file_location("data_wiring", WIRING)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {row[0]: (row[1], row[2]) for row in mod.PINMAP}, mod


def defines(path):
    out = {}
    for line in open(path, encoding="utf-8"):
        m = re.match(r"\s*#define\s+(\w+)\s+(\S+)", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def main():
    pm, mod = load_pinmap()
    cfg = defines(os.path.join(FW, "screen_board", "src", "config.h"))
    body = open(os.path.join(FW, "lib", "spike_body", "src", "spike_body.cpp"), encoding="utf-8").read()
    errors = []

    def expect(label, cond):
        print(("ok    " if cond else "FAIL  ") + label)
        if not cond:
            errors.append(label)

    io = lambda s: [int(x) for x in re.findall(r"IO(\d+)", s)]
    expect("I2C SDA = IO%s" % cfg["PIN_I2C_SDA"], io(pm["I2C SDA"][0])[0] == int(cfg["PIN_I2C_SDA"]))
    expect("I2C SCL = IO%s" % cfg["PIN_I2C_SCL"], io(pm["I2C SCL"][0])[0] == int(cfg["PIN_I2C_SCL"]))
    expect("I2C speed 100 kHz", "100 kHz" in pm["I2C SCL"][1] and cfg["ROBOT_I2C_HZ"] == "100000")
    expect("OE / wheel stop = IO%s" % cfg["PIN_SERVO_OE"], io(pm["Wheel stop / servo enable"][0])[0] == int(cfg["PIN_SERVO_OE"]))
    expect("battery = IO%s" % cfg["PIN_VBAT"], io(pm["Battery voltage"][0])[0] == int(cfg["PIN_VBAT"]))
    expect("battery divider 10k / 4.7k", "10 kOhm" in pm["Battery voltage"][1] and "4.7 kOhm" in pm["Battery voltage"][1]
           and "10.0f + 4.7f) / 4.7f" in open(os.path.join(FW, "screen_board", "src", "config.h")).read())
    mic = io(pm["Microphones (I2S, both mics)"][0])
    expect("mics SCK/WS/SD = IO%s/%s/%s" % (cfg["PIN_MIC_SCK"], cfg["PIN_MIC_WS"], cfg["PIN_MIC_SD"]),
           mic == [int(cfg["PIN_MIC_SCK"]), int(cfg["PIN_MIC_WS"]), int(cfg["PIN_MIC_SD"])])
    expect("PCA9685 A 0x40 / B 0x41", "0x40" in pm["PCA9685 A"][0] and "0x41" in pm["PCA9685 B"][0]
           and "PCA_ADDR[2] = {0x40, 0x41}" in open(os.path.join(FW, "lib", "spike_body", "src", "spike_body.h")).read())
    expect("MPU6050 0x68", "0x68" in pm["MPU6050"][0] and cfg["ADDR_MPU6050"] == "0x68")
    expect("MPR121 0x5A", "0x5A" in pm["MPR121"][0] and cfg["ADDR_MPR121"] == "0x5A")
    expect("APDS-9960 0x39", "0x39" in pm["APDS-9960"][0] and cfg["ADDR_APDS9960"] == "0x39")
    expect("MPR121 head pad = E%s" % cfg["PAD_HEAD"], "E%s head" % cfg["PAD_HEAD"] in pm["MPR121"][1])

    # servo channels: the guide's SERVO_CH table vs kServoMap
    rows = re.findall(r'\{"([a-z -]+)", (\d), (\d+), (true|false)\}', body)
    fw = {name: (int(b), int(ch)) for name, b, ch, _ in rows}
    for servo, board, ch, _ in mod.SERVO_CH:
        part, leg = [s.strip() for s in servo.replace("(360)", "").split(",")] if "," in servo else (servo, "")
        name = (part.lower() + (" " + leg.lower() if leg else "")).replace("back", "back").strip()
        b = 0 if board.startswith("A") else 1
        expect("servo %-22s board %s ch %2d" % (servo, "AB"[b], ch), fw.get(name) == (b, ch))
    # laser XSHUT channels
    lasers = re.findall(r'\{"([a-z -]+)", (\d+), 0x3\d\}', body)
    fwl = [int(c) for _, c in lasers]
    expect("laser XSHUT channels %s" % fwl, fwl == [c for _, _, c in mod.LASER_CH])
    expect("rear-leg limit hip > +25 -> knee <= +45", "above +25 deg -> knee at most +45 deg" in pm["Joint sign"][1]
           and "REAR_HIP_RULE = 25, REAR_KNEE_CAP = 45" in open(os.path.join(FW, "lib", "spike_body", "src", "spike_body.h")).read())
    print("\n%s: %d mismatch(es)" % ("FAIL" if errors else "PASS", len(errors)))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
