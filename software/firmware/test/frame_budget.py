"""frame_budget.py -- the face's frame budget: measured work per frame on the PC build, and an ESTIMATE
of the render time on the ESP32-S3 (240 MHz, octal PSRAM frame buffer) from a per-operation cycle model.

Input : test/out/frame_stats.csv (written by `face_pc cases`, one row per golden case = 285 faces:
        every preset x key mood, every mood for Spike and Spicy, dice faces, frames from the engine)
Output: test/out/frame_budget.txt

The cycle costs are ASSUMPTIONS (documented in DESIGN.md), deliberately on the slow side. The screen
board logs its real render time every 10 s ("face: .. fps, render .. ms"): compare on day 1.
"""
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
MHZ = 240.0
CYCLES = {  # per unit of work, ESP32-S3 at 240 MHz, float FPU, frame buffer in octal PSRAM
    "path_points": 250,  # tessellate + transform one path point (sinf/cosf in newlib ~100-150 cycles each)
    "edge_rows": 80,     # one edge's area contribution to one pixel row
    "scanned": 10,       # clear + prefix-sum + classify one accumulator cell (internal SRAM)
    "px_solid": 12,      # write one RGB565 pixel to PSRAM (~40 MB/s effective write bandwidth)
    "px_blend": 45,      # read-modify-write one PSRAM pixel with alpha
}
OVERHEAD_MS = 0.6  # behaviour update + face params + particles + queues per frame


def main():
    rows = list(csv.DictReader(open(os.path.join(OUT, "frame_stats.csv"))))
    est, pcms = [], []
    for r in rows:
        cyc = sum(float(r[k]) * c for k, c in CYCLES.items() if k in r)
        est.append(cyc / MHZ / 1000.0 + OVERHEAD_MS)
        pcms.append(float(r["ms"]))
    est_sorted = sorted(est)
    n = len(est)
    p50, p95, mx = est_sorted[n // 2], est_sorted[int(n * 0.95)], est_sorted[-1]
    worst = sorted(zip(est, [r["name"] for r in rows]), reverse=True)[:5]
    push_ms = 480 * 272 * 2 * 8 / 4 / 32e6 * 1000  # 4-bit QSPI at 32 MHz
    lines = [
        "face frame budget (target 30 fps = 33.3 ms per frame)",
        "PC build (MSVC /O2, this laptop): mean %.2f ms, max %.2f ms over %d faces" % (sum(pcms) / n, max(pcms), n),
        "work per frame: " + ", ".join("%s mean %.0f max %.0f" % (k, sum(float(r[k]) for r in rows) / n, max(float(r[k]) for r in rows))
                                        for k in CYCLES if k in rows[0]),
        "ESP32-S3 render ESTIMATE (cycle model, one core): median %.1f ms, 95th pct %.1f ms, max %.1f ms" % (p50, p95, mx),
        "panel push (other core, overlapped with rendering): %.1f ms per frame at 32 MHz QSPI" % push_ms,
        "=> expected: %s" % ("30 fps for typical faces" if p50 < 33.3 else "below 30 fps") +
        ("; the heaviest faces drop to about %.0f fps" % (1000 / mx) if mx > 33.3 else "; every face fits 30 fps"),
        "heaviest faces: " + ", ".join("%s %.1f ms" % (nm, e) for e, nm in worst),
        "cycle model: " + ", ".join("%s %d" % kv for kv in CYCLES.items()) + ", + %.1f ms overhead" % OVERHEAD_MS,
    ]
    open(os.path.join(OUT, "frame_budget.txt"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
