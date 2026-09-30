// DEV ONLY: render one face region zoomed.  node tools/zoom.js <conceptId> <mood> <x> <y> <w> <h> <scale> [mode]
'use strict';
var path = require('path'), fs = require('fs');
var { createCanvas } = require('@napi-rs/canvas');
function req(rel) { return require(path.join(__dirname, '..', rel)); }
var Gfx = req('gfx.js'), FP = req('params.js'), Recipe = req('recipe.js'), FaceDraw = req('face_draw.js'), Moods = req('moods.js');
var a = process.argv.slice(2);
var rec = Recipe.normalize(Recipe.CONCEPTS[a[0]] || Recipe.PRESETS[a[0]] || Recipe.BASE);
var x = +a[2] || 0, y = +a[3] || 0, w = +a[4] || 480, h = +a[5] || 272, s = +a[6] || 2;
var cv = createCanvas(Math.round(w * s), Math.round(h * s)), ctx = cv.getContext('2d');
ctx.scale(s, s); ctx.translate(-x, -y);
FaceDraw.draw(Gfx.create(ctx), FP.merge(Moods.getTarget(a[1] || 'neutral', a[7] || 'dog')), rec, 0.6);
var out = path.join(__dirname, 'out', 'zoom.png');
fs.writeFileSync(out, cv.toBuffer('image/png'));
console.log('wrote', out);
