# Updating the Spike website

The website is the `docs/` folder of this repository. GitHub Pages publishes it automatically at
<https://nur-arpon.github.io/Spike/> a minute or two after every push to `main`. There is no build step:
every file here is served exactly as it is.

| What | Where |
|---|---|
| Pages | `index.html` (Home), `meet-spike.html`, `robot.html`, `inside-spike.html`, `app.html`, `updates.html`, `privacy-policy.html`, `404.html` |
| Interactive 3D model (The Robot page) | `robot-3d.html`, made by `tools/make_robot_3d.py` |
| Inside Spike page (exploded view) | `inside-spike.html`; component `assets/components/exploded-view.js`; Spike content `assets/products/spike/` (copies, see below) |
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
- `links.android`, `status.android.version`, `.size`, `.sha256` - a new Android release: upload the file to GitHub Releases, then change these four values (the download link, version, size and checksum on `app.html` and Home update from them) and add an update entry. Search the `docs` folder for the old version number in the page text too.
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

## Update the Inside Spike exploded view

`inside-spike.html` uses the shared `<exploded-view>` component. The site holds **copies**: the component in
`assets/components/` and Spike's manifest, geometry and models in `assets/products/spike/`. After a CAD
re-export (new files in `preview_3d/exploded_v3_4c/`), or a new version of the component, refresh them. Run
from the repository folder:

```
powershell -File docs\tools\sync_exploded.ps1
```

That is the two copy steps in one go. By hand, from the repository folder:

```
copy ..\shared-components\exploded-view\exploded-view.js docs\assets\components\
xcopy /Y /I preview_3d\exploded_v3_4c\manifest.json docs\assets\products\spike\
xcopy /Y /I preview_3d\exploded_v3_4c\geometry.json docs\assets\products\spike\
xcopy /Y /I /E preview_3d\exploded_v3_4c\models docs\assets\products\spike\models\
```

For a new export folder name use `-Content preview_3d\exploded_v3_4d`. Nothing is deleted: a model removed from
the CAD stays in `docs/assets/products/spike/models/` until you remove it by hand. When the electronics stop
being stand-in shapes, change the "test model" note on `inside-spike.html` too.

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

## Edit the "Inside Spike" scroll story (beats, cards and part facts)

The scroll section is the first thing under the Home hero, and it is also at the top of `inside-spike.html`.
Both use the same component (`<exploded-view mode="scroll" layout="minimal" orbit>`, version 1.5.0) and the same
manifest, so one edit changes both. The stage is full-screen, edge to edge, and since 1.4.0 it follows iyO's
"Details" section: Spike big and centred, no captions on screen, only a small "INSIDE SPIKE" label top left (with
"Spike", or the part group in focus), a small Parts chip (all 8 cards in a drawer, or a sheet on phones) and the
Cream / Chocolate switch top right. Hovering a part (or tapping it on a phone) shows a small dark card with a
picture of that part, its name and a short line or two. The site header slides away while the stage is pinned
(`site.css`, the `data-pinned` rule). Taking `layout="minimal"` off the tag brings back the 1.3.0 look (big
captions bottom left, beat card, progress dots).

**Spinning Spike (orbit, since 1.5.0).** The `orbit` attribute on both tags lets visitors turn him at any point
of the story: drag with the mouse (the plain wheel still scrolls and takes him apart; Ctrl+wheel zooms), two fingers
on a phone (one finger still scrolls the page; pinch zooms), or the small "Spin" chip on touch screens, which makes
one finger spin until it is tapped again or the page scrolls. With the stage focused (Tab), the arrow keys spin and
tilt, + and - zoom, Home resets. After letting go he coasts a little, holds, and 2 s later glides back to the story's
angle over 1 s (with reduced motion he just stays). The first visit shows a small "Drag to spin" pill once
(remembered under `spike-stage-orbit-hint`). To turn it off, delete the word `orbit` from the tag in
`index.html` and `inside-spike.html`. The numbers (35 degrees of tilt, 0.7x to 2.4x zoom, 2 s hold, 1 s glide) are
the `ORBIT_*` constants near the top of the component. Screenshots: `software/app/screens/website/scroll-orbit/`.

