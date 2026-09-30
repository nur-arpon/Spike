// DEV ONLY: render a strip of hand-made face states.
//   node tools/probe.js <presetId> '<JSON array of partial states>' [scale]
// Each partial state is merged over the defaults. Writes tools/out/probe.png
'use strict';
var path = require('path'), fs = require('fs');
var { createCanvas } = require('@napi-rs/canvas');
function req(rel) { return require(path.join(__dirname, '..', rel)); }
var Gfx = req('gfx.js'), FP = req('params.js'), R = req('recipe.js'), FD = req('face_draw.js');
var a = process.argv.slice(2);
var rec = R.PRESETS[a[0]] || R.PRESETS.classic;
var states = JSON.parse(a[1] || '[{}]');
var s = +a[2] || 0.5;
var cv = createCanvas(Math.round(states.length * 480 * s), Math.round(272 * s)), ctx = cv.getContext('2d');
states.forEach(function (st, i) {
  ctx.save(); ctx.translate(i * 480 * s, 0); ctx.scale(s, s);
  FD.draw(Gfx.create(ctx), FP.merge(st), rec, st.t || 0.6);
  ctx.restore();
});
fs.writeFileSync(path.join(__dirname, 'out', 'probe.png'), cv.toBuffer('image/png'));
console.log('wrote tools/out/probe.png');
