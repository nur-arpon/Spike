# Updating the Spike website

The website is the `docs/` folder of this repository. GitHub Pages publishes it automatically at
<https://nur-arpon.github.io/Spike/> a minute or two after every push to `main`. There is no build step:
every file here is served exactly as it is.

| What | Where |
|---|---|
| Pages | `index.html` (Home), `meet-spike.html`, `robot.html`, `app.html`, `updates.html`, `privacy-policy.html`, `404.html` |
| Interactive 3D model (The Robot page) | `robot-3d.html`, made by `tools/make_robot_3d.py` |
| Design (colours, type, layout) | `assets/css/site.css` (one file; colour tokens at the top) |
| Behaviour | `assets/js/site.js` (menu, image switcher, screenshot tabs, 3D loader, reads the data files) |
| Names, links, statuses, robot build steps | `data/site.json` |
| Updates / changelog | `data/updates.json` |
| Images | `assets/img/` (`robot/`, `app/`, `cad/`, logo, icons, `og.png` for link previews) |
| Search engines | `sitemap.xml`, `robots.txt` |

## Post an update (the common case)

1. Open `data/updates.json`.
2. Copy an existing entry and paste it at the **top** of the `updates` list (newest first):

   ```json
   {
     "date": "2026-10-12",
     "tag": "Robot",
     "title": "The first print is done",
     "text": "One or two plain sentences about what changed and why it matters.",
     "link": "robot.html",
     "linkText": "See the robot"
   },
   ```

   - `date` is `YYYY-MM-DD`. The list is sorted by date anyway, so order mistakes are harmless.
   - `tag` is one word. The filter buttons on the Updates page are made from the tags in use, so a new tag
     (for example `Video`) gets its own button automatically. Current tags: App, Robot, Brain, Face, Design,
     Website.
   - `link` and `linkText` are optional. Use a page (`app.html`), a section (`robot.html#design`) or a full URL.
3. Commit and push. The newest three updates also appear on the Home page.

Check the file is still valid JSON (a missing comma breaks the list): paste it into any JSON validator, or
run `python -m json.tool docs/data/updates.json`.

## Change a status, a version or the robot build progress

All in `data/site.json`:

- `status.windows.version` - the version shown on The App page (for example `1.0.2`).
- `status.android` - when the phone app reaches Google Play, change it to
  `{ "label": "On Google Play", "state": "live" }`, then update the wording on `app.html` (the "Not on
  Google Play yet" line and the phone section) and add a Play link.
- `status.robot.label` - for example `"First prototype assembled"`.
- `state` values: `live` (green dot), `soon` (amber), `build` (caramel).
- `robotBuild` - the five steps on The Robot page. Each has `title`, `text` and `state`: `done`, `now` or
  `next`. Exactly one step should be `now`. Steps can be added or removed; the row adapts.

The HTML pages contain the same text as a fallback for search engines and visitors without JavaScript. If you
change a status label, change the same words in the pages too (search the `docs` folder for the old label).

## Change the product name, publisher or developer

The names live in one place: `brand` in `data/site.json`, mirroring `software/app/spike_app/brand.json`
(productName "Spike", storeName "Spike - your personal desktop companion", publisher "SpaceZ",
developer "Nur Ifran Arpon").

1. Edit the values in `data/site.json`.
2. Run `python docs/tools/apply_brand.py` to see which pages would change, then
   `python docs/tools/apply_brand.py --write` to rewrite them. URLs such as `github.com/nur-arpon/Spike` are
   left alone.
3. Re-render `assets/img/og.png` (the link-preview picture has the name drawn in it): open
   `docs/tools/og.html` in Chrome at 1200 x 630 and take a screenshot, or ask Claude to re-render it.
4. Read the pages once: sentences that use the name in the middle of prose may want rewording.

## Swap or add images

- Use WebP (or PNG/JPG), around 1600 px wide, and keep each under about 300 KB.
- To swap an image, replace the file under the same name in `assets/img/...` - nothing else changes.
- To use a new image, add it to `assets/img/` and point the page at it: `src="assets/img/robot/new.webp"`,
  with real `width` and `height` attributes and an `alt` text that says what the picture shows.
- Robot renders have a dark-mode twin (`hero-dark.webp`, `close-dark.webp`...), used through a `<picture>`
  element. If you replace a light render, replace its dark twin too (or delete the `<source>` line).
- App screenshots must not show private data: no addresses, QR codes, keys, notifications or personal names.

## Update the interactive 3D model

When a new 3D preview exists in `preview_3d/` (a single-file `..._view.html`), run:

```
python docs/tools/make_robot_3d.py preview_3d/spike_preview_v7_2_view.html
```

It copies the preview to `docs/robot-3d.html` and hides the design-review text and engineering controls.

## Change the privacy policy

Edit `privacy-policy.html` directly; its address must stay exactly
`https://nur-arpon.github.io/Spike/privacy-policy.html` (the Microsoft Store links to it). Keep it in step
with the app's Store kit template (`software/app/store/templates/privacy-policy.html`) and change the
"Last updated" date when the meaning changes.

## Add a page

Copy the closest existing page, keep the `<head>`, header and footer as they are, replace what is inside
`<main>`, and set its `<title>`, description and canonical URL. Then add it to the navigation in **every**
page (the header and footer blocks are repeated in each file) and to `sitemap.xml`.

## Check before pushing

- Open the page locally: from the repository folder run `python -m http.server 8000` and visit
  `http://localhost:8000/docs/`. (Opening the file directly works for most things, but the data files need a
  server.)
- After pushing, the site updates within a few minutes; the build status is under the repository's
  **Actions** tab ("pages build and deployment").