All of its words live in the HUMAN manifest, never in `geometry.json` (that file is rewritten by every CAD export):

- edit `preview_3d/exploded_v3_4g/manifest.json` (the source), then copy it to the site with
  `powershell -File docs\tools\sync_exploded.ps1 -Content preview_3d\exploded_v3_4g`.

What to change, and where in that file:

- **The captions (beats):** `scroll.beats`. With the minimal layout their words are read only by screen readers;
  what shows is the top-left name, which is the beat's `label` (only "Senses" has one) or its card's title while
  Spike is fully apart, and `scroll.name` ("Spike") the rest of the time. Each has `at` (where it appears, from 0 = the top of the section to
  1 = the end), a `title` and one or two short sentences of `text`. `card` names the card that opens with it,
  and `parts` (optional) the parts that light up and get framed big while he is fully apart. `camera`
  (optional) turns the view for that beat: a camera id, or a direction such as `[0.85, -0.32, 1.15]` (from a
  little below, used for the dock). Keep them in order. Spike is fully apart between `explodeAt[1]` (0.30) and
  `assembleAt[0]` (0.84), so the beats that light parts go in there, about 0.1 apart for a comfortable dwell.
- **How close a beat zooms:** `scroll.focusMin` (0.6: a beat's parts may be framed up to about 1.7 times closer
  than the fully-apart view). `scroll.beatDim` is how faint everything else gets during a beat.
- **The 8 part cards:** `scroll.cards`. Each has an `id` (do not change it: beats point at it), a `title`, a
  `text` of two or three sentences, one short `fact`, and the `parts` that light up. `camera` only picks the
  angle of the small picture, which is drawn from the 3D model automatically.
- **A part's hover details:** in `parts` (or in its group in `groups`): `name`, `role` (what it does) and
  `fact` (one true fact). A group's `fact` is used for every part in it that has no fact of its own. The hover card
  shows `role` and `fact` together; when they run long (past about 130 characters), give the part a `brief` (two
  or three short lines, shortened from the role and fact, nothing new) and the card shows that instead. 19 parts
  have one now. The picture in the card is drawn from the 3D model automatically.
- **How the minimal layout feels:** `scroll.hoverDim` (0.42: how faint the other parts get while you hover one),
  `scroll.beatDim` (0.28: the same while a beat frames its group), `scroll.focusMin` (0.42) and a beat's own
  `focusMin` (the dock: 0.22) for how close a beat zooms, `scroll.spread` (0.8: the scroll story takes him apart
  to 80 % of the Explode tab's distances, so the parts are bigger on screen) and `scroll.apartTilt` (0.2: on a
  landscape screen the camera looks a little more level while he is apart).
- **The order he comes apart:** `scroll.layers` (legs out, lid up, boards lift, head opens). `carry` lets the
  head ride up with the lid so nothing passes through anything. In the 1.3.0 layout the layer titles show in a
  small pill ("Taking apart · Lid up"); its words are `scroll.apartLabel` and `scroll.togetherLabel`.
- **How far the parts spread:** each group's and part's `explode` (`distance` in mm, `add` for an extra
  offset). The legs go out 140 mm and front/back legs 55 mm apart; these are shared with the Explode tab on
  `inside-spike.html`.
- **What reduced motion shows:** `scroll.static` (a title and a sentence for the still, exploded view).

Rules for the words: every fact must be true and come from the project docs (`guide/FOLLOW_THE_ENERGY.md`,
`cad/release_v3_4/HOW_IT_WORKS.md`, `FIT_REPORT.md`, the `UPDATE_*.md` files, `software/firmware/README.md`).
Only claim what the real robot does; walk and give paw stay "in development". Plain, warm and short.

