/*
 * make_windows_icons.js -- every Windows icon and package logo from the ONE logo file,
 * assets/icon/spike_icon.svg (Screen Pup "Mix 1", final 29 Sep 2026). Nothing is hand-drawn.
 *
 *   windows/runner/resources/app_icon.ico      exe icon: 16..256 px (PNG-compressed ICO entries)
 *   assets/icon/tray.ico                       notification-area icon: 16, 20, 24, 32, 40, 48 px
 *   windows/packaging/Assets/*.png             MSIX logos in every scale / target size Windows asks for
 *
 * Run from spike_app/:
 *   set NODE_PATH=..\..\face_v2\tools\node_modules   (uses @napi-rs/canvas, like make_icons.js)
 *   node tool/make_windows_icons.js
 */
'use strict';
const fs = require('fs');
const path = require('path');
const { createCanvas, loadImage } = require('@napi-rs/canvas');

const ROOT = path.join(__dirname, '..');
const SRC = path.join(ROOT, 'assets', 'icon', 'spike_icon.svg');
const ASSETS = path.join(ROOT, 'windows', 'packaging', 'Assets');
const svgText = fs.readFileSync(SRC, 'utf8');

let logo; // the 1024 px squircle logo (transparent outside the squircle)

/** A square PNG of the logo at `size`, the logo taking `fill` of the side, centred. */
function square(size, fill = 1.0) {
  const c = createCanvas(size, size);
  const ctx = c.getContext('2d');
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  const d = Math.round(size * fill);
  const o = Math.round((size - d) / 2);
  ctx.drawImage(logo, o, o, d, d);
  return c.toBuffer('image/png');
}

/** A w x h PNG with the logo centred at `h * fill` high. */
function wide(w, h, fill) {
  const c = createCanvas(w, h);
  const ctx = c.getContext('2d');
  ctx.imageSmoothingQuality = 'high';
  const d = Math.round(h * fill);
  ctx.drawImage(logo, Math.round((w - d) / 2), Math.round((h - d) / 2), d, d);
  return c.toBuffer('image/png');
}

/** An ICO file whose entries are PNGs (supported by Windows since Vista, sharp at every size). */
function ico(sizes) {
  const pngs = sizes.map((s) => square(s));
  const head = Buffer.alloc(6 + 16 * sizes.length);
  head.writeUInt16LE(0, 0);
  head.writeUInt16LE(1, 2);
  head.writeUInt16LE(sizes.length, 4);
  let offset = head.length;
  sizes.forEach((s, i) => {
    const e = 6 + 16 * i;
    head.writeUInt8(s >= 256 ? 0 : s, e);
    head.writeUInt8(s >= 256 ? 0 : s, e + 1);
    head.writeUInt8(0, e + 2);
    head.writeUInt8(0, e + 3);
    head.writeUInt16LE(1, e + 4);
    head.writeUInt16LE(32, e + 6);
    head.writeUInt32LE(pngs[i].length, e + 8);
    head.writeUInt32LE(offset, e + 12);
    offset += pngs[i].length;
  });
  return Buffer.concat([head, ...pngs]);
}

function write(file, buf) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, buf);
  console.log('wrote', path.relative(ROOT, file));
}

(async () => {
  logo = await loadImage(Buffer.from(svgText));

  write(path.join(ROOT, 'windows', 'runner', 'resources', 'app_icon.ico'), ico([16, 20, 24, 32, 40, 48, 64, 128, 256]));
  write(path.join(ROOT, 'assets', 'icon', 'tray.ico'), ico([16, 20, 24, 32, 40, 48]));

  // MSIX logos (learn.microsoft.com "App icons and logos"): scale-XXX for tiles, targetsize-XX
  // (plated + altform-unplated) for the taskbar, Start list and File Explorer.
  const scales = [100, 125, 150, 200, 400];
  for (const sc of scales) {
    const k = sc / 100;
    write(path.join(ASSETS, `Square44x44Logo.scale-${sc}.png`), square(Math.round(44 * k), 0.92));
    write(path.join(ASSETS, `Square71x71Logo.scale-${sc}.png`), square(Math.round(71 * k), 0.78));
    write(path.join(ASSETS, `Square150x150Logo.scale-${sc}.png`), square(Math.round(150 * k), 0.66));
    write(path.join(ASSETS, `Wide310x150Logo.scale-${sc}.png`), wide(Math.round(310 * k), Math.round(150 * k), 0.66));
    write(path.join(ASSETS, `Square310x310Logo.scale-${sc}.png`), square(Math.round(310 * k), 0.62));
    write(path.join(ASSETS, `StoreLogo.scale-${sc}.png`), square(Math.round(50 * k), 1.0));
    write(path.join(ASSETS, `SplashScreen.scale-${sc}.png`), wide(Math.round(620 * k), Math.round(300 * k), 0.5));
  }
  for (const t of [16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256]) {
    write(path.join(ASSETS, `Square44x44Logo.targetsize-${t}.png`), square(t, 1.0));
    write(path.join(ASSETS, `Square44x44Logo.targetsize-${t}_altform-unplated.png`), square(t, 1.0));
    write(path.join(ASSETS, `Square44x44Logo.targetsize-${t}_altform-lightunplated.png`), square(t, 1.0));
  }
  // the Store listing's 300 x 300 app tile / box art source
  write(path.join(ROOT, '..', 'store', 'images', 'store_logo_300.png'), square(300, 1.0));
})().catch((e) => { console.error(e); process.exit(1); });
