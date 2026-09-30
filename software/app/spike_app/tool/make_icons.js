/*
 * make_icons.js -- builds every launcher-icon source PNG from the ONE logo
 * file, assets/icon/spike_icon.svg (Screen Pup "Mix 1", final 29 Sep 2026).
 *
 *   icon_full.png   1024 px: squircle + art (legacy launchers, Play Store)
 *   icon_fg.png     1024 px: art only on transparent, scaled into the
 *                   adaptive-icon safe zone (Android 8+ masks it)
 *   icon_mono.png   1024 px: one-colour alpha silhouette for Android 13+
 *                   themed icons (face + ears solid, features cut out)
 *
 * Run from spike_app/:
 *   set NODE_PATH=..\..\face_v2\tools\node_modules   (uses @napi-rs/canvas)
 *   node tool/make_icons.js
 *   dart run flutter_launcher_icons
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { createCanvas, loadImage } = require('@napi-rs/canvas');

const SRC = path.join(__dirname, '..', 'assets', 'icon', 'spike_icon.svg');
const OUT = path.join(__dirname, '..', 'assets', 'icon', 'generated');
const S = 1024;

const svg = fs.readFileSync(SRC, 'utf8');
const art = svg.slice(svg.indexOf('<g id="art">'), svg.lastIndexOf('</svg>'));
const head = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" width="1024" height="1024">';

// Adaptive icons are 108 dp with a 66 dp safe circle: the art (ears to chin
// ~724 x 722 px, centred on 512,459) is scaled so it sits inside it.
const FG_SCALE = 0.66;
const fgSvg = `${head}<g transform="translate(512 518) scale(${FG_SCALE}) translate(-512 -459)">${art}</g></svg>`;

// Monochrome: solid silhouette in white, the features in black (black = cut out).
const MONO = { '#F3DDBF': '#FFFFFF', '#B97A4F': '#FFFFFF', '#C98A5E': '#FFFFFF', '#2E1F17': '#000000',
  '#2E2320': '#000000', '#E0564F': '#000000', '#B8403A': '#FFFFFF', '#4A2E24': '#000000' };
let monoArt = art.replace(/#[0-9A-Fa-f]{6}/g, (h) => MONO[h.toUpperCase()] || h);
// the eye highlights and nose shine stay white on the black eye (read as detail)
const monoSvg = `${head}<rect width="1024" height="1024" fill="#000"/>` +
  `<g transform="translate(512 518) scale(${FG_SCALE}) translate(-512 -459)">${monoArt}</g></svg>`;

async function render(text, file, post) {
  const img = await loadImage(Buffer.from(text));
  const c = createCanvas(S, S);
  const ctx = c.getContext('2d');
  ctx.drawImage(img, 0, 0, S, S);
  if (post) post(ctx);
  fs.writeFileSync(path.join(OUT, file), c.toBuffer('image/png'));
  console.log('wrote', file);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  await render(svg, 'icon_full.png');
  await render(fgSvg, 'icon_fg.png');
  await render(monoSvg, 'icon_mono.png', (ctx) => {
    const d = ctx.getImageData(0, 0, S, S);
    for (let i = 0; i < d.data.length; i += 4) {
      const lum = d.data[i];                 // white = keep, black = transparent
      d.data[i] = d.data[i + 1] = d.data[i + 2] = 255;
      d.data[i + 3] = lum;
    }
    ctx.putImageData(d, 0, 0);
  });
  // a preview of what a launcher shows: the middle 72 of 108 dp, circle-masked
  const prev = createCanvas(S, S), p = prev.getContext('2d');
  p.fillStyle = '#4A3326'; p.beginPath(); p.arc(512, 512, 512 * 72 / 108, 0, Math.PI * 2); p.fill();
  p.save(); p.clip();
  p.drawImage(await loadImage(fs.readFileSync(path.join(OUT, 'icon_fg.png'))), 0, 0, S, S);
  p.restore();
  fs.writeFileSync(path.join(OUT, 'preview_adaptive_circle.png'), prev.toBuffer('image/png'));
  console.log('wrote preview_adaptive_circle.png');
})().catch((e) => { console.error(e); process.exit(1); });