The page side, if ever needed: the section's attributes (`scroll-length`, 680 = about 6.8 screens of
scroll, `stage`, `stage-labels`, `storage-key`, `parts-title`, and `max-dpr` if you ever need to cap the
resolution) are on the `<exploded-view mode="scroll">` tag in `index.html` and `inside-spike.html`; the
visitor's Cream / Chocolate choice is remembered under the key `spike-stage`. The poster that shows until the
3D is ready is `assets/img/robot/spike-3d-opening.webp` (1040 x 1726): a transparent render of whole Spike at the
story's exact opening camera, cropped tight to his part boxes and without the floor shadow, so the swap to 3D
does not move or turn him. Re-make it after a CAD change that alters his outside, or a change to the default
camera or `scroll.sweep`, and put its new width and height on the `<img>` in both pages. (The older square
`spike-3d-whole.webp` is no longer used by the pages but is kept.) After any change, bump the `?v=` on
the manifest and component links in both pages so visitors get the new copy (and the `site.css?v=` when you
touch the CSS), and update `sitemap.xml`.

## The light field (the dusky glow and the dust behind every page)

Added 2026-10-14, made stronger the same day (v2) to match the dusk of Nur's portfolio Spike page
(`NurIfranArpon-v2/spike.html`). Three layers, all behind the content (`z-index: -1`, `pointer-events: none`):

1. **The aurora** (`<canvas id="field">`, in every page): slow fbm-noise bands, a warm spotlight that follows the
   pointer (with no pointer it rests low on the left), and darker corners. Half resolution, about 30 frames a second.
2. **The dust** (`<canvas id="dust">`, added by the script): 2,600 fine specks at 1366 x 768 (scaled by screen area,
   300 to 4,000) drifting on a curl-noise flow. The cursor, or a finger dragged on a phone, pushes and swirls them;
   a fast swipe leaves a wake, then they ease back into the flow. CPU sim in typed arrays (about 0.4 ms a frame on
   Nur's laptop); if it ever costs more than about 0.9 ms it drops a fifth of the specks at a time.
3. **The grain** (`<div class="grain">`, in every page): paper grain in CSS.

The code is `assets/js/light-field.js` (adapted from the portfolio's `assets/js/app.js`).

**Every knob is a CSS variable in `site.css`** (light values in `:root`, dark ones in the dark block): `--field-glow`,
`--field-accent`, `--field-aurora` (band strength), `--field-spot` and `--field-spot-size` (spotlight), `--field-speed`,
`--field-vignette`, `--field-scrim`, `--grain`, `--grain-size`, `--grain-blend`, `--dust-count`, `--dust-size` (px),
`--dust-opacity`, `--dust-color`, `--dust-push` and `--dust-radius` (px). Change a number and reload. The dark mode
uses the portfolio's Spike colours (glow `#6B3F22`, accent `#D9956A`).

**Text stays readable through a local scrim.** The script finds every bit of text that sits straight on the page
background, blurs a mask of where it is, and fades the aurora and the dust back to the page colour behind the
words (`--field-scrim`, .96 light / .9 dark). Everywhere else the effect stays at full strength. Measured over
428 text samples on 8 pages at 375 and 1366, light and dark, with the spotlight on the text: every one is at or
above WCAG AA (lowest 4.58:1 light, 4.93:1 dark). If you lower `--field-scrim` or raise `--grain`, re-check the
small grey text (`--ink-3`, `#7A6352` in light, darkened from `#8C7462` for AA). `.section--tint` is now 55 %
see-through so the field runs under those bands too.

Rules that must stay:
- `getContext('webgl', { alpha: true })` on both canvases. Never `alpha: false` or `powerPreference: 'low-power'`:
  an opaque full-screen canvas turned the whole page bright green on Nur's laptop.
- `#field` keeps `background: var(--bg)`, so with WebGL off or failing (the canvas then gets `data-off`) the page
  looks as it did before.
- Both loops stop while the tab is hidden and while the full-screen 3D story (`<exploded-view mode="scroll">`) is
  pinned (`data-pinned`); `<html>` gets `data-field-paused` meanwhile. With reduced motion there is one still
  frame (redrawn only when you scroll, so the scrim stays under the text), the dust stays still and the cursor does
  nothing.
- After changing `light-field.js` or `site.css`, bump the `?v=` on both links in **every** page (currently
  `20261014-field2`).
- Screenshots and short screen recordings of the check: `software/app/screens/website/light-field-v2/`.
