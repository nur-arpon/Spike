"""Rename the product everywhere on the website after editing docs/data/site.json.

The pages read names from data/site.json when they load, so visitors see a rename at once. This script
also rewrites the plain text in the HTML files (page titles, descriptions, the text search engines and
no-JavaScript visitors see), so both stay the same.

Usage:  python docs/tools/apply_brand.py            (shows what would change)
        python docs/tools/apply_brand.py --write    (changes the files)

It remembers the names it last applied in docs/tools/brand_applied.json and replaces those old values with
the new ones from site.json in every docs/*.html file. Longest names are replaced first, so
"Spike - your personal desktop companion" is handled before "Spike".
"""
import json, pathlib, re, sys

DOCS = pathlib.Path(__file__).resolve().parents[1]
site = json.loads((DOCS / "data" / "site.json").read_text(encoding="utf-8"))["brand"]
stamp_file = DOCS / "tools" / "brand_applied.json"
old = json.loads(stamp_file.read_text(encoding="utf-8")) if stamp_file.exists() else dict(site)

pairs = sorted(((old[k], site[k]) for k in site if k in old and old[k] != site[k]), key=lambda p: -len(p[0]))
if not pairs:
    print("Nothing to rename: site.json matches the names last applied.")
    sys.exit(0)

write = "--write" in sys.argv
for f in sorted(DOCS.glob("*.html")):
    if f.name == "robot-3d.html":
        continue
    text = f.read_text(encoding="utf-8")
    new = text
    for a, b in pairs:
        # whole words only, and never inside a URL or path (".../Spike/..." stays as it is)
        new = re.sub(r"(?<![/\w-])" + re.escape(a) + r"(?![\w/])", lambda m: b, new)
    if new != text:
        print(("updated " if write else "would update ") + f.name)
        if write:
            f.write_text(new, encoding="utf-8", newline="\n")
if write:
    stamp_file.write_text(json.dumps(site, indent=2) + "\n", encoding="utf-8")
    print("Done. Also update software/app/spike_app/brand.json if the app is renamed too.")
else:
    print("Run again with --write to apply: " + ", ".join(f"{a!r} -> {b!r}" for a, b in pairs))
