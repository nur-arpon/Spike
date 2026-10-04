"""Builds docs/robot-3d.html (the interactive 3D Spike on The Robot page) from a 3D preview.

Usage:  python docs/tools/make_robot_3d.py [path/to/preview_view.html]
Default source: preview_3d/spike_preview_v7_1_view.html. The preview file is copied unchanged and a
style block is appended that hides the design-review text and engineering controls, leaving only the
model, the camera views and the screen states, in the website's colours.
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
src = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "preview_3d" / "spike_preview_v7_1_view.html"
out = ROOT / "docs" / "robot-3d.html"

OVERRIDE = """
<!-- website override (docs/tools/make_robot_3d.py) -->
<meta name="robots" content="noindex">
<style id="site-override">
:root{--ground:transparent;--surface:#FFFAF3;--ink:#4A3326;--muted:#7A6152;--line:#E6D5C0;
  --stage-hi:#FCF5EB;--stage-lo:#EEDCC5;--chip:#FFFAF3;--accent:#B97A4F;--accent-ink:#FFFFFF}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--ground:transparent;--surface:#2A1F18;
  --ink:#F3DDBF;--muted:#C2A88F;--line:#46362A;--stage-hi:#3B2B21;--stage-lo:#1C1410;--chip:#2A1F18}}
html,body{height:100%;background:transparent}
body{overflow:hidden}
.wrap{max-width:none;padding:0;display:block;height:100%}
.wrap>*:not(.stage){display:none!important}
.stage{display:block;height:100%}
.stage aside,.labels,#xray,#labtog,#earin,#v-under,#v-top,#shape-seg,#tuft-seg,#tag-seg,.swatches,.hint{display:none!important}
.viewer{border:0;border-radius:0;aspect-ratio:auto;height:100%;max-height:none}
.toolbar{justify-content:center}
.optbar{bottom:12px;justify-content:center}
.seg button[aria-pressed="true"]{background:var(--accent);color:#fff}
.ol{display:none}
</style>
"""

html = src.read_text(encoding="utf-8")
html = re.sub(r"<title>.*?</title>", "<title>Spike in 3D</title>", html, count=1, flags=re.S)
html = html.replace("</head>", OVERRIDE + "</head>", 1)
out.write_text(html, encoding="utf-8")
print(f"wrote {out} ({out.stat().st_size/1e6:.2f} MB) from {src.name}")
