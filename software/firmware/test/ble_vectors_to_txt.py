"""ble_vectors_to_txt.py -- turns software/protocol/ble_frame_vectors.json (PROTOCOL.md 11.2, v1.3) into a
plain token file for the C++ host test (`face_pc link <file>`), which has no JSON parser.

Every value is passed through unchanged, as hex; nothing is recomputed here, so the C++ codec is
checked against the shared vectors themselves.

  # <case name>
  E <att_mtu> <start_counter> <message hex or -> <n frames> <frame hex>...
  D <n frames> <frame hex>... <n messages> <message hex or ->... <dropped> <too_big 0|1>

Run: python software/firmware/test/ble_vectors_to_txt.py [out.txt]
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SW = os.path.dirname(os.path.dirname(HERE))
VECTORS = os.path.join(SW, "protocol", "ble_frame_vectors.json")


def hx(text):
    return text.encode("utf-8").hex() or "-"


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "out", "ble_vectors.txt")
    with open(VECTORS, encoding="utf-8") as f:
        v = json.load(f)
    lines = ["# from %s (%s), max_message %d" % (os.path.relpath(VECTORS, SW), v["spec"], v["max_message"])]
    for c in v["encode"]:
        lines.append("# " + c["name"])
        lines.append("E %d %d %s %d %s" % (c["att_mtu"], c["start_counter"], hx(c["message"]), len(c["frames"]),
                                           " ".join(c["frames"])))
    for c in v["decode"]:
        lines.append("# " + c["name"])
        lines.append("D %d %s %d %s %d %d" % (len(c["frames"]), " ".join(c["frames"]), len(c["messages"]),
                                              " ".join(hx(m) for m in c["messages"]), c["dropped"], 1 if c["too_big"] else 0))
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="ascii", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    print("ble vectors: %d encode + %d decode cases -> %s" % (len(v["encode"]), len(v["decode"]), out))


if __name__ == "__main__":
    main()
