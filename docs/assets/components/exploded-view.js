/*!
 * <exploded-view> — a reusable, manifest-driven 3D exploded view.
 * Modes: Explode (slider), Build (step by step), Follow the energy (stage by stage),
 * and (1.2.0) mode="scroll": a sticky stage that the page scroll takes apart and puts back together, with part cards.
 * 1.3.0: the scroll stage is full-screen (edge to edge), framed per beat, with overlay captions, a beat card,
 * a Parts drawer and an adaptive pixel ratio.
 * One ES module, no build step. Needs an import map that maps "three" and "three/addons/" (see README.md).
 * All product content lives in the manifest JSON; this file holds no product knowledge.
 * (c) Nur Ifran Arpon / SpaceZ.
 */
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

const VERSION = '1.3.0';
const MODES = ['explode', 'build', 'energy'];
/** 1.2.0: one model cache for the whole page, so two views of the same product (scroll + tabs) download each GLB once.
 *  Each view clones the scene and gives it its own materials, so sharing is safe. */
const GLTF_CACHE = new Map();
const MODE_LABELS = {
  explode: ['Explode', 'Explode'],
  build: ['Build', 'Build it'],
  energy: ['Energy', 'Follow the energy'],
};

/* ------------------------------------------------------------------------------------------------
 * Styles. Every colour, radius and size is a CSS custom property on the host, so a site can theme it:
 *   exploded-view { --ev-accent: #2a6; --ev-height: 640px; }
 * ---------------------------------------------------------------------------------------------- */
const CSS = /* css */ `
:host {
  --ev-bg: #fbf5ec;
  --ev-surface: #fffaf3;
  --ev-stage-top: #fff9f0;
  --ev-stage-bottom: #f1e3cf;
  --ev-text: #3b2a20;
  --ev-muted: #76604f;
  --ev-border: #e6d5bd;
  --ev-accent: #b97a4f;
  --ev-accent-strong: #8a5530;
  --ev-accent-soft: #f3e2cf;
  --ev-on-accent: #fffaf3;
  --ev-energy: #f0a43a;
  --ev-energy-soft: #fde7c4;
  --ev-shadow: 0 1px 2px rgba(74, 51, 38, .08), 0 8px 24px rgba(74, 51, 38, .08);
  --ev-radius: 18px;
  --ev-radius-small: 12px;
  --ev-font: inherit;
  --ev-height: 600px;
  --ev-mobile-stage-height: 380px;
  --ev-panel-width: 360px;
  --ev-control-size: 48px;
  display: block;
  container-type: inline-size;
  font-family: var(--ev-font);
  color: var(--ev-text);
  -webkit-tap-highlight-color: transparent;
}
:host([hidden]) { display: none; }
/* Warm dark theme. Light stays the default; theme="dark" forces dark, theme="auto" follows the visitor's setting. */
:host([theme="dark"]) {
  --ev-bg: #1d1611; --ev-surface: #241b15; --ev-stage-top: #2c221a; --ev-stage-bottom: #18120e;
  --ev-text: #f3e6d6; --ev-muted: #bba48e; --ev-border: #3a2d23;
  --ev-accent: #d39a6a; --ev-accent-strong: #e8b88c; --ev-accent-soft: #3a2b20; --ev-on-accent: #1d1611;
  --ev-energy: #f4b04e; --ev-energy-soft: #4a3518;
  --ev-shadow: 0 1px 2px rgba(0, 0, 0, .3), 0 8px 24px rgba(0, 0, 0, .3);
}
@media (prefers-color-scheme: dark) {
  :host([theme="auto"]) {
    --ev-bg: #1d1611; --ev-surface: #241b15; --ev-stage-top: #2c221a; --ev-stage-bottom: #18120e;
    --ev-text: #f3e6d6; --ev-muted: #bba48e; --ev-border: #3a2d23;
    --ev-accent: #d39a6a; --ev-accent-strong: #e8b88c; --ev-accent-soft: #3a2b20; --ev-on-accent: #1d1611;
    --ev-energy: #f4b04e; --ev-energy-soft: #4a3518;
    --ev-shadow: 0 1px 2px rgba(0, 0, 0, .3), 0 8px 24px rgba(0, 0, 0, .3);
  }
}
* { box-sizing: border-box; }
.ev {
  background: var(--ev-bg);
  border: 1px solid var(--ev-border);
  border-radius: var(--ev-radius);
  overflow: hidden;
  box-shadow: var(--ev-shadow);
}
.ev-head {
  display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 10px 16px;
  padding: 14px 16px 12px;
  border-bottom: 1px solid var(--ev-border);
}
.ev-title { margin: 0; font-size: 1.05rem; font-weight: 700; line-height: 1.25; letter-spacing: -.01em; }
.ev-sub { margin: 2px 0 0; font-size: .85rem; color: var(--ev-muted); line-height: 1.35; }
:host([hide-title]) .ev-titles { display: none; }
.ev-tabs {
  display: flex; gap: 4px; padding: 4px; margin: 0;
  background: var(--ev-accent-soft); border-radius: 999px;
  flex: 1 1 auto; max-width: 460px;
}
:host([hide-title]) .ev-tabs { max-width: none; }
.ev-tab {
  flex: 1 1 0; min-height: 44px; padding: 0 12px;
  border: 0; border-radius: 999px; background: transparent;
  font: inherit; font-size: .92rem; font-weight: 650; color: var(--ev-accent-strong);
  cursor: pointer; white-space: nowrap;
  transition: background .2s, color .2s, box-shadow .2s;
}
.ev-tab:hover { background: rgba(255, 255, 255, .55); }
.ev-tab[aria-selected="true"] { background: var(--ev-surface); color: var(--ev-text); box-shadow: 0 1px 3px rgba(74, 51, 38, .18); }
.ev-tab .long { display: none; }
.ev-tab:focus-visible, .ev-btn:focus-visible, .ev-chip:focus-visible, .ev-range:focus-visible, .ev-x:focus-visible {
  outline: 3px solid var(--ev-accent-strong); outline-offset: 2px;
}
.ev-body { display: flex; flex-direction: column; }
.ev-stage {
  position: relative; height: var(--ev-mobile-stage-height); min-height: 280px;
  background: radial-gradient(120% 90% at 50% 25%, var(--ev-stage-top) 0%, var(--ev-stage-bottom) 100%);
  overflow: hidden; touch-action: none; user-select: none; -webkit-user-select: none;
}
.ev-stage canvas { display: block; width: 100%; height: 100%; outline: none; }
.ev-panel { padding: 16px; display: flex; flex-direction: column; gap: 14px; background: var(--ev-surface); }
.ev-pane[hidden] { display: none !important; }
.ev-pane { display: flex; flex-direction: column; gap: 14px; }
.ev-kicker { font-size: .75rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; color: var(--ev-accent-strong); margin: 0; }
.ev-h { margin: 0; font-size: 1.15rem; line-height: 1.3; font-weight: 700; }
.ev-p { margin: 0; font-size: .97rem; line-height: 1.55; color: var(--ev-text); }
.ev-hint { margin: 0; font-size: .85rem; color: var(--ev-muted); line-height: 1.45; }
.ev-badge {
  align-self: flex-start; display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px; border-radius: 999px; white-space: nowrap;
  background: var(--ev-energy-soft); color: var(--ev-text); font-size: .85rem; font-weight: 650;
}
.ev-badge[hidden] { display: none; }
.ev-badge::before { content: ""; width: 8px; height: 8px; border-radius: 50%; background: var(--ev-energy); box-shadow: 0 0 0 3px rgba(240, 164, 58, .25); }

/* Slider: big thumb, thick track, filled to --p */
.ev-slider { display: flex; flex-direction: column; gap: 6px; }
.ev-slider-labels { display: flex; justify-content: space-between; font-size: .82rem; color: var(--ev-muted); font-weight: 600; }
.ev-range {
  --p: 0%;
  -webkit-appearance: none; appearance: none; width: 100%; height: 44px; margin: 0; background: transparent; cursor: pointer;
  touch-action: pan-y;
}
.ev-range::-webkit-slider-runnable-track {
  height: 12px; border-radius: 999px;
  background: linear-gradient(to right, var(--ev-accent) 0, var(--ev-accent) var(--p), var(--ev-border) var(--p), var(--ev-border) 100%);
}
.ev-range::-moz-range-track { height: 12px; border-radius: 999px; background: var(--ev-border); }
.ev-range::-moz-range-progress { height: 12px; border-radius: 999px; background: var(--ev-accent); }
.ev-range::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none; width: 32px; height: 32px; margin-top: -10px; border-radius: 50%;
  background: var(--ev-surface); border: 4px solid var(--ev-accent-strong); box-shadow: 0 2px 6px rgba(74, 51, 38, .3);
}
.ev-range::-moz-range-thumb {
  width: 24px; height: 24px; border-radius: 50%;
  background: var(--ev-surface); border: 4px solid var(--ev-accent-strong); box-shadow: 0 2px 6px rgba(74, 51, 38, .3);
}
.ev-range:active::-webkit-slider-thumb { transform: scale(1.08); }

.ev-row { display: flex; gap: 10px; align-items: center; }
.ev-btn {
  min-height: var(--ev-control-size); min-width: var(--ev-control-size); padding: 0 18px;
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  border-radius: 999px; border: 1.5px solid var(--ev-border); background: var(--ev-surface);
  font: inherit; font-size: .95rem; font-weight: 650; color: var(--ev-text); cursor: pointer;
  transition: background .15s, border-color .15s, transform .1s;
}
.ev-btn:hover { border-color: var(--ev-accent); }
.ev-btn:active { transform: scale(.97); }
.ev-btn[disabled] { opacity: .45; cursor: default; transform: none; }
.ev-btn.primary { background: var(--ev-accent-strong); border-color: var(--ev-accent-strong); color: var(--ev-on-accent); }
.ev-btn.primary:hover { background: var(--ev-accent); border-color: var(--ev-accent); }
.ev-btn.grow { flex: 1 1 0; }
.ev-btn svg { width: 20px; height: 20px; flex: none; }
.ev-count { font-variant-numeric: tabular-nums; }

/* Stage overlays */
.ev-chips {
  position: absolute; left: 0; right: 0; bottom: 0; display: flex; gap: 6px; flex-wrap: nowrap;
  padding: 10px; overflow-x: auto; scrollbar-width: none; pointer-events: none; justify-content: flex-start;
  touch-action: pan-x;
}
.ev-chips::-webkit-scrollbar { display: none; }
.ev-chip {
  pointer-events: auto; flex: none; min-height: 40px; padding: 0 14px; border-radius: 999px;
  border: 1px solid var(--ev-border); background: rgba(255, 250, 243, .88); backdrop-filter: blur(6px);
  font: inherit; font-size: .85rem; font-weight: 650; color: var(--ev-text); cursor: pointer; white-space: nowrap;
}
.ev-chip[aria-pressed="true"] { background: var(--ev-accent-strong); color: var(--ev-on-accent); border-color: var(--ev-accent-strong); }
.ev-tip {
  position: absolute; left: 0; top: 0; max-width: min(280px, 80%); padding: 8px 12px; border-radius: var(--ev-radius-small);
  background: rgba(59, 42, 32, .92); color: #fffaf3; font-size: .85rem; line-height: 1.4; pointer-events: none;
  transform: translate(-9999px, 0); box-shadow: 0 6px 18px rgba(0, 0, 0, .18); z-index: 3;
}
.ev-tip b { display: block; font-size: .9rem; }
.ev-card {
  position: absolute; left: 10px; right: 10px; top: 10px; display: flex; gap: 10px; align-items: flex-start;
  padding: 10px 8px 10px 14px; border-radius: var(--ev-radius-small);
  background: rgba(255, 250, 243, .95); border: 1px solid var(--ev-border); box-shadow: var(--ev-shadow); z-index: 4;
  max-width: 420px;
}
.ev-card[hidden] { display: none; }
.ev-card-text { flex: 1 1 auto; font-size: .9rem; line-height: 1.45; }
.ev-card-text b { display: block; font-size: .98rem; }
.ev-x {
  flex: none; width: 40px; height: 40px; border-radius: 50%; border: 0; background: transparent; cursor: pointer;
  color: var(--ev-muted); font-size: 22px; line-height: 1;
}
.ev-x:hover { background: var(--ev-accent-soft); }
.ev-label {
  position: absolute; left: 0; top: 0; padding: 6px 12px; border-radius: 999px; white-space: nowrap;
  background: var(--ev-energy); color: #3b2a20; font-size: .82rem; font-weight: 750; pointer-events: none;
  transform: translate(-9999px, 0); box-shadow: 0 4px 14px rgba(240, 164, 58, .45); z-index: 2;
}
.ev-label.alt { background: var(--ev-surface); color: var(--ev-text); border: 1px solid var(--ev-border); box-shadow: var(--ev-shadow); }
.ev-loading {
  position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px;
  color: var(--ev-muted); font-size: .92rem; background: transparent; z-index: 5; text-align: center; padding: 16px;
}
.ev-loading[hidden] { display: none; }
.ev-bar { width: min(240px, 70%); height: 8px; border-radius: 999px; background: var(--ev-border); overflow: hidden; }
.ev-bar i { display: block; height: 100%; width: 0; background: var(--ev-accent); border-radius: 999px; transition: width .2s; }
.ev-error { color: #9b3b26; font-weight: 600; }
.ev-steps { display: flex; gap: 6px; flex-wrap: wrap; }
.ev-dot {
  width: 28px; height: 28px; border-radius: 50%; border: 1.5px solid var(--ev-border); background: var(--ev-surface);
  font: inherit; font-size: .72rem; font-weight: 700; color: var(--ev-muted); cursor: pointer; padding: 0;
}
.ev-dot[aria-current="step"] { background: var(--ev-energy); border-color: var(--ev-energy); color: #3b2a20; }
.ev-dot.done { background: var(--ev-energy-soft); border-color: var(--ev-energy-soft); color: var(--ev-text); }
.ev-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

/* Wide containers: model left, panel right */
@container (min-width: 560px) {
  .ev-tab .short { display: none; }
  .ev-tab .long { display: inline; }
  .ev-stage { height: calc(var(--ev-mobile-stage-height) + 60px); }
}
@container (min-width: 880px) {
  .ev-body { flex-direction: row; height: var(--ev-height); }
  .ev-stage { flex: 1 1 auto; height: 100%; }
  .ev-panel { width: var(--ev-panel-width); flex: none; border-left: 1px solid var(--ev-border); overflow-y: auto; padding: 22px; }
  .ev-head { padding: 16px 22px 14px; }
  .ev-card { right: auto; width: 360px; }
}
@media (prefers-reduced-motion: reduce) {
  .ev-tab, .ev-btn, .ev-bar i { transition: none; }
}
`;

/* ------------------------------------------------------------------------------------------------
 * 1.2.0 scroll mode styles. Used instead of CSS above when the element has mode="scroll".
 * Two stage palettes: stage="dark" (the default here) and stage="light". Every colour is a custom property.
 * ---------------------------------------------------------------------------------------------- */
const SCROLL_CSS = /* css */ `
:host {
  --ev-font: inherit;
  --ev-display-font: inherit;
  --ev-sticky-top: 0px;
  --ev-scroll-length: 640vh;
  --ev-panel-width: 380px;
  --ev-gutter: clamp(16px, 3.4cqi, 56px);
  /* dark stage (chocolate) */
  --sv-hi: #3B2B21; --sv-lo: #120D0A; --sv-panel: rgba(28, 21, 16, .86); --sv-scrim: rgba(18, 13, 10, .78);
  --sv-ink: #F6EADB; --sv-ink-2: #DCC8B4; --sv-ink-3: #B39A85;
  --sv-line: rgba(246, 234, 219, .14); --sv-card: rgba(246, 234, 219, .04); --sv-card-hover: rgba(246, 234, 219, .08);
  --sv-card-active: rgba(246, 234, 219, .1); --sv-thumb: rgba(246, 234, 219, .07);
  --sv-accent: #E7AA80; --sv-seg: rgba(30, 22, 17, .62); --sv-seg-on: #F3DDBF; --sv-seg-on-ink: #2E2019;
  --sv-tip-bg: rgba(250, 240, 226, .97); --sv-tip-ink: #2E2019; --sv-tip-ink-2: #66503F; --sv-tip-accent: #8A5330;
  --sv-glow: #D9956A; --sv-shadow: 0 18px 48px rgba(0, 0, 0, .38);
  display: block;
  container-type: inline-size;
  font-family: var(--ev-font);
  color: var(--sv-ink);
  -webkit-tap-highlight-color: transparent;
}
:host([stage="light"]) {
  --sv-hi: #FFFAF2; --sv-lo: #E8D2B6; --sv-panel: rgba(255, 250, 243, .9); --sv-scrim: rgba(240, 225, 205, .82);
  --sv-ink: #2A1C15; --sv-ink-2: #5A4434; --sv-ink-3: #7E6655;
  --sv-line: rgba(74, 51, 38, .16); --sv-card: rgba(255, 253, 249, .5); --sv-card-hover: rgba(255, 253, 249, .85);
  --sv-card-active: #FFFDF9; --sv-thumb: rgba(201, 138, 94, .14);
  --sv-accent: #8A5330; --sv-seg: rgba(255, 250, 243, .72); --sv-seg-on: #4A3326; --sv-seg-on-ink: #FBF0E0;
  --sv-tip-bg: rgba(46, 32, 25, .95); --sv-tip-ink: #FBF0E0; --sv-tip-ink-2: #DCC6AA; --sv-tip-accent: #F3DDBF;
  --sv-glow: #C98A5E; --sv-shadow: 0 18px 44px rgba(74, 51, 38, .2);
}
:host([hidden]) { display: none; }
* { box-sizing: border-box; }
.sv [hidden] { display: none !important; }
.sv { position: relative; height: var(--ev-scroll-length); }
/* 1.3.0: a full-bleed, full-screen stage. While the section comes on screen it is a rounded card that grows to
   the edges as it pins (the inset is set from the scroll position), and it shrinks back as it leaves. */
.sv-sticky {
  position: -webkit-sticky; position: sticky; top: var(--ev-sticky-top);
  height: calc(100vh - var(--ev-sticky-top)); height: calc(100svh - var(--ev-sticky-top));
  min-height: 480px; overflow: hidden;
  background: radial-gradient(120% 100% at 62% 38%, var(--sv-hi) 0%, var(--sv-lo) 100%);
  clip-path: inset(var(--sv-iy, 0px) var(--sv-ix, 0px) round var(--sv-ir, 0px));
}
.sv-stage { position: absolute; inset: 0; overflow: hidden; user-select: none; -webkit-user-select: none; }
.sv-stage canvas { position: absolute; inset: 0; display: block; width: 100%; height: 100%; outline: none; touch-action: pan-y; }
.sv-poster { position: absolute; left: 0; top: 0; width: 100%; height: 100%; display: grid; place-items: center; pointer-events: none; transition: opacity .6s ease; }
.sv-poster ::slotted(img) { width: 100%; height: 100%; object-fit: contain; }
.sv-poster.gone { opacity: 0; }
/* a soft wash behind the caption, so the words read over any part in either stage colour */
.sv-wash {
  position: absolute; inset: 0; z-index: 2; pointer-events: none;
  background: linear-gradient(to top, var(--sv-scrim) 0%, transparent 34%);
}

/* the caption: big headline and one line, lower third */
.sv-beat {
  position: absolute; left: 16px; right: 44px; bottom: calc(18px + env(safe-area-inset-bottom, 0px)); z-index: 3;
  pointer-events: none; display: grid; gap: 8px; max-width: 40rem;
}
.sv-kicker { margin: 0; display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; font-size: .74rem; font-weight: 750; letter-spacing: .14em; text-transform: uppercase; color: var(--sv-accent); }
.sv-kicker .sv-count { font-variant-numeric: tabular-nums; color: var(--sv-ink-3); letter-spacing: .08em; }
.sv-layer {
  position: absolute; left: 0; bottom: calc(100% + 12px);
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 10px; border-radius: 999px; white-space: nowrap;
  font-size: .72rem; letter-spacing: .06em; text-transform: none; font-weight: 700;
  background: color-mix(in srgb, var(--sv-accent) 18%, transparent); color: var(--sv-ink); transition: opacity .25s;
}
.sv-layer[hidden] { display: none; }
.sv-beat h3 {
  margin: 0; font-family: var(--ev-display-font); font-weight: 600; font-size: clamp(2rem, 9cqi, 2.6rem);
  line-height: 1.02; letter-spacing: -.02em; color: var(--sv-ink); text-wrap: balance;
  text-shadow: 0 1px 18px var(--sv-lo);
}
.sv-beat p.sv-text { margin: 0; font-size: 1rem; line-height: 1.5; color: var(--sv-ink-2); max-width: 34rem; text-wrap: pretty; text-shadow: 0 1px 12px var(--sv-lo); }
.sv-beat.in > :not(.sv-cue) { animation: sv-rise .55s cubic-bezier(.2, .7, .2, 1) both; }
.sv-beat.in > :nth-child(2) { animation-delay: .05s; }
.sv-beat.in > :nth-child(3) { animation-delay: .1s; }
@keyframes sv-rise { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: none; } }
.sv-cue { display: inline-flex; align-items: center; gap: 8px; margin-top: 2px; font-size: .86rem; font-weight: 650; color: var(--sv-ink-3); transition: opacity .3s; }
.sv-cue svg { width: 16px; height: 16px; animation: sv-bob 1.8s ease-in-out infinite; }
.sv-cue.gone { opacity: 0; visibility: hidden; }
@keyframes sv-bob { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(4px); } }

/* top-right chips: Parts and the stage colour */
.sv-chips { position: absolute; top: 14px; right: 12px; z-index: 5; display: flex; gap: 8px; align-items: center; }
.sv-chip, .sv-toggle {
  display: inline-flex; align-items: center; border-radius: 999px; background: var(--sv-seg); border: 1px solid var(--sv-line);
  -webkit-backdrop-filter: blur(10px); backdrop-filter: blur(10px); color: var(--sv-ink);
}
.sv-chip {
  gap: 7px; min-height: 40px; padding: 0 14px 0 12px; cursor: pointer; font: inherit; font-size: .84rem; font-weight: 700; white-space: nowrap;
  transition: background-color .2s;
}
.sv-chip svg { width: 18px; height: 18px; flex: none; }
.sv-chip:hover { background: var(--sv-card-active); }
.sv-chip[aria-expanded="true"] { background: var(--sv-seg-on); color: var(--sv-seg-on-ink); }
.sv-chip:focus-visible, .sv-toggle button:focus-visible, .sv-dot:focus-visible, .sv-x:focus-visible { outline: 3px solid var(--sv-accent); outline-offset: 2px; }
.sv-toggle { gap: 2px; padding: 3px; }
.sv-toggle[hidden] { display: none; }
.sv-toggle-lbl { display: none; font-size: .78rem; font-weight: 650; color: var(--sv-ink-3); margin: 0 4px 0 9px; white-space: nowrap; }
.sv-toggle button {
  min-height: 34px; padding: 0 12px; border: 0; border-radius: 999px; background: transparent; cursor: pointer;
  font: inherit; font-size: .82rem; font-weight: 650; color: var(--sv-ink-2); white-space: nowrap;
  transition: background-color .2s, color .2s;
}
.sv-toggle button:hover { color: var(--sv-ink); }
.sv-toggle button[aria-pressed="true"] { background: var(--sv-seg-on); color: var(--sv-seg-on-ink); }

/* progress: one dot per beat on a thin rail at the right edge */
.sv-dots { position: absolute; right: 6px; top: 50%; z-index: 4; transform: translateY(-50%); display: grid; justify-items: center; margin: 0; padding: 0; list-style: none; }
.sv-rail { position: absolute; left: 50%; top: 14px; bottom: 14px; width: 2px; margin-left: -1px; border-radius: 2px; background: var(--sv-line); overflow: hidden; }
.sv-rail i { display: block; width: 100%; height: 100%; background: var(--sv-accent); transform-origin: 50% 0; transform: scaleY(0); }
.sv-dot { position: relative; display: grid; place-items: center; width: 28px; height: 28px; padding: 0; border: 0; background: transparent; cursor: pointer; }
.sv-dot i { display: block; width: 8px; height: 8px; border-radius: 99px; background: var(--sv-ink-3); box-shadow: 0 0 0 3px var(--sv-lo); transition: height .3s, background-color .3s; }
.sv-dot.done i { background: var(--sv-accent); }
.sv-dot[aria-current="step"] i { height: 20px; background: var(--sv-ink); }

/* the active beat's part card: a compact panel that slides in beside the parts in focus */
.sv-bcard {
  position: absolute; z-index: 4; left: 12px; right: 44px; top: 66px; display: flex; gap: 12px; align-items: center;
  padding: 10px 14px 10px 10px; border-radius: 18px; background: var(--sv-panel); border: 1px solid var(--sv-line);
  box-shadow: var(--sv-shadow); -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px);
  opacity: 0; transform: translateY(-14px); pointer-events: none; visibility: hidden;
  transition: opacity .35s ease, transform .45s cubic-bezier(.2, .7, .2, 1), visibility 0s linear .45s;
}
.sv-bcard.on { opacity: 1; transform: none; visibility: visible; pointer-events: auto; transition: opacity .35s ease, transform .45s cubic-bezier(.2, .7, .2, 1); }
.sv-bcard .sv-thumb { width: 52px; height: 52px; }
.sv-bcard-main { display: grid; gap: 2px; min-width: 0; }
.sv-bcard-k { font-size: .66rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; color: var(--sv-ink-3); }
.sv-bcard-t { font-weight: 700; font-size: .98rem; line-height: 1.25; color: var(--sv-ink); }
.sv-bcard-x { display: none; margin: 4px 0 0; font-size: .88rem; line-height: 1.45; color: var(--sv-ink-2); }
.sv-bcard-f { margin: 0; font-size: .8rem; line-height: 1.35; font-weight: 650; color: var(--sv-accent); }
:host([data-tip]) .sv-bcard { opacity: 0; visibility: hidden; }

/* part details: follows the mouse; docked at the top of the stage after a tap */
.sv-tip {
  position: absolute; left: 0; top: 0; z-index: 7; width: max-content; max-width: min(320px, calc(100% - 24px));
  padding: 11px 15px 12px; border-radius: 14px; background: var(--sv-tip-bg); color: var(--sv-tip-ink);
  box-shadow: 0 10px 30px rgba(0, 0, 0, .28); pointer-events: none; transform: translate(-9999px, 0);
  font-size: .88rem; line-height: 1.42;
}
.sv-tip > div { display: grid; gap: 3px; }
.sv-tip b { font-size: 1rem; font-weight: 700; }
.sv-tip .sv-tip-role { color: var(--sv-tip-ink-2); }
.sv-tip .sv-tip-fact { margin-top: 3px; padding-top: 6px; border-top: 1px solid color-mix(in srgb, var(--sv-tip-ink) 14%, transparent); color: var(--sv-tip-ink); font-weight: 600; }
.sv-tip .sv-tip-fact::before { content: "Fact  "; font-size: .7rem; letter-spacing: .1em; text-transform: uppercase; color: var(--sv-tip-accent); font-weight: 750; }
.sv-tip.docked { left: 12px; right: 44px; top: 66px; max-width: 440px; width: auto; transform: none; pointer-events: auto; padding-right: 48px; }
.sv-tip-x {
  display: none; position: absolute; right: 4px; top: 4px; width: 40px; height: 40px; border: 0; border-radius: 50%;
  background: transparent; color: var(--sv-tip-ink-2); font-size: 22px; line-height: 1; cursor: pointer;
}
.sv-tip.docked .sv-tip-x { display: block; }

/* all the part cards: a drawer on wide stages, a sheet from the bottom on phones */
.sv-drawer {
  position: absolute; z-index: 8; left: 0; right: 0; bottom: 0; max-height: 74%; display: flex; flex-direction: column;
  border-radius: 22px 22px 0 0; background: var(--sv-panel); border: 1px solid var(--sv-line); border-bottom: 0;
  box-shadow: var(--sv-shadow); -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px);
  transform: translateY(104%); visibility: hidden;
  transition: transform .45s cubic-bezier(.2, .7, .2, 1), visibility 0s linear .45s;
}
.sv-drawer.open { transform: none; visibility: visible; transition: transform .45s cubic-bezier(.2, .7, .2, 1); }
.sv-drawer-head { flex: none; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 10px 6px 20px; }
.sv-drawer-head h4 { margin: 0; font-family: var(--ev-display-font); font-weight: 600; font-size: 1.25rem; color: var(--sv-ink); }
.sv-x {
  flex: none; display: grid; place-items: center; width: 44px; height: 44px; border: 0; border-radius: 50%; padding: 0;
  background: transparent; color: var(--sv-ink-2); cursor: pointer; font-size: 26px; line-height: 1;
}
.sv-x:hover { background: var(--sv-card-hover); color: var(--sv-ink); }
.sv-cards {
  flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; gap: 6px; margin: 0; padding: 4px 14px 16px; list-style: none;
  overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin;
  padding-bottom: calc(16px + env(safe-area-inset-bottom, 0px));
}
.sv-card {
  flex: none; position: relative; border-radius: 16px; background: var(--sv-card); border: 1px solid var(--sv-line);
  transition: background-color .25s, border-color .25s, box-shadow .25s;
}
.sv-card:hover { background: var(--sv-card-hover); }
.sv-card.on { background: var(--sv-card-active); border-color: color-mix(in srgb, var(--sv-accent) 55%, transparent); box-shadow: 0 6px 22px rgba(0, 0, 0, .14); }
.sv-card-btn {
  display: flex; width: 100%; align-items: center; gap: 12px; padding: 7px 10px; margin: 0; border: 0; border-radius: 16px;
  background: transparent; color: inherit; font: inherit; text-align: left; cursor: pointer;
}
.sv-card-btn:focus-visible { outline: 3px solid var(--sv-accent); outline-offset: -3px; }
.sv-thumb { flex: none; width: 44px; height: 44px; border-radius: 12px; background: var(--sv-thumb); display: grid; place-items: center; overflow: hidden; }
.sv-thumb img { width: 100%; height: 100%; object-fit: contain; display: block; }
.sv-thumb i { width: 12px; height: 12px; border-radius: 50%; background: var(--sv-accent); opacity: .5; }
.sv-card-title { flex: 1 1 auto; min-width: 0; font-weight: 650; font-size: .95rem; line-height: 1.25; color: var(--sv-ink); }
.sv-chev { flex: none; width: 20px; height: 20px; color: var(--sv-ink-3); transition: transform .3s; }
.sv-card.on .sv-chev { transform: rotate(180deg); }
.sv-card-body { display: grid; grid-template-rows: 0fr; transition: grid-template-rows .35s cubic-bezier(.2, .7, .2, 1); }
.sv-card.on .sv-card-body { grid-template-rows: 1fr; }
.sv-card-body > div { overflow: hidden; min-height: 0; }
.sv-card-text { margin: 0; padding: 2px 14px 0 66px; font-size: .88rem; line-height: 1.45; color: var(--sv-ink-2); }
.sv-card-fact { margin: 6px 0 0; padding: 0 14px 12px 66px; font-size: .8rem; line-height: 1.35; font-weight: 650; color: var(--sv-accent); }

.sv-loading {
  position: absolute; left: 50%; top: 50%; z-index: 5; transform: translate(-50%, -50%);
  display: grid; gap: 8px; justify-items: center; padding: 10px 16px; border-radius: 14px;
  background: var(--sv-seg); border: 1px solid var(--sv-line); color: var(--sv-ink-2); font-size: .85rem; text-align: center;
  -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px); max-width: calc(100% - 32px);
}
.sv-loading[hidden] { display: none; }
.ev-bar { width: 180px; max-width: 100%; height: 6px; border-radius: 999px; background: var(--sv-line); overflow: hidden; }
.ev-bar i { display: block; height: 100%; width: 0; background: var(--sv-accent); border-radius: 999px; transition: width .2s; }
.ev-error { color: var(--sv-accent); font-weight: 650; }
.ev-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }

/* tablets and up */
@container (min-width: 600px) {
  .sv-chips { top: 18px; right: 18px; }
  .sv-toggle-lbl { display: inline; }
  .sv-beat { left: var(--ev-gutter); right: 72px; bottom: calc(28px + env(safe-area-inset-bottom, 0px)); gap: 10px; }
  .sv-beat h3 { font-size: clamp(2.4rem, 6cqi, 3.4rem); }
  .sv-beat p.sv-text { font-size: 1.08rem; }
  .sv-dots { right: 14px; }
  .sv-bcard { left: var(--ev-gutter); right: auto; top: 76px; width: min(400px, calc(100% - 120px)); }
  .sv-tip.docked { left: var(--ev-gutter); right: auto; top: 76px; width: min(420px, calc(100% - 120px)); }
}
/* wide: caption bottom-left, the card beside the parts in focus, a drawer on the right */
@container (min-width: 900px) {
  .sv-wash { background: radial-gradient(70% 62% at 0% 100%, var(--sv-scrim) 0%, transparent 72%); }
  .sv-beat { right: auto; width: min(32%, 32rem); bottom: 48px; }
  .sv-beat h3 { font-size: clamp(2.8rem, 4.6cqi, 4.6rem); }
  .sv-beat p.sv-text { font-size: clamp(1.05rem, 1.25cqi, 1.3rem); max-width: 30rem; }
  .sv-chips { top: 24px; right: 24px; }
  .sv-dots { right: 20px; }
  /* the left column holds the words (card on top, caption below); the model fills the rest */
  .sv-bcard { top: 88px; width: min(340px, calc(32% - 8px)); flex-direction: column; align-items: flex-start; padding: 16px 18px 18px;
    transform: translateX(-28px); }
  .sv-bcard.on { transform: none; }
  .sv-bcard .sv-thumb { width: 64px; height: 64px; border-radius: 14px; }
  .sv-bcard-t { font-size: 1.12rem; }
  .sv-tip.docked { top: 84px; }
  .sv-drawer {
    left: auto; right: 16px; top: 76px; bottom: 16px; width: min(var(--ev-panel-width), calc(100% - 32px)); max-height: none;
    border-radius: 22px; border-bottom: 1px solid var(--sv-line); transform: translateX(calc(100% + 24px));
  }
}
@container (min-width: 1500px) {
  .sv-beat { bottom: 64px; }
  .sv-bcard { top: 104px; width: 380px; }
  .sv-dots { right: 28px; }
}

/* reduced motion: no scrub. One full screen with a still, exploded model and the cards. */
:host([data-reduced]) .sv { height: auto; }
:host([data-reduced]) .sv-sticky { position: relative; top: 0; height: max(600px, 100vh); height: max(600px, 100svh); clip-path: none; }
:host([data-reduced]) .sv-cue, :host([data-reduced]) .sv-dots, :host([data-reduced]) .sv-layer { display: none; }
@media (prefers-reduced-motion: reduce) {
  .sv-beat.in > :not(.sv-cue), .sv-cue svg { animation: none; }
  .sv-card, .sv-card-body, .sv-chev, .sv-poster, .sv-toggle button, .sv-bcard, .sv-bcard.on, .sv-drawer, .sv-drawer.open, .sv-dot i { transition: none; }
}
`;

/* ------------------------------------------------------------------------------------------------
 * Small helpers
 * ---------------------------------------------------------------------------------------------- */
const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const easeOut = (t) => 1 - Math.pow(1 - t, 3);
/** Soft landing: quick fall that slows right down for the last few millimetres. Never overshoots,
 *  so a part never sinks into the one below it. */
const softLand = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : 1 - Math.pow(1 - t, 4));
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** Glob match for ids: '*' = any run of characters, '?' = one. Case-sensitive. */
const globCache = new Map();
function globRe(p) {
  if (!globCache.has(p)) {
    const re = '^' + p.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*').replace(/\?/g, '.') + '$';
    globCache.set(p, new RegExp(re));
  }
  return globCache.get(p);
}
const matches = (id, pattern) => (pattern.includes('*') || pattern.includes('?') ? globRe(pattern).test(id) : id === pattern);

/** "Thigh_FrontLeft_Outer_v3_4" -> "Thigh front left outer" (fallback name only). */
function prettyId(id) {
  const s = id.replace(/_v\d+(_\d+)*[a-z]?$/i, '').replace(/[-_]+/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').trim();
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
  return r.json();
}

const Y_AXIS = new THREE.Vector3(0, 1, 0);
const ICONS = {
  chev: '<svg class="sv-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>',
  down: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6"/></svg>',
  prev: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>',
  next: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5.5v13a1 1 0 0 0 1.5.86l10.5-6.5a1 1 0 0 0 0-1.72L9.5 4.64A1 1 0 0 0 8 5.5z"/></svg>',
  pause: '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>',
  parts: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="4" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.6"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.6"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.6"/></svg>',
};

/* ------------------------------------------------------------------------------------------------
 * Manifest: load, merge the human-written content with the machine-written geometry, resolve refs.
 * See README.md for the schema. The result is a plain object the element renders from.
 * ---------------------------------------------------------------------------------------------- */
export async function loadManifest(src) {
  const base = new URL(src, document.baseURI).href;
  const content = await fetchJSON(base);
  let geometry = null, geoBase = base;
  if (typeof content.geometry === 'string') {
    geoBase = new URL(content.geometry, base).href;
    geometry = await fetchJSON(geoBase);
  } else if (content.geometry && typeof content.geometry === 'object') {
    geometry = content.geometry;
  }
  return resolveManifest(content, geometry, base, geoBase);
}

export function resolveManifest(content, geometry, base = document.baseURI, geoBase = base) {
  const warnings = [];
  // 1. the list of geometric parts: geometry file first, else an array in content.parts
  const geoParts = geometry?.parts || (Array.isArray(content.parts) ? content.parts : []);
  const overrides = Array.isArray(content.parts) ? {} : (content.parts || {});
  const groups = content.groups || [];
  const hide = content.hide || [];
  const defaults = content.defaults || {};

  const parts = [];
  for (const g of geoParts) {
    if (!g || !g.id) continue;
    const p = {
      id: g.id,
      model: g.model ? new URL(g.model, geoBase).href : null,
      node: g.node || null,
      matrix: g.matrix || null,
      bbox: g.bbox || null,
      placeholder: g.placeholder || null,
      cadColour: g.colour || g.cadColour || null,
      vertexColours: !!g.vertexColours,
    };
    // group: first group whose "match" list matches; an explicit "group" in an override wins
    let group = null;
    for (const gr of groups) {
      if ((gr.match || []).some((m) => matches(p.id, m))) { group = gr; break; }
    }
    // overrides: wildcard keys first (in file order), then the exact id last
    const keys = Object.keys(overrides);
    const ov = {};
    for (const k of keys) if (k !== p.id && matches(p.id, k)) Object.assign(ov, overrides[k]);
    if (overrides[p.id]) Object.assign(ov, overrides[p.id]);
    if (ov.group) group = groups.find((gr) => gr.id === ov.group) || group;
    const pick = (key) => (ov[key] !== undefined ? ov[key] : group?.[key] !== undefined ? group[key] : defaults[key]);
    p.group = group?.id || null;
    p.groupName = group?.name || null;
    p.name = ov.name || (group?.partName ? group.partName.replace('{id}', prettyId(p.id)) : null) || prettyId(p.id);
    p.role = pick('role') || '';
    p.fact = pick('fact') || '';          // 1.2.0: one short, true fact, shown in the scroll mode's part details
    p.colour = pick('colour') ?? pick('color') ?? (p.vertexColours ? 'model' : p.cadColour) ?? '#d9cbb8';
    p.roughness = pick('roughness') ?? 0.62;
    p.metalness = pick('metalness') ?? 0.0;
    p.opacity = pick('opacity') ?? 1;
    p.explode = Object.assign({}, defaults.explode || {}, group?.explode || {}, ov.explode || {});
    p.order = ov.order ?? null;
    p.hidden = !!(ov.hidden ?? group?.hidden) || hide.some((h) => matches(p.id, h));
    parts.push(p);
  }
  const byId = new Map(parts.map((p) => [p.id, p]));

  // 2. references: "Exact_Id", "Glob*", or "group:<id>"; hidden parts are never returned
  const resolveRefs = (refs, where) => {
    const out = [];
    for (const r of [].concat(refs || [])) {
      if (typeof r !== 'string') continue;
      let found;
      if (r.startsWith('group:')) found = parts.filter((p) => p.group === r.slice(6));
      else found = parts.filter((p) => matches(p.id, r));
      found = found.filter((p) => !p.hidden);
      if (!found.length) warnings.push(`${where}: "${r}" matches no visible part`);
      for (const p of found) if (!out.includes(p.id)) out.push(p.id);
    }
    return out;
  };

  // 3. build steps; the step index becomes each part's assembly order unless the part sets "order"
  const build = (content.build || []).map((s, i) => ({
    title: s.title || `Step ${i + 1}`,
    caption: s.caption || '',
    camera: s.camera || null,
    parts: resolveRefs(s.parts, `build step ${i + 1}`),
  }));
  build.forEach((s, i) => s.parts.forEach((id) => {
    const p = byId.get(id);
    if (p && p.buildStep === undefined) p.buildStep = i;
  }));
  const visible = parts.filter((p) => !p.hidden);
  const unplaced = visible.filter((p) => p.buildStep === undefined);
  if (build.length && unplaced.length) {
    warnings.push(`${unplaced.length} visible part(s) are in no build step; they arrive with the last step: ` +
      unplaced.slice(0, 6).map((p) => p.id).join(', ') + (unplaced.length > 6 ? ' ...' : ''));
    unplaced.forEach((p) => { p.buildStep = build.length - 1; });
  }
  for (const p of parts) if (p.order === null || p.order === undefined) p.order = p.buildStep ?? 0;

  // 4. energy stages
  const E = content.energy || {};
  const points = E.points || {};
  const resolvePath = (path, where) => {
    const lines = Array.isArray(path) && path.length && Array.isArray(path[0]) ? path : (path ? [path] : []);
    return lines.map((line) => line.map((ref) => {
      if (typeof ref === 'string' && ref.startsWith('@')) {
        const pt = points[ref.slice(1)];
        if (!pt) { warnings.push(`${where}: no energy point "${ref}"`); return null; }
        return { point: pt.at, label: pt.label || ref.slice(1) };
      }
      const ids = resolveRefs(ref, where);
      return ids.length ? { parts: ids } : null;
    }).filter(Boolean)).filter((l) => l.length >= 2);
  };
  const stages = (E.stages || []).map((s, i) => ({
    title: s.title || `Stage ${i + 1}`,
    text: s.text || '',
    badge: s.badge || '',
    camera: s.camera || null,
    lift: s.lift || null,
    parts: resolveRefs(s.parts, `energy stage ${i + 1}`),
    path: resolvePath(s.path, `energy stage ${i + 1} path`),
    labels: s.labels !== false,
  }));

  // 5. scroll story (1.2.0): layers (the order he comes apart), beats (captions), cards (main parts)
  const SC = content.scroll || null;
  let scroll = null;
  if (SC) {
    const range = (v, d) => (Array.isArray(v) && v.length === 2 && v[0] < v[1] ? [clamp(+v[0]), clamp(+v[1])] : d);
    const layers = (SC.layers || []).map((l, i) => ({
      title: l.title || `Layer ${i + 1}`,
      parts: resolveRefs(l.parts, `scroll layer ${i + 1}`),
      carry: l.carry && Array.isArray(l.carry.by) ? { parts: resolveRefs(l.carry.parts, `scroll layer ${i + 1} carry`), by: l.carry.by.map(Number) } : null,
    }));
    const cards = (SC.cards || []).map((c, i) => ({
      id: String(c.id || `card-${i + 1}`).replace(/[^\w-]/g, '-'),
      title: c.title || `Part ${i + 1}`,
      text: c.text || '',
      fact: c.fact || '',
      camera: c.camera || null,
      parts: resolveRefs(c.parts, `scroll card "${c.title || i + 1}"`),
    }));
    const beats = (SC.beats || []).map((b, i) => ({
      at: clamp(+b.at || 0),
      title: b.title || '',
      text: b.text || '',
      card: b.card ? String(b.card) : null,
      camera: b.camera || null,
      focusMin: b.focusMin != null ? clamp(+b.focusMin, 0.15, 1) : null,   // 1.3.0: this beat may zoom closer (small parts)
      parts: b.parts ? resolveRefs(b.parts, `scroll beat "${b.title || i + 1}"`) : null,
    })).sort((a, b) => a.at - b.at);
    for (const b of beats) {
      if (b.card && !cards.some((c) => c.id === b.card)) warnings.push(`scroll beat "${b.title}": no card "${b.card}"`);
    }
    scroll = {
      kicker: SC.kicker || '',
      explodeAt: range(SC.explodeAt, [0.05, 0.32]),
      assembleAt: range(SC.assembleAt, [0.78, 0.95]),
      sweep: Array.isArray(SC.sweep) && SC.sweep.length === 2 ? SC.sweep.map(Number) : [-16, 18],
      dim: clamp(SC.dim ?? 0.16, 0.02, 1),
      beatDim: clamp(SC.beatDim ?? 0.3, 0.02, 1),
      overlap: clamp(SC.overlap ?? 0.35, 0, 0.9),
      layers, cards, beats,
      static: SC.static || null,
      // 1.3.0
      apartLabel: SC.apartLabel || 'Taking apart',
      togetherLabel: SC.togetherLabel || 'Back together',
      focusMin: clamp(SC.focusMin ?? 0.55, 0.2, 1),
    };
    if (scroll.explodeAt[1] > scroll.assembleAt[0]) warnings.push('scroll: explodeAt must end before assembleAt starts');
  }

  return {
    schema: content.schema || 'exploded-view/manifest@1',
    title: content.title || '',
    subtitle: content.subtitle || '',
    units: geometry?.units || content.units || 'mm',
    upAxis: (geometry?.upAxis || content.upAxis || 'y').toLowerCase(),
    draco: content.draco || null,
    parts,
    byId,
    groups,
    cameras: content.cameras || [],
    defaultCamera: content.defaultCamera || (content.cameras?.[0]?.id ?? null),
    labels: Object.assign({ assembled: 'Assembled', exploded: 'Exploded' }, content.labels || {}),
    explodeHint: content.explodeHint || 'Drag to spin. Pinch or scroll to zoom. Tap a part to see what it does.',
    explodeStagger: content.explodeStagger ?? 0.55,
    build,
    energy: { intro: E.intro || '', stages, liftDistance: E.liftDistance ?? null, liftDir: E.liftDir || [0, 1, 0], ghostOpacity: E.ghostOpacity ?? 0.07 },
    scroll,
    geometryInfo: geometry ? { generator: geometry.generator, generated: geometry.generated, source: geometry.source } : null,
    warnings,
  };
}

/* ------------------------------------------------------------------------------------------------
 * The element
 * ---------------------------------------------------------------------------------------------- */
export class ExplodedView extends HTMLElement {
  static get observedAttributes() { return ['src', 'mode', 'step']; }

  constructor() {
    super();
    this._uid = Math.random().toString(36).slice(2, 8);
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.innerHTML = `<style>${CSS}</style>${this._template()}`;
    this.$ = (s) => this.shadowRoot.querySelector(s);
    this._mode = 'explode';
    this._explode = 0;            // 0..1 target from the slider
    this._explodeShown = 0;       // eased value actually shown
    this._step = 0; this._buildT = 0; this._buildTarget = 1; this._buildSpeed = 1.2;
    this._stage = 0;
    this._playing = false;
    this._hover = null; this._selected = null;
    this._needs = true;
    this._visible = true;
    this._clock = new THREE.Clock();
    this._reduced = window.matchMedia('(prefers-reduced-motion: reduce)');
    this._onReduced = () => { this._needs = true; };
    this._reduced.addEventListener?.('change', this._onReduced);
  }

  _template() {
    const u = this._uid;
    const tab = (m) => `<button class="ev-tab" role="tab" id="tab-${m}-${u}" data-mode="${m}" aria-controls="pane-${m}-${u}" aria-selected="false" tabindex="-1"><span class="short">${MODE_LABELS[m][0]}</span><span class="long">${MODE_LABELS[m][1]}</span></button>`;
    return `
<div class="ev" part="root">
  <div class="ev-head" part="header">
    <div class="ev-titles"><p class="ev-title" id="title"></p><p class="ev-sub" id="sub"></p></div>
    <div class="ev-tabs" role="tablist" aria-label="View mode">${MODES.map(tab).join('')}</div>
  </div>
  <div class="ev-body">
    <div class="ev-stage" part="stage">
      <canvas aria-label="Interactive 3D model. Drag to rotate, pinch or scroll to zoom." role="img" tabindex="0"></canvas>
      <div class="ev-tip" id="tip"></div>
      <div id="labels"></div>
      <div class="ev-card" id="card" hidden role="status">
        <div class="ev-card-text" id="cardText"></div>
        <button class="ev-x" id="cardX" aria-label="Close part details">&times;</button>
      </div>
      <div class="ev-chips" id="chips" role="group" aria-label="Camera views"></div>
      <div class="ev-loading" id="loading"><div id="loadMsg">Loading the model…</div><div class="ev-bar"><i id="bar"></i></div></div>
    </div>
    <div class="ev-panel" part="panel">
      <section class="ev-pane" id="pane-explode-${u}" data-pane="explode" role="tabpanel" aria-labelledby="tab-explode-${u}">
        <p class="ev-kicker">Explode</p>
        <div class="ev-slider">
          <label class="ev-sr" for="explodeRange-${u}">Explode amount</label>
          <input class="ev-range" id="explodeRange-${u}" data-r="explode" type="range" min="0" max="100" step="1" value="0">
          <div class="ev-slider-labels"><span id="lblA">Assembled</span><span class="ev-count" id="explodeVal" aria-hidden="true">0%</span><span id="lblB">Exploded</span></div>
        </div>
        <div class="ev-row">
          <button class="ev-btn grow" data-act="assemble">Put together</button>
          <button class="ev-btn grow primary" data-act="explode">Take apart</button>
        </div>
        <p class="ev-hint" id="explodeHint"></p>
      </section>
      <section class="ev-pane" id="pane-build-${u}" data-pane="build" role="tabpanel" aria-labelledby="tab-build-${u}" hidden>
        <p class="ev-kicker">Step <span class="ev-count" id="buildNum">1</span> of <span id="buildTotal">1</span></p>
        <div aria-live="polite"><h3 class="ev-h" id="buildTitle"></h3><p class="ev-p" id="buildCaption" style="margin-top:6px"></p></div>
        <div class="ev-slider">
          <label class="ev-sr" for="buildRange-${u}">Build step</label>
          <input class="ev-range" id="buildRange-${u}" data-r="build" type="range" min="1" max="1" step="1" value="1">
        </div>
        <div class="ev-row">
          <button class="ev-btn" data-act="buildPrev" aria-label="Previous step">${ICONS.prev}</button>
          <button class="ev-btn grow" data-act="buildPlay" id="playBtn" aria-label="Play all steps">${ICONS.play}<span>Play</span></button>
          <button class="ev-btn primary grow" data-act="buildNext">Next ${ICONS.next}</button>
        </div>
      </section>
      <section class="ev-pane" id="pane-energy-${u}" data-pane="energy" role="tabpanel" aria-labelledby="tab-energy-${u}" hidden>
        <p class="ev-kicker">Stage <span class="ev-count" id="energyNum">1</span> of <span id="energyTotal">1</span></p>
        <div aria-live="polite"><h3 class="ev-h" id="energyTitle"></h3><p class="ev-p" id="energyText" style="margin-top:6px"></p></div>
        <span class="ev-badge" id="energyBadge" hidden></span>
        <div class="ev-slider">
          <label class="ev-sr" for="energyRange-${u}">Energy stage</label>
          <input class="ev-range" id="energyRange-${u}" data-r="energy" type="range" min="1" max="1" step="1" value="1">
        </div>
        <div class="ev-row">
          <button class="ev-btn" data-act="energyPrev" aria-label="Previous stage">${ICONS.prev}</button>
          <button class="ev-btn primary grow" data-act="energyNext">Next ${ICONS.next}</button>
        </div>
        <div class="ev-steps" id="energyDots" role="group" aria-label="Jump to stage"></div>
      </section>
    </div>
  </div>
</div>`;
  }

  /* ---------- public API ---------- */
  get mode() { return this._mode; }
  set mode(m) { this.setMode(m); }
  setMode(m) {
    if (this._scrollMode) return;
    if (!MODES.includes(m) || !this._availableModes().includes(m)) return;
    const changed = m !== this._mode;
    this._mode = m;
    this.shadowRoot.querySelectorAll('.ev-tab').forEach((t) => {
      const on = t.dataset.mode === m;
      t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1;
    });
    this.shadowRoot.querySelectorAll('.ev-pane').forEach((p) => { p.hidden = p.dataset.pane !== m; });
    this._stopPlay();
    this._clearSelection();
    if (this._m) {
      if (m === 'build') this.goToStep(this._step, !changed);
      if (m === 'energy') this.goToStage(this._stage, !changed);
    }
    this._needs = true;
    if (changed) this._emit('modechange', { mode: m });
  }
  setExplode(v) {
    if (this._scrollMode) return;
    this._explode = clamp(v / 100);
    const r = this._range('explode');
    if (r) { r.value = Math.round(this._explode * 100); this._fill(r); }
    this.$('#explodeVal').textContent = `${Math.round(this._explode * 100)}%`;
    if (this._reducedMotion()) this._explodeShown = this._explode;
    this._needs = true;
  }
  goToStep(i, instant = false) {
    if (this._scrollMode || !this._m || !this._m.build.length) return;
    const n = this._m.build.length;
    i = Math.max(0, Math.min(n - 1, i | 0));
    const jump = Math.abs(i + 1 - this._buildT);
    this._step = i; this._buildTarget = i + 1;
    if (instant || this._reducedMotion()) this._buildT = this._buildTarget;
    this._buildSpeed = Math.max(0.9, jump / 1.4);        // a long scrub still finishes in about 1.4 s
    const s = this._m.build[i];
    this.$('#buildNum').textContent = i + 1;
    this.$('#buildTitle').textContent = s.title;
    this.$('#buildCaption').textContent = s.caption;
    const r = this._range('build'); r.value = i + 1; this._fill(r);
    this.shadowRoot.querySelector('[data-act="buildPrev"]').disabled = i === 0;
    this.shadowRoot.querySelector('[data-act="buildNext"]').disabled = i === n - 1;
    if (s.camera) this._applyCamera(s.camera, !instant);
    this._needs = true;
    this._emit('stepchange', { index: i, title: s.title });
  }
  goToStage(i, instant = false) {
    if (this._scrollMode || !this._m || !this._m.energy.stages.length) return;
    const st = this._m.energy.stages;
    i = Math.max(0, Math.min(st.length - 1, i | 0));
    this._stage = i;
    const s = st[i];
    this.$('#energyNum').textContent = i + 1;
    this.$('#energyTitle').textContent = s.title;
    this.$('#energyText').textContent = s.text;
    const b = this.$('#energyBadge'); b.hidden = !s.badge; b.textContent = s.badge;
    const r = this._range('energy'); r.value = i + 1; this._fill(r);
    this.shadowRoot.querySelector('[data-act="energyPrev"]').disabled = i === 0;
    this.shadowRoot.querySelector('[data-act="energyNext"]').disabled = i === st.length - 1;
    this.shadowRoot.querySelectorAll('.ev-dot').forEach((d, k) => {
      d.classList.toggle('done', k < i);
      if (k === i) d.setAttribute('aria-current', 'step'); else d.removeAttribute('aria-current');
    });
    this._energyStart = this._clock.getElapsedTime();
    if (instant || this._reducedMotion()) this._parts?.forEach((p) => { p.lift = this._liftTarget(p); p.ghost = this._ghostTarget(p); });
    if (s.camera) this._applyCamera(s.camera, !instant);
    this._needs = true;
    this._emit('stagechange', { index: i, title: s.title });
  }
  setCamera(id) { this._applyCamera(id, true); }

  /* ---------- lifecycle ---------- */
  connectedCallback() {
    if (this._started) return;
    this._started = true;
    // 1.2.0: mode="scroll" is fixed when the element first connects; it swaps in its own template.
    if (!this._scrollMode && this.getAttribute('mode') === 'scroll') {
      this._scrollMode = true;
      this.shadowRoot.innerHTML = `<style>${SCROLL_CSS}</style>${this._scrollTemplate()}`;
    }
    if (!this._wired) { if (this._scrollMode) this._wireScrollUI(); else this._wireUI(); this._wired = true; }
    if (this._scrollMode) this._attachScroll();
    const src = this.getAttribute('src');
    // 1.2.0: lazy = wait until the element is near the viewport before the WebGL context, manifest and models
    if (src && this.hasAttribute('lazy') && !this._m && 'IntersectionObserver' in window) {
      this._lazyIO?.disconnect();
      this._lazyIO = new IntersectionObserver((es) => {
        if (!es.some((e) => e.isIntersecting)) return;
        this._lazyIO.disconnect(); this._lazyIO = null;
        const s = this.getAttribute('src'); if (s) this._load(s);
      }, { rootMargin: '60% 0px 60% 0px' });
      this._lazyIO.observe(this);
    } else if (src) this._load(src);
    if (this.hasAttribute('link-hash') && !this._onHash) {   // 1.1.0: #build=N / #energy=N deep links (opt-in)
      this._onHash = () => this._applyDeepLink();
      window.addEventListener('hashchange', this._onHash);
    }
  }
  disconnectedCallback() {
    this._started = false;
    this._loadToken = null;
    cancelAnimationFrame(this._raf);
    this._ro?.disconnect(); this._io?.disconnect();
    this._lazyIO?.disconnect(); this._lazyIO = null;
    this._detachScroll?.();
    document.removeEventListener('visibilitychange', this._onVis);
    if (this._onHash) { window.removeEventListener('hashchange', this._onHash); this._onHash = null; }
    this._stopPlay();
    this._disposeScene();
  }
  attributeChangedCallback(name, oldV, v) {
    if (!this._started || oldV === v) return;
    if (name === 'src' && v) this._load(v);
    if (this._scrollMode && name !== 'src') return;
    if (name === 'mode' && v) this.setMode(v);
    if (name === 'step' && v) this._applyDeepLink();
  }

  /* ---------- deep links (1.1.0) ----------
   * step="N" (1-based, as the panel shows it) opens Build mode at step N.
   * With the link-hash attribute, the page URL #build=N or #energy=N does the same, also on hashchange.
   * The steps before N are shown already built and step N plays its own drop. Without either, nothing changes. */
  _deepLink() {
    if (!this._m) return null;
    let mode = null, n = NaN;
    const h = this.hasAttribute('link-hash') && /^#(build|energy)=(\d+)$/.exec(window.location.hash || '');
    if (h) { mode = h[1]; n = +h[2]; this._fromHash = true; }
    else if (this.hasAttribute('step')) { mode = 'build'; n = +this.getAttribute('step'); }
    if (!mode || !(n >= 1) || !this._availableModes().includes(mode)) return null;
    const len = mode === 'build' ? this._m.build.length : this._m.energy.stages.length;
    return { mode, i: Math.min(len, n) - 1 };
  }
  _applyDeepLink() {
    if (!this._ready) return false;
    const d = this._deepLink();
    if (!d) return false;
    if (this._fromHash) { this._fromHash = false; this.scrollIntoView({ block: 'start', behavior: this._reducedMotion() ? 'auto' : 'smooth' }); }
    if (d.mode === 'build') {
      this._step = d.i;
      this.setMode('build');
      this._buildT = d.i;                 // everything before step N is in place...
      this.goToStep(d.i);                 // ...and step N drops in
    } else {
      this._stage = d.i;
      this.setMode('energy');
      this.goToStage(d.i);
    }
    return true;
  }

  _emit(type, detail) { this.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true })); }
  _reducedMotion() { return this._reduced.matches || this.hasAttribute('reduced-motion'); }
  _range(k) { return this.shadowRoot.querySelector(`[data-r="${k}"]`); }
  _fill(r) {
    const min = +r.min, max = +r.max;
    r.style.setProperty('--p', `${max > min ? ((r.value - min) / (max - min)) * 100 : 0}%`);
  }
  _availableModes() {
    const want = (this.getAttribute('modes') || MODES.join(',')).split(',').map((s) => s.trim());
    if (!this._m) return want;
    return want.filter((m) => m === 'explode' || (m === 'build' && this._m.build.length) ||
      (m === 'energy' && this._m.energy.stages.length));
  }

  /* ---------- UI wiring ---------- */
  _wireUI() {
    const root = this.shadowRoot;
    root.querySelectorAll('.ev-tab').forEach((t) => t.addEventListener('click', () => this.setMode(t.dataset.mode)));
    root.querySelector('.ev-tabs').addEventListener('keydown', (e) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return;
      const tabs = [...root.querySelectorAll('.ev-tab')].filter((t) => !t.hidden);
      let i = tabs.findIndex((t) => t.dataset.mode === this._mode);
      i = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : -1) + tabs.length) % tabs.length;
      this.setMode(tabs[i].dataset.mode); tabs[i].focus(); e.preventDefault();
    });
    this._range('explode').addEventListener('input', (e) => this.setExplode(+e.target.value));
    this._range('build').addEventListener('input', (e) => { this._stopPlay(); this.goToStep(+e.target.value - 1); });
    this._range('energy').addEventListener('input', (e) => this.goToStage(+e.target.value - 1));
    root.querySelectorAll('[data-act]').forEach((b) => b.addEventListener('click', () => this._act(b.dataset.act)));
    this.$('#cardX').addEventListener('click', () => this._clearSelection());
    this.addEventListener('keydown', (e) => { if (e.key === 'Escape') this._clearSelection(); });
  }

  _act(a) {
    switch (a) {
      case 'assemble': return this._animateExplodeTo(0);
      case 'explode': return this._animateExplodeTo(100);
      case 'buildPrev': this._stopPlay(); return this.goToStep(this._step - 1);
      case 'buildNext': this._stopPlay(); return this.goToStep(this._step + 1);
      case 'buildPlay': return this._playing ? this._stopPlay() : this._startPlay();
      case 'energyPrev': return this.goToStage(this._stage - 1);
      case 'energyNext': return this.goToStage(this._stage + 1);
    }
  }
  _animateExplodeTo(v) {
    // the slider value jumps; the shown value eases toward it in the render loop
    this.setExplode(v);
  }
  _startPlay() {
    if (!this._m?.build.length) return;
    if (this._step >= this._m.build.length - 1) this.goToStep(0);
    this._playing = true; this._setPlayIcon();
    const tick = () => {
      if (!this._playing) return;
      if (this._step >= this._m.build.length - 1) { this._stopPlay(); return; }
      this.goToStep(this._step + 1);
      this._playTimer = setTimeout(tick, this._reducedMotion() ? 3200 : 2400);
    };
    this._playTimer = setTimeout(tick, this._reducedMotion() ? 1800 : 1200);
  }
  _stopPlay() {
    clearTimeout(this._playTimer);
    if (this._playing) { this._playing = false; this._setPlayIcon(); }
  }
  _setPlayIcon() {
    const b = this.$('#playBtn');
    b.innerHTML = this._playing ? `${ICONS.pause}<span>Pause</span>` : `${ICONS.play}<span>Play</span>`;
    b.setAttribute('aria-label', this._playing ? 'Pause' : 'Play all steps');
  }

  /* ---------- loading ---------- */
  async _load(src) {
    const token = {}; this._loadToken = token;
    const loading = this.$('#loading'), bar = this.$('#bar'), msg = this.$('#loadMsg');
    loading.hidden = false; bar.style.width = '0%'; msg.textContent = 'Loading the model…';
    try {
      const m = await loadManifest(src);
      if (this._loadToken !== token) return;
      m.warnings.forEach((w) => console.warn('[exploded-view]', w));
      this._m = m;
      if (this._scrollMode) {
        if (!m.scroll) throw new Error('mode="scroll" needs a "scroll" block in the manifest');
        this._buildScrollCards();
        this._initThree();
        this._ready = false;
        this._clearParts();
        await this._loadParts(m, (done, total) => {
          if (this._loadToken === token) { bar.style.width = `${Math.round((done / total) * 100)}%`; msg.textContent = `Loading parts… ${done} of ${total}`; }
        }, token);
        if (this._loadToken !== token) return;
        this._prepare();
        this._prepareScroll();
        this._makeThumbs();
        this._ready = true;
        loading.hidden = true;
        if (this._reducedMotion() && (this._stageW || 0) >= 900) this._setDrawer(true);   // still view: the cards stay open beside it
        this.$('.sv-poster').classList.add('gone');
        this._scrollDirty = true; this._sp = null; this._needs = true;
        this._loop();
        this._emit('ready', { parts: this._parts.length, warnings: m.warnings });
        return;
      }
      this.$('#title').textContent = m.title;
      this.$('#sub').textContent = m.subtitle;
      this.$('#sub').hidden = !m.subtitle;
      this.$('#lblA').textContent = m.labels.assembled;
      this.$('#lblB').textContent = m.labels.exploded;
      this.$('#explodeHint').textContent = m.explodeHint;
      const avail = this._availableModes();
      this.shadowRoot.querySelectorAll('.ev-tab').forEach((t) => { t.hidden = !avail.includes(t.dataset.mode); });
      this.shadowRoot.querySelector('.ev-tabs').hidden = avail.length < 2;
      this._initThree();
      this._ready = false;
      this._clearParts();
      await this._loadParts(m, (done, total) => {
        if (this._loadToken === token) { bar.style.width = `${Math.round((done / total) * 100)}%`; msg.textContent = `Loading parts… ${done} of ${total}`; }
      }, token);
      if (this._loadToken !== token) return;
      this._prepare();
      this._ready = true;
      this._buildUIForManifest();
      loading.hidden = true;
      const start = this.getAttribute('mode');
      this._mode = null;
      this.setMode(avail.includes(start) ? start : avail[0]);
      this._applyCamera(m.defaultCamera, false);
      this._applyDeepLink();
      this._loop();
      this._emit('ready', { parts: this._parts.length, warnings: m.warnings });
    } catch (err) {
      if (this._loadToken !== token) return;
      console.warn('[exploded-view] could not load', src, err);
      msg.innerHTML = `<span class="ev-error">Sorry, the 3D model could not be loaded.</span><br><small>${esc(err.message || err)}</small>`;
      bar.parentElement.hidden = true;
    }
  }

  _initThree() {
    if (this._renderer) return;
    const canvas = this.shadowRoot.querySelector('canvas');
    const r = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'high-performance' });
    r.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    r.outputColorSpace = THREE.SRGBColorSpace;
    r.toneMapping = THREE.NoToneMapping;
    this._renderer = r;
    this._scene = new THREE.Scene();
    const pm = new THREE.PMREMGenerator(r);
    this._envTex = pm.fromScene(new RoomEnvironment(r), 0.04).texture;
    pm.dispose();
    this._scene.environment = this._envTex;
    this._scene.add(new THREE.HemisphereLight(0xfff4e6, 0xc9a98a, 0.55));
    const key = new THREE.DirectionalLight(0xfff1de, 1.05);
    key.position.set(0.6, 1.4, 1.0);
    this._scene.add(key);
    const rim = new THREE.DirectionalLight(0xffe2c4, 0.35);
    rim.position.set(-1, 0.4, -1.2);
    this._scene.add(rim);
    this._camera = new THREE.PerspectiveCamera(32, 1, 0.1, 10000);
    this._controls = new OrbitControls(this._camera, canvas);
    this._controls.enableDamping = true;
    this._controls.dampingFactor = 0.09;
    this._controls.rotateSpeed = 0.8;
    this._controls.zoomSpeed = 0.9;
    this._controls.screenSpacePanning = true;
    this._controls.addEventListener('change', () => { this._needs = true; });
    this._controls.addEventListener('start', () => { this._camAnim = null; this._markChip(null); this._userOrbit = true; });
    this._controls.addEventListener('end', () => { this._userOrbit = false; });
    this._raycaster = new THREE.Raycaster();
    this._pointer = new THREE.Vector2();
    this._model = new THREE.Group();
    this._scene.add(this._model);
    if (this._scrollMode) {
      // the page scroll drives the camera: no orbit, no wheel zoom, and touch must scroll the page
      this._controls.enabled = false;
      canvas.style.touchAction = 'pan-y';
      this._wireScrollPointer(canvas);
    } else this._wirePointer(canvas);
    const stage = this._stageEl();
    this._ro = new ResizeObserver(() => this._resize());
    this._ro.observe(stage);
    this._io = new IntersectionObserver((es) => { this._visible = es.some((e) => e.isIntersecting); if (this._visible) this._loop(); });
    this._io.observe(this);
    this._onVis = () => { if (!document.hidden) this._loop(); };
    document.addEventListener('visibilitychange', this._onVis);
    this._resize();
    this._makePathObjects();
  }

  _stageEl() { return this.shadowRoot.querySelector('.ev-stage, .sv-stage'); }
  _resize() {
    if (!this._renderer) return;
    const stage = this._stageEl();
    const w = Math.max(1, stage.clientWidth), h = Math.max(1, stage.clientHeight);
    if (this._scrollMode) {
      // 1.3.0: a full-screen canvas. The pixel ratio is capped (max-dpr, default 1.75; the drawing buffer stays
      // under about 3200 px on its long side) and lowered by _perfTick if frames run slow.
      const cap = parseFloat(this.getAttribute('max-dpr')) || 1.75;
      this._prCap = Math.max(0.75, Math.min(window.devicePixelRatio || 1, cap, 3200 / Math.max(w, h)));
      this._stickyTop = parseFloat(getComputedStyle(this.$('.sv-sticky')).top) || 0;
      this._stageW = w; this._stageH = h;
      this._renderer.setPixelRatio(Math.max(Math.min(1, this._prCap) * 0.8, this._prCap * (this._prScale ?? 1)));
      this._measureCaption();
      this._svRect = null;
      this._scrollDirty = true;
    }
    this._renderer.setSize(w, h, false);
    this._camera.aspect = w / h;
    this._camera.updateProjectionMatrix();
    this._needs = true;
  }

  _clearParts() {
    if (!this._parts) { this._parts = []; return; }
    for (const p of this._parts) {
      this._model.remove(p.root);
      p.root.traverse((o) => { [].concat(o.material || []).forEach((mm) => mm.dispose?.()); });
    }
    this._parts = [];
  }

  _disposeScene() {
    this._controls?.dispose();
    this._scene?.traverse((o) => {
      o.geometry?.dispose?.();
      [].concat(o.material || []).forEach((mm) => { mm.map?.dispose?.(); mm.dispose?.(); });
    });
    this._envTex?.dispose();
    this._renderer?.dispose();
    this._renderer = null; this._scene = null; this._parts = null;
  }

  async _loadParts(m, progress, token) {
    const loader = new GLTFLoader();
    loader.setMeshoptDecoder(MeshoptDecoder);
    if (m.draco) {
      const { DRACOLoader } = await import('three/addons/loaders/DRACOLoader.js');
      const d = new DRACOLoader(); d.setDecoderPath(m.draco); loader.setDRACOLoader(d);
    }
    const get = (url) => {
      if (!GLTF_CACHE.has(url)) {
        // one quiet retry: a busy server or a dropped connection should not leave a hole in the model
        const pr = loader.loadAsync(url).catch(() => new Promise((r) => setTimeout(r, 500)).then(() => loader.loadAsync(url)));
        pr.catch(() => GLTF_CACHE.delete(url));     // a failed download can be retried by the next load
        GLTF_CACHE.set(url, pr);
      }
      return GLTF_CACHE.get(url);
    };
    const todo = m.parts.filter((p) => !p.hidden && p.model);
    let done = 0, failed = 0, next = 0;
    const worker = async () => {
      while (next < todo.length) {
        const p = todo[next++];
        try {
          const g = await get(p.model);
          if (this._loadToken !== token) return;
          this._addPart(p, g);
        } catch (e) {
          failed++; console.warn('[exploded-view] part failed to load:', p.id, e?.message || e);
        }
        progress(++done, todo.length);
      }
    };
    await Promise.all(Array.from({ length: Math.min(6, todo.length) }, worker));
    if (failed) m.warnings.push(`${failed} part(s) failed to load`);
  }

  _addPart(p, gltf) {
    let src = gltf.scene;
    if (p.node) src = gltf.scene.getObjectByName(p.node) || gltf.scene;
    const inner = src.clone(true);
    if (p.node) { src.updateWorldMatrix(true, false); inner.applyMatrix4(src.matrixWorld); }
    if (p.matrix) { const M = new THREE.Matrix4().fromArray(p.matrix); inner.applyMatrix4(M); }
    const root = new THREE.Group();
    root.name = p.id;
    root.add(inner);
    const mats = [];
    inner.traverse((o) => {
      if (!o.isMesh) return;
      const hasVC = !!o.geometry.attributes.color;
      const useModel = p.colour === 'model';
      const old = o.material;
      const mat = new THREE.MeshStandardMaterial({
        color: useModel ? (hasVC ? 0xffffff : (old?.color?.clone?.() ?? 0xdddddd)) : new THREE.Color(p.colour),
        vertexColors: useModel && hasVC,
        roughness: p.roughness, metalness: p.metalness,
        envMapIntensity: 0.55,
        transparent: p.opacity < 1, opacity: p.opacity,
        side: THREE.FrontSide,
      });
      if (useModel && old?.map) mat.map = old.map;
      o.material = mat;
      o.userData.partId = p.id;
      mats.push(mat);
    });
    this._model.add(root);
    this._parts.push(Object.assign(p, {
      root, mats, offset: new THREE.Vector3(),
      lift: 0, ghost: 1, fade: 1, glow: 0, liftVecCur: new THREE.Vector3(),
    }));
  }

  /* ---------- geometry prep: centres, explode vectors, camera fit ---------- */
  _prepare() {
    const m = this._m;
    if (m.upAxis === 'z') this._model.rotation.x = -Math.PI / 2; else this._model.rotation.set(0, 0, 0);
    this._model.updateMatrixWorld(true);
    const box = new THREE.Box3();
    const local = new THREE.Box3();
    for (const p of this._parts) {
      local.makeEmpty();
      p.root.updateMatrixWorld(true);
      p.root.traverse((o) => {
        if (!o.isMesh) return;
        o.geometry.computeBoundingBox();
        const b = o.geometry.boundingBox.clone();
        // transform into the model group's local space
        const M = new THREE.Matrix4().copy(this._model.matrixWorld).invert().multiply(o.matrixWorld);
        local.union(b.applyMatrix4(M));
      });
      p.box = local.clone();
      p.center = local.getCenter(new THREE.Vector3());
      p.size = local.getSize(new THREE.Vector3()).length();
      box.union(local);
    }
    this._box = box;
    this._center = box.getCenter(new THREE.Vector3());
    this._radius = Math.max(1e-6, box.getSize(new THREE.Vector3()).length() / 2);
    const R = this._radius;

    // explode vectors
    const orders = this._parts.map((p) => p.order);
    const oMin = Math.min(...orders), oMax = Math.max(...orders);
    for (const p of this._parts) {
      const e = p.explode || {};
      const d = new THREE.Vector3().subVectors(p.center, this._center);
      let dir;
      if (Array.isArray(e.dir)) dir = new THREE.Vector3(...e.dir);
      else if (e.dir === 'radial-x') dir = new THREE.Vector3(Math.sign(d.x) || 1, 0, 0);
      else if (e.dir === 'radial-y') dir = new THREE.Vector3(0, Math.sign(d.y) || 1, 0);
      else if (e.dir === 'radial-z') dir = new THREE.Vector3(0, 0, Math.sign(d.z) || 1);
      else if (e.dir === 'radial-xz') dir = new THREE.Vector3(d.x, 0, d.z);
      else if (e.dir === 'none') dir = new THREE.Vector3();
      else dir = d.clone();
      if (dir.lengthSq() < 1e-9 && e.dir !== 'none') dir.set(0, 1, 0);
      dir.normalize();
      const dist = typeof e.distance === 'number' ? e.distance : 0.35 * R;
      p.explodeVec = dir.clone().multiplyScalar(dist);
      if (Array.isArray(e.add)) p.explodeVec.add(new THREE.Vector3(...e.add));
      p.explodeDir = p.explodeVec.lengthSq() > 0 ? p.explodeVec.clone().normalize() : new THREE.Vector3(0, 1, 0);
      p.rank = oMax > oMin ? (oMax - p.order) / (oMax - oMin) : 0;   // 0 = built last = comes off first
      p.dropVec = p.explodeDir.clone().multiplyScalar(Math.max(0.5 * R, Math.min(dist, 0.9 * R)));
    }
    // build: index inside its step, for a small stagger
    m.build.forEach((s) => s.parts.forEach((id, j) => {
      const p = m.byId.get(id);
      if (p && p.buildStep === m.build.indexOf(s)) { p.stepIndex = j; p.stepCount = s.parts.length; }
    }));
    // fit radius covers the fully exploded model too
    const ex = new THREE.Box3();
    for (const p of this._parts) ex.union(p.box.clone().translate(p.explodeVec));
    this._explodedRadius = ex.getSize(new THREE.Vector3()).length() / 2;
    this._fitRadius = lerp(R, this._explodedRadius, 0.3);
    // auto-framing: as the model explodes, the camera dollies out and re-centres on the exploded parts
    this._frameRatio = Math.max(1, lerp(R, this._explodedRadius, 0.92) / this._fitRadius);
    this._frameOffset = this._toWorld(ex.getCenter(new THREE.Vector3())).sub(this._toWorld(this._center));
    this._frameCur = { k: 0, s: 1 };
    this._controls.minDistance = 0.25 * R;
    this._controls.maxDistance = 8 * this._fitRadius;
    this._camera.near = Math.max(0.01, R / 200);
    this._camera.far = R * 60;
    this._camera.updateProjectionMatrix();
    this._makeShadow();
  }

  _makeShadow() {
    if (this._shadow) { this._scene.remove(this._shadow); this._shadow.geometry.dispose(); this._shadow.material.map.dispose(); this._shadow.material.dispose(); }
    const c = document.createElement('canvas'); c.width = c.height = 128;
    const g = c.getContext('2d');
    const grd = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    grd.addColorStop(0, 'rgba(74,51,38,0.55)'); grd.addColorStop(0.55, 'rgba(74,51,38,0.18)'); grd.addColorStop(1, 'rgba(74,51,38,0)');
    g.fillStyle = grd; g.fillRect(0, 0, 128, 128);
    const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace;
    const size = this._box.getSize(new THREE.Vector3());
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
      new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false, opacity: 0.6 }));
    mesh.rotation.x = -Math.PI / 2;
    const wb = this._box.clone().applyMatrix4(this._model.matrixWorld);
    const wc = wb.getCenter(new THREE.Vector3());
    mesh.position.set(wc.x, wb.min.y - this._radius * 0.01, wc.z);
    mesh.scale.set(Math.max(size.x, size.z) * 1.5, Math.max(size.x, size.z) * 1.5, 1);
    mesh.renderOrder = -1;
    this._shadow = mesh;
    this._scene.add(mesh);
  }

  _buildUIForManifest() {
    const m = this._m;
    const chips = this.$('#chips');
    chips.innerHTML = '';
    for (const c of m.cameras) {
      const b = document.createElement('button');
      b.className = 'ev-chip'; b.textContent = c.label || c.id; b.dataset.cam = c.id; b.setAttribute('aria-pressed', 'false');
      b.addEventListener('click', () => this._applyCamera(c.id, true));
      chips.appendChild(b);
    }
    const br = this._range('build'); br.max = Math.max(1, m.build.length); this.$('#buildTotal').textContent = m.build.length;
    const er = this._range('energy'); er.max = Math.max(1, m.energy.stages.length); this.$('#energyTotal').textContent = m.energy.stages.length;
    const dots = this.$('#energyDots'); dots.innerHTML = '';
    m.energy.stages.forEach((s, i) => {
      const d = document.createElement('button');
      d.className = 'ev-dot'; d.textContent = i + 1; d.title = s.title; d.setAttribute('aria-label', `Stage ${i + 1}: ${s.title}`);
      d.addEventListener('click', () => this.goToStage(i));
      dots.appendChild(d);
    });
    this._step = 0; this._stage = 0; this._buildT = 1; this._buildTarget = 1;
    this.setExplode(this._explode * 100);
    [br, er].forEach((r) => this._fill(r));
  }

  /* ---------- camera presets ---------- */
  _toWorld(v) { return this._model.localToWorld(v.clone()); }
  _cameraPose(id) {
    const c = this._m.cameras.find((k) => k.id === id) || this._m.cameras[0] || { dir: [1, 0.55, 1.4], zoom: 1 };
    const fc = this._frameCur || { k: 0, s: 1 };
    const target = Array.isArray(c.target) ? this._toWorld(new THREE.Vector3(...c.target)) : this._toWorld(this._center);
    if (this._frameOffset) target.addScaledVector(this._frameOffset, fc.k);
    let pos;
    if (Array.isArray(c.position)) pos = this._toWorld(new THREE.Vector3(...c.position));
    else {
      const dir = new THREE.Vector3(...(c.dir || [1, 0.55, 1.4])).normalize();
      const vf = THREE.MathUtils.degToRad(this._camera.fov);
      const hf = 2 * Math.atan(Math.tan(vf / 2) * this._camera.aspect);
      const dist = (this._fitRadius / Math.sin(Math.min(vf, hf) / 2)) * (c.zoom || 1) * 0.84 * fc.s;
      pos = target.clone().add(dir.multiplyScalar(dist));
    }
    return { pos, target, id: c.id };
  }
  _applyCamera(id, animate) {
    if (!this._camera || !this._center) return;
    const pose = this._cameraPose(id);
    this._markChip(pose.id);
    if (!animate || this._reducedMotion()) {
      this._camera.position.copy(pose.pos); this._controls.target.copy(pose.target);
      this._controls.update(); this._camAnim = null; this._needs = true; return;
    }
    this._camAnim = { t: 0, fromP: this._camera.position.clone(), fromT: this._controls.target.clone(), toP: pose.pos, toT: pose.target };
    this._needs = true;
  }
  _markChip(id) {
    this.shadowRoot.querySelectorAll('.ev-chip').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.cam === id)));
  }

  /* ---------- pointer: hover tooltip, tap to select ---------- */
  _wirePointer(canvas) {
    let down = null;
    canvas.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, t: performance.now() }; });
    canvas.addEventListener('pointerup', (e) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      const quick = performance.now() - down.t < 600;
      down = null;
      if (moved > 7 || !quick) return;
      const p = this._pick(e);
      if (p) this._select(p); else this._clearSelection();
    });
    canvas.addEventListener('pointermove', (e) => {
      if (e.pointerType !== 'mouse' || e.buttons) { this._setHover(null); return; }
      this._lastMove = e;
      if (!this._hoverQueued) {
        this._hoverQueued = true;
        requestAnimationFrame(() => { this._hoverQueued = false; const ev = this._lastMove; if (ev) this._setHover(this._pick(ev), ev); });
      }
    });
    canvas.addEventListener('pointerleave', () => { this._lastMove = null; this._setHover(null); });
  }
  _pick(e) {
    if (!this._ready || !this._parts?.length) return null;
    const rect = this.shadowRoot.querySelector('canvas').getBoundingClientRect();
    this._pointer.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    this._raycaster.setFromCamera(this._pointer, this._camera);
    const targets = [];
    for (const p of this._parts) if (p.root.visible && (this._scrollMode || p.ghost * p.fade > 0.3)) p.root.traverse((o) => { if (o.isMesh) targets.push(o); });
    const hit = this._raycaster.intersectObjects(targets, false)[0];
    return hit ? this._m.byId.get(hit.object.userData.partId) : null;
  }
  _setHover(p, e) {
    const tip = this.$('#tip');
    if (p !== this._hover) { this._hover = p; this._needs = true; }
    if (!p || !e) { tip.style.transform = 'translate(-9999px,0)'; this.shadowRoot.querySelector('canvas').style.cursor = ''; return; }
    this.shadowRoot.querySelector('canvas').style.cursor = 'pointer';
    tip.innerHTML = `<b>${esc(p.name)}</b>${p.role ? esc(p.role) : ''}`;
    const rect = this.shadowRoot.querySelector('.ev-stage').getBoundingClientRect();
    let x = e.clientX - rect.left + 16, y = e.clientY - rect.top + 16;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    if (x + w > rect.width - 8) x = e.clientX - rect.left - w - 12;
    if (y + h > rect.height - 8) y = e.clientY - rect.top - h - 12;
    tip.style.transform = `translate(${Math.max(8, x)}px, ${Math.max(8, y)}px)`;
  }
  _select(p) {
    this._selected = p; this._needs = true;
    const extra = p.placeholder ? `<br><small style="color:var(--ev-muted)">Shown as a simple placeholder shape for now.</small>` : '';
    this.$('#cardText').innerHTML = `<b>${esc(p.name)}</b>${esc(p.role || p.groupName || '')}${extra}`;
    this.$('#card').hidden = false;
    this._emit('partselect', { id: p.id, name: p.name, role: p.role });
  }
  _clearSelection() {
    if (this._selected) { this._selected = null; this._needs = true; }
    const c = this.$('#card'); if (c) c.hidden = true;
  }

  /* ---------- energy path: dots along a curve plus glowing pulses ---------- */
  _makePathObjects() {
    const MAX = 600;
    const dotGeo = new THREE.SphereGeometry(1, 10, 8);
    const dotMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, depthTest: false, depthWrite: false });
    this._dots = new THREE.InstancedMesh(dotGeo, dotMat, MAX);
    this._dots.count = 0; this._dots.renderOrder = 10; this._dots.frustumCulled = false;
    this._scene.add(this._dots);
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const g = c.getContext('2d');
    const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.25, 'rgba(255,236,200,0.95)');
    grd.addColorStop(0.6, 'rgba(255,190,90,0.35)'); grd.addColorStop(1, 'rgba(255,170,60,0)');
    g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
    this._glowTex = new THREE.CanvasTexture(c); this._glowTex.colorSpace = THREE.SRGBColorSpace;
    this._pulses = [];
    for (let i = 0; i < 24; i++) {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this._glowTex, transparent: true, depthTest: false, depthWrite: false, blending: THREE.AdditiveBlending }));
      s.renderOrder = 11; s.visible = false;
      this._scene.add(s); this._pulses.push(s);
    }
    this._tmpM = new THREE.Matrix4();
  }
  _energyColour() {
    const v = getComputedStyle(this).getPropertyValue('--ev-energy').trim() || '#f0a43a';
    if (v !== this._energyHex) { this._energyHex = v; try { this._energyCol = new THREE.Color(v); } catch { this._energyCol = new THREE.Color('#f0a43a'); } }
    return this._energyCol;
  }
  _partPoint(ids) {
    const v = new THREE.Vector3(); let n = 0;
    for (const id of ids) { const p = this._m.byId.get(id); if (p?.root) { v.add(p.center).add(p.offset); n++; } }
    return n ? v.divideScalar(n) : null;
  }
  _updatePath(time, fadeIn) {
    const show = this._mode === 'energy' && this._m.energy.stages.length;
    const stage = show ? this._m.energy.stages[this._stage] : null;
    let nDots = 0, nPulse = 0;
    const labels = [];
    if (stage) {
      const R = this._radius, col = this._energyColour();
      this._dots.material.color.copy(col);
      this._dots.material.opacity = 0.85 * fadeIn;
      for (const line of stage.path) {
        const pts = [];
        for (const node of line) {
          const v = node.point ? new THREE.Vector3(...node.point) : this._partPoint(node.parts);
          if (v) pts.push(v);
          if (node.point) labels.push({ at: v, text: node.label, alt: true });
        }
        if (pts.length < 2) continue;
        // gentle arch between consecutive points so the path reads as a flow, not a line through solids
        const ctrl = [pts[0]];
        for (let i = 1; i < pts.length; i++) {
          const a = pts[i - 1], b = pts[i];
          const mid = a.clone().add(b).multiplyScalar(0.5);
          mid.y += Math.min(0.12 * R, a.distanceTo(b) * 0.18);
          ctrl.push(mid, b);
        }
        const curve = new THREE.CatmullRomCurve3(ctrl, false, 'centripetal');
        const len = curve.getLength();
        const count = Math.min(140, Math.max(8, Math.round(len / (0.035 * R))));
        const r = 0.0065 * R;
        for (let i = 0; i <= count && nDots < this._dots.instanceMatrix.count; i++) {
          const pt = this._toWorld(curve.getPointAt(i / count));
          this._tmpM.makeScale(r, r, r).setPosition(pt);
          this._dots.setMatrixAt(nDots++, this._tmpM);
        }
        if (!this._reducedMotion()) {
          const speed = 0.16 * R / Math.max(len, 1e-6) * 2.2;
          for (let k = 0; k < 2 && nPulse < this._pulses.length; k++) {
            const u = ((time * speed + k / 2) % 1 + 1) % 1;
            const s = this._pulses[nPulse++];
            s.position.copy(this._toWorld(curve.getPointAt(u)));
            const sc = 0.07 * R * (0.85 + 0.15 * Math.sin(time * 6 + k));
            s.scale.set(sc, sc, sc); s.visible = true; s.material.opacity = fadeIn;
            s.material.color.copy(col);
          }
        }
      }
      // labels for the stage's own parts (one per part when few, one for the group when many)
      if (stage.labels && stage.parts.length) {
        if (stage.parts.length <= 3) {
          for (const id of stage.parts) { const p = this._m.byId.get(id); if (p?.root) labels.push({ at: p.center.clone().add(p.offset), text: p.name }); }
        } else {
          const c = this._partPoint(stage.parts);
          if (c) labels.push({ at: c, text: stage.title });
        }
      }
    }
    this._dots.count = nDots;
    this._dots.instanceMatrix.needsUpdate = true;
    for (let i = nPulse; i < this._pulses.length; i++) this._pulses[i].visible = false;
    this._placeLabels(labels, fadeIn);
  }
  _placeLabels(list, alpha = 1) {
    const host = this.$('#labels');
    while (host.children.length < list.length) { const d = document.createElement('div'); d.className = 'ev-label'; host.appendChild(d); }
    const stage = this.shadowRoot.querySelector('.ev-stage');
    const w = stage.clientWidth, h = stage.clientHeight;
    const placed = [];
    [...host.children].forEach((el, i) => {
      const L = list[i];
      if (!L) { el.style.transform = 'translate(-9999px,0)'; return; }
      const v = this._toWorld(L.at).project(this._camera);
      if (v.z > 1) { el.style.transform = 'translate(-9999px,0)'; return; }
      if (el.textContent !== L.text) el.textContent = L.text;
      el.classList.toggle('alt', !!L.alt);
      const x = (v.x * 0.5 + 0.5) * w, y = (-v.y * 0.5 + 0.5) * h;
      const ew = el.offsetWidth, eh = el.offsetHeight || 30;
      let cx = Math.min(w - ew - 8, Math.max(8, x - ew / 2));
      let cy = Math.min(h - eh - 60, Math.max(8, y - eh - 18));
      // never stack labels: nudge up past any label already placed, and drop it if there is no room
      for (let k = 0; k < 6; k++) {
        const hit = placed.find((r) => cx < r.x + r.w + 6 && cx + ew + 6 > r.x && cy < r.y + r.h + 6 && cy + eh + 6 > r.y);
        if (!hit) break;
        cy = hit.y - eh - 8;
      }
      if (cy < 4 || placed.some((r) => cx < r.x + r.w && cx + ew > r.x && cy < r.y + r.h && cy + eh > r.y)) {
        el.style.transform = 'translate(-9999px,0)'; return;
      }
      placed.push({ x: cx, y: cy, w: ew, h: eh });
      el.style.opacity = String(alpha);
      el.style.transform = `translate(${cx}px, ${cy}px)`;
    });
  }
  _liftTarget(p) {
    const st = this._m.energy.stages[this._stage];
    return this._mode === 'energy' && st && st.parts.includes(p.id) ? 1 : 0;
  }
  _ghostTarget(p) {
    if (this._mode !== 'energy') return 1;
    const st = this._m.energy.stages[this._stage];
    if (!st) return 1;
    if (st.parts.includes(p.id)) return 1;
    const onPath = st.path.some((line) => line.some((n) => n.parts?.includes(p.id)));
    return onPath ? 0.42 : this._m.energy.ghostOpacity;
  }
  _stageLiftVec(p) {
    const st = this._m.energy.stages[this._stage];
    if (st?.lift) return new THREE.Vector3(...st.lift);
    // default: straight out of the top of the body (model "up"), so the part is never hidden inside it
    const d = this._m.energy.liftDistance ?? 0.45 * this._radius;
    return new THREE.Vector3(...this._m.energy.liftDir).normalize().multiplyScalar(d);
  }

  /* ---------- per-frame update ---------- */
  _update(dt, time) {
    if (!this._ready || !this._parts?.length) return false;
    if (this._scrollMode) return this._updateScroll(dt, time);
    let anim = false;
    const reduced = this._reducedMotion();

    // camera tween
    if (this._camAnim) {
      const a = this._camAnim;
      a.t = Math.min(1, a.t + dt / 0.8);
      const k = easeInOut(a.t);
      this._camera.position.lerpVectors(a.fromP, a.toP, k);
      this._controls.target.lerpVectors(a.fromT, a.toT, k);
      if (a.t >= 1) this._camAnim = null;
      anim = true;
    }
    if (this._controls.update()) anim = true;

    // mode change: blend from where parts were to where the new mode wants them
    if (this._lastMode !== this._mode) {
      this._lastMode = this._mode;
      this._blend = reduced ? 1 : 0;
      for (const p of this._parts) { p.fromOffset = p.offset.clone(); p.fromFade = p.fade; }
      if (this._mode === 'energy') this._prepStageLift();
    }
    if (this._blend < 1) { this._blend = Math.min(1, this._blend + dt / 0.55); anim = true; }
    const blend = easeInOut(this._blend ?? 1);

    const mode = this._mode;
    const target = new THREE.Vector3();
    const accent = this._accentCol || (this._accentCol = new THREE.Color('#c98a55'));
    const energyCol = this._energyColour();

    if (mode === 'explode') {
      const d = this._explode - this._explodeShown;
      if (reduced || Math.abs(d) < 0.0008) this._explodeShown = this._explode;
      else { this._explodeShown += d * Math.min(1, dt * 5.5); anim = true; }
    }
    if (mode === 'build') {
      const d = this._buildTarget - this._buildT;
      if (reduced || Math.abs(d) < 1e-3) this._buildT = this._buildTarget;
      else { this._buildT += Math.sign(d) * Math.min(Math.abs(d), this._buildSpeed * dt); anim = true; }
    }
    if (mode === 'energy' && this._stageSeen !== this._stage) { this._stageSeen = this._stage; this._prepStageLift(); }

    this._autoFrame(mode === 'explode' ? easeInOut(this._explodeShown) : 0, mode === 'energy' ? 1.1 : 1);

    const stag = clamp(this._m.explodeStagger, 0, 0.9);
    for (const p of this._parts) {
      let fade = 1, ghost = 1, emis = 0, emisCol = accent;
      if (mode === 'explode') {
        const t = clamp((this._explodeShown - p.rank * stag) / (1 - stag));
        target.copy(p.explodeVec).multiplyScalar(easeInOut(t));
      } else if (mode === 'build') {
        const k = p.buildStep ?? 0, n = p.stepCount || 1, j = p.stepIndex || 0;
        const delay = n > 1 ? (j / (n - 1)) * 0.35 : 0;
        const local = clamp((this._buildT - k - delay) / 0.65);
        target.copy(p.dropVec).multiplyScalar(1 - softLand(local));
        fade = clamp(local * 3);
        if (k === this._step && local >= 1) emis = 0.12;
      } else {
        const lt = this._liftTarget(p);
        if (reduced) p.lift = lt;
        else if (p.lift !== lt) { p.lift += Math.sign(lt - p.lift) * Math.min(Math.abs(lt - p.lift), dt / 0.85); anim = true; }
        const gt = this._ghostTarget(p);
        if (reduced) p.ghost = gt;
        else if (Math.abs(p.ghost - gt) > 1e-3) { p.ghost += Math.sign(gt - p.ghost) * Math.min(Math.abs(gt - p.ghost), dt / 0.45); anim = true; }
        else p.ghost = gt;
        ghost = p.ghost;
        target.copy(p.liftVecCur).multiplyScalar(easeInOut(p.lift));
        if (lt === 1 || p.lift > 0) {
          emis = (reduced ? 0.55 : 0.5 + 0.22 * Math.sin(time * 3.4)) * easeInOut(p.lift);
          emisCol = energyCol;
        }
      }
      if (mode !== 'energy') { p.ghost = 1; p.lift = 0; }
      if (this._blend < 1) {
        p.offset.lerpVectors(p.fromOffset, target, blend);
        fade = lerp(p.fromFade ?? 1, fade, blend);
      } else p.offset.copy(target);
      p.fade = fade;
      if (p === this._selected) { emis = Math.max(emis, 0.32); if (emisCol !== energyCol) emisCol = accent; }
      else if (p === this._hover) { emis = Math.max(emis, 0.2); if (emisCol !== energyCol) emisCol = accent; }
      this._applyVisual(p, fade, ghost, emis, emisCol);
    }

    // energy pulse + labels
    if (mode === 'energy') {
      const fadeIn = reduced ? 1 : clamp((time - (this._energyStart ?? 0)) / 0.6);
      this._updatePath(time, fadeIn);
      if (!reduced) anim = true;          // pulse runs continuously while this tab is open and on screen
    } else if (this._dots.count || this._pulses[0].visible) {
      this._dots.count = 0; this._pulses.forEach((s) => { s.visible = false; }); this._placeLabels([]);
    }
    return anim;
  }

  _autoFrame(k, extra) {
    const cur = this._frameCur;
    if (!cur || this.hasAttribute('no-autoframe')) return;
    const s = lerp(1, this._frameRatio, k) * extra;
    if (Math.abs(s - cur.s) < 1e-4 && Math.abs(k - cur.k) < 1e-4) return;
    const t = this._controls.target;
    const rel = this._camera.position.clone().sub(t).multiplyScalar(s / cur.s);
    t.addScaledVector(this._frameOffset, k - cur.k);
    this._camera.position.copy(t).add(rel);
    if (this._camAnim) {           // keep a running preset tween consistent with the new framing
      const a = this._camAnim;
      const relA = a.toP.clone().sub(a.toT).multiplyScalar(s / cur.s);
      a.toT.addScaledVector(this._frameOffset, k - cur.k);
      a.toP.copy(a.toT).add(relA);
    }
    cur.k = k; cur.s = s;
    this._needs = true;
  }

  _prepStageLift() {
    const st = this._m.energy.stages[this._stage];
    if (!st) return;
    for (const id of st.parts) { const p = this._m.byId.get(id); if (p?.root) p.liftVecCur = this._stageLiftVec(p); }
  }

  _applyVisual(p, fade, ghost, emis, emisCol) {
    p.root.position.copy(p.offset);
    const op = p.opacity * ghost * fade;
    p.root.visible = op > 0.005;
    // scroll mode dims and lifts parts all the time: keep one shader variant (always transparent) so a part
    // fading for the first time never costs a shader compile mid-scroll
    const transparent = this._scrollMode || op < 0.999;
    for (const m of p.mats) {
      if (m.transparent !== transparent) { m.transparent = transparent; m.needsUpdate = true; }
      m.opacity = op;
      m.depthWrite = op > 0.55;
      m.emissive.copy(emisCol);
      m.emissiveIntensity = emis;
    }
  }

  /* ================================================================================================
   * 1.2.0 scroll mode. The page scrolls natively; the animation only follows it (no scroll-jacking).
   * Progress 0..1 through the element -> explode amount (apart, hold, back together) -> layer timings.
   * ============================================================================================== */
  _scrollTemplate() {
    const u = this._uid;
    return `
<div class="sv" part="root">
  <div class="sv-sticky" part="sticky">
    <div class="sv-stage" part="stage">
      <canvas role="img" aria-label="3D model. Scroll to take it apart and put it back together. Hover or tap a part to see what it does."></canvas>
      <div class="sv-poster"><slot name="poster"></slot></div>
      <div class="sv-wash" aria-hidden="true"></div>
      <div class="sv-beat" id="beat" aria-live="polite">
        <p class="sv-kicker"><span id="beatKicker"></span><span class="sv-count" id="beatCount"></span><span class="sv-layer" id="layer" aria-hidden="true" hidden></span></p>
        <h3 id="beatTitle"></h3>
        <p class="sv-text" id="beatText"></p>
        <span class="sv-cue gone" id="cue" aria-hidden="true">${ICONS.down}Scroll</span>
      </div>
      <nav class="sv-dots" id="dots" aria-label="Jump to a part of the story"><span class="sv-rail" aria-hidden="true"><i></i></span></nav>
      <aside class="sv-bcard" id="bcard" aria-hidden="true">
        <span class="sv-thumb" id="bThumb"><i></i></span>
        <div class="sv-bcard-main"><span class="sv-bcard-k" id="bKick">In focus</span><span class="sv-bcard-t" id="bTitle"></span>
          <p class="sv-bcard-x" id="bText"></p><p class="sv-bcard-f" id="bFact"></p></div>
      </aside>
      <div class="sv-chips">
        <button type="button" class="sv-chip" id="partsBtn" aria-expanded="false" aria-controls="drawer-${u}">${ICONS.parts}<span id="partsLbl">Parts</span></button>
        <div class="sv-toggle" id="stageToggle" role="group" aria-label="Stage colour" hidden>
          <span class="sv-toggle-lbl" aria-hidden="true">Stage</span>
          <button type="button" data-stage="light" aria-pressed="false">Light</button>
          <button type="button" data-stage="dark" aria-pressed="false">Dark</button>
        </div>
      </div>
      <div class="sv-tip" id="tip"><div id="tipBody"></div><button type="button" class="sv-tip-x" id="tipX" aria-label="Close part details">&times;</button></div>
      <section class="sv-drawer" id="drawer-${u}" aria-labelledby="drawerTitle-${u}">
        <div class="sv-drawer-head"><h4 id="drawerTitle-${u}">Main parts</h4><button type="button" class="sv-x" id="drawerX" aria-label="Close the parts list">&times;</button></div>
        <ul class="sv-cards" id="cards" aria-label="Main parts"></ul>
      </section>
      <div class="sv-loading" id="loading"><div id="loadMsg">Loading the 3D model…</div><div class="ev-bar"><i id="bar"></i></div></div>
    </div>
  </div>
</div>`;
  }

  /** Public: switch the scroll stage colour ("light" or "dark") and remember it. */
  setStage(st) { if (this._scrollMode) this._setStage(st, true); }
  /** Public (1.3.0): open or close the scroll mode's parts drawer. */
  showParts(open = true) { if (this._scrollMode) this._setDrawer(!!open); }

  _attachScroll() {
    if (this._onScroll) return;
    this._onScroll = () => { this._svChrome(); this._scrollDirty = true; this._needs = true; if (this._ready) this._loop(); };
    window.addEventListener('scroll', this._onScroll, { passive: true });
    window.addEventListener('resize', this._onScroll, { passive: true });
    this._onReducedScroll = () => this._applyReduced();
    this._reduced.addEventListener?.('change', this._onReducedScroll);
    const len = parseFloat(this.getAttribute('scroll-length'));
    if (len > 0) this.style.setProperty('--ev-scroll-length', `${len}vh`);
    const pl = this.getAttribute('parts-label'), pt = this.getAttribute('parts-title');
    if (pl) this.$('#partsLbl').textContent = pl;
    if (pt) { this.shadowRoot.querySelector('.sv-drawer h4').textContent = pt; this.$('#cards').setAttribute('aria-label', pt); }
    this._applyReduced();
    this._initStage();
    this._svChrome();
    this._detachScroll = () => {
      window.removeEventListener('scroll', this._onScroll);
      window.removeEventListener('resize', this._onScroll);
      this._reduced.removeEventListener?.('change', this._onReducedScroll);
      this._onScroll = null;
      if (this._pinned) { this._pinned = false; this.removeAttribute('data-pinned'); }
    };
  }
  _applyReduced() {
    this.toggleAttribute('data-reduced', this._reducedMotion());
    this._scrollDirty = true; this._needs = true; this._beatShown = undefined;
    requestAnimationFrame(() => {
      this._resize(); this._svChrome();
      if (this._ready && this._reducedMotion() && (this._stageW || 0) >= 900 && !this._drawerOpen) this._setDrawer(true);
    });
  }
  /* 1.3.0: the stage grows from a rounded card to full-bleed as it pins (and shrinks back as it leaves), and the
     host gets data-pinned while the stage fills the screen, so a page can tuck its own header away. Runs on every
     scroll event, before the 3D is ready too, and only touches styles when a value changes. */
  _svChrome() {
    const st = this.$('.sv-sticky');
    if (!st || !this.isConnected) return;
    const r = this.getBoundingClientRect(), vh = window.innerHeight || 1;
    const reduced = this.hasAttribute('data-reduced');
    let g = 1;
    if (!reduced && !this.hasAttribute('no-grow')) {
      const top = r.top - (this._stickyTop || 0);
      g = easeInOut(Math.min(clamp(1 - top / (vh * 0.9)), clamp((r.bottom - vh * 0.1) / (vh * 0.9))));
    }
    const gx = Math.round((1 - g) * Math.min(56, r.width * 0.045) * 10) / 10;
    if (gx !== this._growX) {
      this._growX = gx;
      st.style.setProperty('--sv-ix', `${gx}px`);
      st.style.setProperty('--sv-iy', `${Math.round(gx * 0.6 * 10) / 10}px`);
      st.style.setProperty('--sv-ir', `${Math.round((1 - g) * 28)}px`);
    }
    const pinned = !reduced && r.top <= vh * 0.1 && r.bottom >= vh * 0.9;
    if (pinned !== this._pinned) {
      this._pinned = pinned;
      this.toggleAttribute('data-pinned', pinned);
      this._emit('pinchange', { pinned });
    }
  }
  _initStage() {
    const key = this.getAttribute('storage-key');
    let st = null;
    if (key) { try { st = window.localStorage.getItem(key); } catch { st = null; } }
    if (st !== 'light' && st !== 'dark') st = this.getAttribute('stage') === 'light' ? 'light' : 'dark';
    const t = this.$('#stageToggle');
    t.hidden = !this.hasAttribute('stage-toggle');
    const labels = (this.getAttribute('stage-labels') || 'Light,Dark').split(',').map((s) => s.trim());
    t.querySelector('[data-stage="light"]').textContent = labels[0] || 'Light';
    t.querySelector('[data-stage="dark"]').textContent = labels[1] || 'Dark';
    this._setStage(st, false);
  }
  _setStage(st, save) {
    st = st === 'light' ? 'light' : 'dark';
    if (this.getAttribute('stage') !== st) this.setAttribute('stage', st);
    this.shadowRoot.querySelectorAll('#stageToggle button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.stage === st)));
    if (save) {
      const key = this.getAttribute('storage-key');
      if (key) { try { window.localStorage.setItem(key, st); } catch { /* private window: the choice lasts this visit */ } }
      this._emit('stagechange', { stage: st });
    }
    this._needs = true;
  }
  _setDrawer(open, focusBack) {
    open = !!open;
    this._drawerOpen = open;
    const d = this.shadowRoot.querySelector('.sv-drawer');
    d.classList.toggle('open', open);
    d.inert = !open;
    this.$('#partsBtn').setAttribute('aria-expanded', String(open));
    this._measureCaption();
    if (this._ready) this._loop();
    if (open) {
      if (this._activeCardId) this._revealCard(this._activeCardId);
    } else {
      this._svPinCard = null; this._svHoverCard = null; this._svFocusCard = null;
      this._svRefresh();
      if (focusBack) this.$('#partsBtn').focus({ preventScroll: true });
    }
    this._needs = true;
  }
  _wireScrollUI() {
    this.shadowRoot.querySelectorAll('#stageToggle button').forEach((b) => b.addEventListener('click', () => this._setStage(b.dataset.stage, true)));
    // a tap can dock the card right under the finger; ignore the click that the same tap sends a moment later
    this.$('#tipX').addEventListener('click', () => { if (performance.now() - (this._pinAt || 0) > 450) this._svPin(null); });
    this.$('#partsBtn').addEventListener('click', () => this._setDrawer(!this._drawerOpen));
    this.$('#drawerX').addEventListener('click', () => this._setDrawer(false, true));
    this.shadowRoot.querySelector('.sv-drawer').inert = true;
    this.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      if (this._drawerOpen) { this._setDrawer(false, true); return; }
      this._svPinCard = null; this._svPin(null);
    });
    const list = this.$('#cards');
    const touched = () => { this._rowTouched = performance.now(); };
    list.addEventListener('pointerdown', touched, { passive: true });
    list.addEventListener('wheel', touched, { passive: true });
  }

  _buildScrollCards() {
    const S = this._m.scroll;
    const list = this.$('#cards');
    list.innerHTML = '';
    this._cardEls = new Map();
    this._svCardById = new Map(S.cards.map((c) => [c.id, c]));
    for (const c of S.cards) {
      const li = document.createElement('li');
      li.className = 'sv-card'; li.dataset.card = c.id;
      const bid = `cb-${c.id}-${this._uid}`;
      li.innerHTML = `<button type="button" class="sv-card-btn" aria-expanded="false" aria-controls="${bid}">` +
        `<span class="sv-thumb"><i></i></span><span class="sv-card-title">${esc(c.title)}</span>${ICONS.chev}</button>` +
        `<div class="sv-card-body" id="${bid}"><div><p class="sv-card-text">${esc(c.text)}</p>` +
        `${c.fact ? `<p class="sv-card-fact">${esc(c.fact)}</p>` : ''}</div></div>`;
      const btn = li.querySelector('button');
      li.addEventListener('pointerenter', (e) => { if (e.pointerType === 'mouse') { this._svHoverCard = c; this._svRefresh(); } });
      li.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse' && this._svHoverCard === c) { this._svHoverCard = null; this._svRefresh(); } });
      btn.addEventListener('focus', () => { if (btn.matches(':focus-visible')) { this._svFocusCard = c; this._svRefresh(); } });
      btn.addEventListener('blur', () => { if (this._svFocusCard === c) { this._svFocusCard = null; this._svRefresh(); } });
      btn.addEventListener('click', () => {
        this._svPinPart = null; this._hideTip();
        this._svPinCard = this._svPinCard === c ? null : c;
        this._svRefresh();
      });
      list.appendChild(li);
      this._cardEls.set(c.id, li);
    }
    this._partCard = new Map();
    for (const c of S.cards) for (const id of c.parts) if (!this._partCard.has(id)) this._partCard.set(id, c);
    // the progress dots: one per beat; a click scrolls the page (natively, smoothly) to that beat
    const dots = this.$('#dots');
    dots.querySelectorAll('.sv-dot').forEach((n) => n.remove());
    this._dotEls = S.beats.map((b, i) => {
      const d = document.createElement('button');
      d.type = 'button'; d.className = 'sv-dot'; d.innerHTML = '<i></i>';
      d.setAttribute('aria-label', `${i + 1} of ${S.beats.length}: ${b.title}`);
      d.addEventListener('click', () => this._goBeat(i));
      dots.appendChild(d);
      return d;
    });
    dots.hidden = S.beats.length < 2;
    this.$('#partsBtn').hidden = !S.cards.length;
    // fill the caption now, so the poster and the first 3D frame are framed around the real caption
    const first = this._reducedMotion() ? (S.static || S.beats[0]) : S.beats[0];
    this.$('#beatKicker').textContent = S.kicker || '';
    this.$('#beatCount').textContent = !this._reducedMotion() && S.beats.length ? `1 / ${S.beats.length}` : '';
    this.$('#beatTitle').textContent = first?.title || '';
    this.$('#beatText').textContent = first?.text || '';
    this._measureCaption();
  }
  /** Scrolls the page (native, smooth) to beat i, landing a little inside it. */
  _goBeat(i) {
    const S = this._m?.scroll;
    if (!S || !S.beats[i]) return;
    const a = S.beats[i].at, b = S.beats[i + 1]?.at ?? 1;
    const at = i === 0 ? 0 : Math.min(a + 0.025, (a + b) / 2);
    const r = this.getBoundingClientRect();
    const total = r.height - this.$('.sv-sticky').offsetHeight;
    window.scrollTo({ top: window.scrollY + r.top - (this._stickyTop || 0) + at * total, behavior: this._reducedMotion() ? 'auto' : 'smooth' });
  }

  _prepareScroll() {
    const S = this._m.scroll, byId = this._m.byId;
    const L = Math.max(1, S.layers.length);
    for (const p of this._parts) { p.svLayer = -1; p.svCarry = []; p.svLift = 0; p.svGlow = 0; p.ghost = 1; }
    S.layers.forEach((l, i) => l.parts.forEach((id) => { const p = byId.get(id); if (p?.root && p.svLayer < 0) p.svLayer = i; }));
    const loose = this._parts.filter((p) => p.svLayer < 0);
    loose.forEach((p) => { p.svLayer = L - 1; });
    if (S.layers.length && loose.length) console.warn('[exploded-view]', `${loose.length} part(s) are in no scroll layer; they move with the last layer: ${loose.slice(0, 6).map((p) => p.id).join(', ')}`);
    // "carry": parts that ride along (rigidly) with an earlier layer, then finish their own move in their own layer.
    // The carried amounts are taken off the part's own move, so fully apart is always exactly its explode vector.
    S.layers.forEach((l, i) => {
      if (!l.carry) return;
      const by = new THREE.Vector3(...l.carry.by);
      for (const id of l.carry.parts) { const p = byId.get(id); if (p?.root && p.svLayer > i) p.svCarry.push({ i, by }); }
    });
    for (const p of this._parts) {
      p.svRest = p.explodeVec.clone(); for (const c of p.svCarry) p.svRest.sub(c.by);
      // 1.3.0: the 8 corners of each part's box, for framing the camera on what is really there
      const b = p.box;
      p.svCorners = [];
      for (let k = 0; k < 8; k++) p.svCorners.push(new THREE.Vector3(k & 1 ? b.max.x : b.min.x, k & 2 ? b.max.y : b.min.y, k & 4 ? b.max.z : b.min.z));
    }
    const ov = S.overlap, w = 1 / (L - (L - 1) * ov);
    this._svWin = Array.from({ length: L }, (_, i) => ({ a: i * w * (1 - ov), w }));
    this._sp = null; this._beatShown = undefined; this._beatLive = null;
    this._svSet = new Set(); this._svLevel = null; this._activeCardId = undefined;
    this._svFs = null; this._svCamMix = 0; this._layerShown = undefined;
  }

  /** Small renders of each card's parts, made once with the same renderer (transparent background). */
  _makeThumbs() {
    const S = this._m.scroll;
    if (!S.cards.length || !this._renderer) return;
    const r = this._renderer, cam = this._camera;
    const prevPR = r.getPixelRatio(), prevSize = r.getSize(new THREE.Vector2()), prevAspect = cam.aspect;
    const size = 128;
    r.setPixelRatio(1); r.setSize(size, size, false);
    cam.clearViewOffset(); this._viewOff = undefined;
    cam.aspect = 1; cam.updateProjectionMatrix();
    if (this._shadow) this._shadow.visible = false;
    const cams = this._m.cameras;
    const base = cams.find((c) => c.id === this._m.defaultCamera) || cams[0] || { dir: [1, 0.55, 1.4] };
    const half = Math.sin(THREE.MathUtils.degToRad(cam.fov) / 2);
    this._thumbUrl = new Map();
    for (const c of S.cards) {
      const set = new Set(c.parts);
      const box = new THREE.Box3();
      for (const p of this._parts) {
        const on = set.has(p.id);
        p.root.visible = on; p.root.position.set(0, 0, 0);
        if (on) box.union(p.box);
      }
      const th = this._cardEls.get(c.id)?.querySelector('.sv-thumb');
      if (box.isEmpty() || !th) continue;
      const ctr = this._toWorld(box.getCenter(new THREE.Vector3()));
      const rad = Math.max(1e-6, box.getSize(new THREE.Vector3()).length() / 2);
      const def = (c.camera && cams.find((k) => k.id === c.camera)) || base;
      const dir = new THREE.Vector3(...(def.dir || [1, 0.55, 1.4])).normalize();
      cam.position.copy(ctr).addScaledVector(dir, (rad / half) * 0.9);
      cam.lookAt(ctr);
      r.render(this._scene, cam);
      const url = r.domElement.toDataURL('image/png');
      this._thumbUrl.set(c.id, url);
      th.innerHTML = `<img src="${url}" alt="" width="64" height="64">`;
    }
    for (const p of this._parts) p.root.visible = true;
    if (this._shadow) this._shadow.visible = true;
    r.setPixelRatio(prevPR); r.setSize(prevSize.x, prevSize.y, false);
    cam.aspect = prevAspect; cam.updateProjectionMatrix();
    this._bcardFor = undefined;
    this._needs = true;
  }

  /** Public: the current frame as a data URL (used to make a poster image of the whole product). */
  snapshot(type = 'image/png', quality) {
    if (!this._renderer || !this._ready) return null;
    this._update(0, this._clock.getElapsedTime());
    this._renderer.render(this._scene, this._camera);
    return this._renderer.domElement.toDataURL(type, quality);
  }

  /* 1.3.0 layout: where on the full-screen stage the model goes, in stage pixels [x0, y0, x1, y1].
     Wide stages keep a left column for the words (the beat card on top, the caption below) and give the model
     the rest; narrow ones put the caption at the bottom and the model above it. Three framings:
     whole (he fills about 80 % of the height), apart (the spread parts fill about 90 %), and focus (the beat's
     parts, big, clear of the card and the caption). */
  _measureCaption() {
    const w = this._stageW, h = this._stageH;
    if (!w || !h) return;
    const cap = this.$('#beat');
    const wide = w >= 900;
    const L = { wide };
    if (wide) {
      const capR = cap ? cap.offsetLeft + cap.offsetWidth : w * 0.34;
      // with the parts drawer open, the model slides left to stay clear of it
      const dr = this._drawerOpen ? this.shadowRoot.querySelector('.sv-drawer') : null;
      const x0 = Math.min(capR + 16, w * 0.45);
      const x1 = Math.max(x0 + w * 0.25, Math.min(w - Math.max(64, w * 0.045), dr ? dr.offsetLeft - 24 : w));
      L.whole = [x0 + 8, h * 0.1, x1 - 8, h * 0.9];
      L.apart = [x0 - 8, h * 0.045, x1, h * 0.955];
      L.focus = [x0 + 16, h * 0.1, x1 - 8, h * 0.9];
    } else {
      const sheet = this._drawerOpen ? this.shadowRoot.querySelector('.sv-drawer') : null;
      const capTop = Math.max(h * 0.24, Math.min(cap ? cap.offsetTop : h * 0.72, sheet ? sheet.offsetTop - 8 : h));
      const top = 62, x1 = w - 38;
      const bc = this.$('#bcard');
      const bcBottom = bc ? Math.max(top, bc.offsetTop + bc.offsetHeight + 10) : top + 90;
      // a tall, narrow screen: let the spread parts run a little past the sides, so they stay big
      const over = w / h < 0.8 ? w * 0.09 : 0;
      L.whole = [14, top + 4, x1, capTop - 10];
      L.apart = [6 - over, top - 4, x1 + 6 + over, capTop - 2];
      L.focus = [16, bcBottom, x1 - 4, capTop - 10];
    }
    this._svL = L;
    const po = this.$('.sv-poster');             // the poster sits where the whole model will be, so the swap to 3D does not jump
    if (po) {
      const [a, b, c, d] = L.whole, s = Math.min(c - a, d - b);
      Object.assign(po.style, { left: `${Math.round((a + c - s) / 2)}px`, top: `${Math.round((b + d - s) / 2)}px`, width: `${Math.round(s)}px`, height: `${Math.round(s)}px` });
    }
    this._needs = true;
  }

  _scrollTarget() {
    const r = this.getBoundingClientRect();
    const total = r.height - this.$('.sv-sticky').offsetHeight;
    if (total <= 1) return 0;
    return clamp(((this._stickyTop || 0) - r.top) / total);
  }
  _explodeAmount(p) {
    const [a0, a1] = this._m.scroll.explodeAt, [b0, b1] = this._m.scroll.assembleAt;
    if (p <= a0) return 0;
    if (p < a1) return (p - a0) / (a1 - a0);
    if (p <= b0) return 1;
    if (p < b1) return 1 - (p - b0) / (b1 - b0);
    return 0;
  }

  /* what is emphasised right now: a part (hover or tap) > a card (hover, keyboard focus or click) > the story beat */
  _svState() {
    const hp = this._svPinPart || this._svHoverPart;
    if (hp) return { ids: [hp.id], level: 'part', card: this._partCard?.get(hp.id) || null };
    const c = this._svHoverCard || this._svFocusCard || this._svPinCard;
    if (c) return { ids: c.parts, level: 'card', card: c };
    const b = this._beatObj;
    if (b && this._beatLive) {
      const bc = this._beatCard;
      const ids = b.parts || bc?.parts || [];
      if (ids.length || bc) return { ids, level: 'beat', card: bc };
    }
    return { ids: [], level: null, card: null };
  }
  _svRefresh() {
    if (!this._cardEls) return;
    const st = this._svState();
    this._svSet = new Set(st.ids); this._svLevel = st.level;
    const cid = st.card?.id || null;
    if (cid !== this._activeCardId) {
      this._activeCardId = cid;
      for (const [id, li] of this._cardEls) {
        const on = id === cid;
        li.classList.toggle('on', on);
        li.querySelector('button').setAttribute('aria-expanded', String(on));
      }
      if (cid && st.level !== 'card') this._revealCard(cid);
    }
    this._needs = true;
    if (this._ready) this._loop();
  }
  _revealCard(cid) {
    const list = this.$('#cards'), li = this._cardEls?.get(cid);
    if (!li || !this._drawerOpen || performance.now() - (this._rowTouched ?? -1e9) < 2500) return;
    if (list.scrollHeight <= list.clientHeight + 2) return;
    const top = li.offsetTop - list.offsetTop;
    if (top < list.scrollTop || top + li.offsetHeight > list.scrollTop + list.clientHeight) {
      list.scrollTo({ top: Math.max(0, top - 12), behavior: this._reducedMotion() ? 'auto' : 'smooth' });
    }
  }

  _wireScrollPointer(canvas) {
    let down = null;
    canvas.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY, t: performance.now() }; });
    canvas.addEventListener('pointercancel', () => { down = null; });
    canvas.addEventListener('pointerup', (e) => {
      if (!down) return;
      const moved = Math.hypot(e.clientX - down.x, e.clientY - down.y);
      const quick = performance.now() - down.t < 600;
      down = null;
      if (moved > 8 || !quick) return;
      if (this._drawerOpen && this._stageW < 900) { this._setDrawer(false); return; }   // a tap above the sheet closes it
      this._svPinCard = null;
      this._svPin(this._pick(e));
    });
    canvas.addEventListener('pointermove', (e) => {
      if (e.pointerType !== 'mouse' || e.buttons) return;
      this._lastMove = e;
      if (this._hoverQueued) return;
      this._hoverQueued = true;
      requestAnimationFrame(() => { this._hoverQueued = false; const ev = this._lastMove; if (ev) this._svHover(this._pick(ev), ev); });
    });
    canvas.addEventListener('pointerleave', () => { this._lastMove = null; this._svHover(null); });
  }
  _svHover(p, e) {
    this.shadowRoot.querySelector('canvas').style.cursor = p ? 'pointer' : '';
    if (p !== this._svHoverPart) { this._svHoverPart = p; this._svRefresh(); }
    if (this._svPinPart) return;                 // a tapped part keeps its docked card
    if (p && e) this._showTip(p, false, e); else this._hideTip();
  }
  _svPin(p) {
    this._svPinPart = p || null;
    this._pinAt = performance.now();
    if (p) this._showTip(p, true); else this._hideTip();
    this._svRefresh();
    if (p) this._emit('partselect', { id: p.id, name: p.name, role: p.role, fact: p.fact });
  }
  _showTip(p, docked, e) {
    const tip = this.$('#tip');
    if (this._tipFor !== p.id) {
      this._tipFor = p.id;
      this.$('#tipBody').innerHTML = `<b>${esc(p.name)}</b>${p.role ? `<span class="sv-tip-role">${esc(p.role)}</span>` : ''}` +
        `${p.fact ? `<span class="sv-tip-fact">${esc(p.fact)}</span>` : ''}`;
    }
    tip.classList.toggle('docked', !!docked);
    this.toggleAttribute('data-tip', !!docked);
    if (docked) { tip.style.transform = ''; return; }
    const rect = this.$('.sv-stage').getBoundingClientRect();
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let x = e.clientX - rect.left + 18, y = e.clientY - rect.top + 18;
    if (x + w > rect.width - 10) x = e.clientX - rect.left - w - 14;
    if (y + h > rect.height - 10) y = e.clientY - rect.top - h - 14;
    tip.style.transform = `translate(${Math.round(Math.max(10, x))}px, ${Math.round(Math.max(10, y))}px)`;
  }
  _hideTip() {
    const tip = this.$('#tip');
    if (!tip) return;
    tip.classList.remove('docked');
    this.removeAttribute('data-tip');
    tip.style.transform = 'translate(-9999px, 0)';
  }

  _updateBeat(p, e, reduced) {
    const S = this._m.scroll;
    let i = -1;
    if (!reduced) { for (let k = 0; k < S.beats.length; k++) if (p >= S.beats[k].at - 1e-6) i = k; if (i < 0 && S.beats.length) i = 0; }
    if (i !== this._beatShown) {
      this._beatShown = i;
      const b = i >= 0 ? S.beats[i] : null;
      const show = reduced ? (S.static || S.beats[0] || {}) : (b || {});
      this.$('#beatKicker').textContent = S.kicker || '';
      this.$('#beatCount').textContent = !reduced && b ? `${i + 1} / ${S.beats.length}` : '';
      this.$('#beatTitle').textContent = show.title || '';
      this.$('#beatText').textContent = show.text || '';
      const el = this.$('#beat');
      el.classList.remove('in'); void el.offsetWidth; el.classList.add('in');
      this._beatObj = reduced ? null : b;
      this._beatCard = b?.card ? this._svCardById.get(b.card) || null : null;
      this._beatLive = null;
      (this._dotEls || []).forEach((d, k) => {
        d.classList.toggle('done', k < i);
        if (k === i) d.setAttribute('aria-current', 'step'); else d.removeAttribute('aria-current');
      });
      this._measureCaption();
      this._emit('beatchange', { index: i, title: show.title || '' });
    }
    const live = !reduced && i >= 0 && e > 0.985;      // a beat only lights its parts while he is fully apart
    if (live !== this._beatLive) { this._beatLive = live; this._svRefresh(); this._setBeatCard(live ? this._beatCard : null); }
  }
  /* the compact card for the beat's part group, beside the parts in focus */
  _setBeatCard(c) {
    const el = this.$('#bcard');
    if (c && this._bcardFor !== c.id) {
      this._bcardFor = c.id;
      this.$('#bTitle').textContent = c.title;
      this.$('#bText').textContent = c.text || '';
      this.$('#bFact').textContent = c.fact || '';
      this.$('#bFact').hidden = !c.fact;
      const url = this._thumbUrl?.get(c.id);
      this.$('#bThumb').innerHTML = url ? `<img src="${url}" alt="" width="64" height="64">` : '<i></i>';
    }
    el.classList.toggle('on', !!c);
    if (!this._svL?.wide) this._measureCaption();   // on phones the card sits above the model: re-fit below it
  }

  _glowColour() {
    const st = this.getAttribute('stage');
    if (st !== this._glowStage || !this._glowCol) {
      this._glowStage = st;
      const v = getComputedStyle(this).getPropertyValue('--sv-glow').trim() || '#d9956a';
      try { this._glowCol = new THREE.Color(v); } catch { this._glowCol = new THREE.Color('#d9956a'); }
    }
    return this._glowCol;
  }

  /* Fits the camera so the given parts (at their current offsets) fill the rect R (stage px), seen from
     direction dir (unit, from the model toward the camera). Exact for perspective: every box corner is checked.
     Returns { t: aim point, d: distance, cx, cy: where on the stage the aim point is drawn }. */
  _fitView(parts, dir, R, out) {
    const cam = this._camera, w = this._stageW || 1, h = this._stageH || 1;
    const tanV = Math.tan(THREE.MathUtils.degToRad(cam.fov) / 2), tanH = tanV * (w / h);
    const f = dir;
    const rt = (this._fv1 || (this._fv1 = new THREE.Vector3())).crossVectors(Y_AXIS, f).normalize();
    const up = (this._fv2 || (this._fv2 = new THREE.Vector3())).crossVectors(f, rt).normalize();
    const M = this._model.matrixWorld;
    const pts = this._fvPts || (this._fvPts = []);
    let n = 0;
    const c = (this._fv3 || (this._fv3 = new THREE.Vector3())).set(0, 0, 0);
    for (const p of parts) {
      if (!p.svCorners) continue;
      for (const k of p.svCorners) {
        const q = pts[n] || (pts[n] = new THREE.Vector3());
        q.copy(k).add(p.offset).applyMatrix4(M);
        c.add(q); n++;
      }
    }
    if (!n) return null;
    c.multiplyScalar(1 / n);
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (let i = 0; i < n; i++) {
      const q = pts[i];
      const dx = q.x - c.x, dy = q.y - c.y, dz = q.z - c.z;
      const x = dx * rt.x + dy * rt.y + dz * rt.z, y = dx * up.x + dy * up.y + dz * up.z;
      if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y;
    }
    const mx = (x0 + x1) / 2, my = (y0 + y1) / 2;
    c.addScaledVector(rt, mx).addScaledVector(up, my);
    const hx = Math.max(0.05, (R[2] - R[0]) / w), hy = Math.max(0.05, (R[3] - R[1]) / h);
    let d = 0;
    for (let i = 0; i < n; i++) {
      const q = pts[i];
      const dx = q.x - c.x, dy = q.y - c.y, dz = q.z - c.z;
      const x = dx * rt.x + dy * rt.y + dz * rt.z, y = dx * up.x + dy * up.y + dz * up.z, z = dx * f.x + dy * f.y + dz * f.z;
      const need = z + Math.max(Math.abs(x) / (tanH * hx), Math.abs(y) / (tanV * hy));
      if (need > d) d = need;
    }
    out = out || {};
    (out.t || (out.t = new THREE.Vector3())).copy(c);
    (out.dir || (out.dir = new THREE.Vector3())).copy(f);
    out.d = Math.max(d, this._radius * 0.2);
    out.cx = (R[0] + R[2]) / 2; out.cy = (R[1] + R[3]) / 2;
    return out;
  }

  _updateScroll(dt) {
    const S = this._m.scroll;
    const reduced = this._reducedMotion();
    if (reduced !== this._lastReduced) {          // also catches a change the media-query event did not report
      this._lastReduced = reduced;
      if (this.hasAttribute('data-reduced') !== reduced) this._applyReduced();
      this._scrollDirty = true;
    }
    let anim = false;
    if (this._scrollDirty || this._spTarget === undefined) {
      this._scrollDirty = false;
      this._spTarget = reduced ? (S.explodeAt[1] + S.assembleAt[0]) / 2 : this._scrollTarget();
    }
    const tgt = this._spTarget;
    // frame-rate independent follow: closes about 9/10 of the gap every quarter second, at any frame rate
    if (this._sp == null || reduced || dt <= 0) this._sp = tgt;
    else {
      const d = tgt - this._sp;
      if (Math.abs(d) < 2e-4) this._sp = tgt; else { this._sp += d * (1 - Math.exp(-dt * 9)); anim = true; }
    }
    const p = this._sp;
    const e = this._explodeAmount(p);
    this._updateBeat(p, e, reduced);
    // the progress rail fills from dot to dot
    if (this._progShown !== p) {
      this._progShown = p;
      const B = S.beats, nB = B.length;
      let f = 0;
      if (nB > 1) {
        let i = 0;
        for (let k = 0; k < nB; k++) if (p >= B[k].at) i = k;
        const a = B[i].at, b = B[i + 1]?.at;
        f = (i + (b != null && b > a ? clamp((p - a) / (b - a)) : 0)) / (nB - 1);
      }
      this.$('.sv-rail i').style.transform = `scaleY(${f.toFixed(4)})`;
    }
    const cueOn = !reduced && p < 0.02;
    if (cueOn !== this._cueOn) { this._cueOn = cueOn; this.$('#cue').classList.toggle('gone', !cueOn); }
    // which layer is coming off right now (a small pill above the caption)
    let lt = '';
    if (!reduced && S.layers.length && e > 0.002 && e < 0.995) {
      if (p <= S.explodeAt[1]) {
        let i = 0;
        this._svWin.forEach((wn, k) => { if (e >= wn.a) i = k; });
        lt = `${S.apartLabel} · ${S.layers[i].title}`;
      } else lt = S.togetherLabel;
    }
    if (lt !== this._layerShown) { this._layerShown = lt; const el = this.$('#layer'); el.textContent = lt; el.hidden = !lt; }

    // camera: a slow swing round as you scroll; fitted every frame so he fills the screen whole, the spread
    // parts fill it when apart, and each beat's parts are framed big beside the words
    const kf = easeInOut(e);
    const cams = this._m.cameras;
    const base = cams.find((c) => c.id === this._m.defaultCamera) || cams[0] || { dir: [1, 0.55, 1.4], zoom: 1 };
    const az = THREE.MathUtils.degToRad(reduced ? (S.sweep[0] + S.sweep[1]) / 2 : lerp(S.sweep[0], S.sweep[1], p));
    const dir = (this._svDir || (this._svDir = new THREE.Vector3())).set(...(base.dir || [1, 0.55, 1.4])).normalize();
    // on a tall, narrow screen look down a little more: the spread parts stack up the screen instead of across it
    // and swing round toward his side, where the explode is taller than it is wide
    const tall = (this._stageW || 1) / (this._stageH || 1) < 0.8;
    if (tall) { dir.y += 0.3 * kf; dir.normalize(); }
    dir.applyAxisAngle(Y_AXIS, az + (tall ? 0.5 * kf : 0));
    if (!this._svL) this._measureCaption();
    const L = this._svL;
    if (!L) return anim;
    const sw = this._stageW || 1, sh = this._stageH || 1;
    // the target rect (whole -> apart), smoothed so a caption that grows by a line never jolts the camera
    const Rt = this._svRt || (this._svRt = [0, 0, 0, 0]);
    for (let i = 0; i < 4; i++) Rt[i] = lerp(L.whole[i], L.apart[i], kf);
    if (!this._svRect || reduced || dt <= 0) this._svRect = Rt.slice();
    const Rs = this._svRect, kr = 1 - Math.exp(-dt * 6);
    for (let i = 0; i < 4; i++) {
      if (Math.abs(Rt[i] - Rs[i]) > 0.5 && !reduced && dt > 0) { Rs[i] += (Rt[i] - Rs[i]) * kr; anim = true; } else Rs[i] = Rt[i];
    }
    const A = this._fitView(this._parts, dir, Rs, this._fvA || (this._fvA = {}));
    if (!A) return anim;
    A.d *= base.zoom || 1;
    // focus framing for the live beat
    let F = null;
    if (this._beatLive) {
      const ids = this._beatObj?.parts || this._beatCard?.parts;
      if (ids?.length) {
        if (this._focusKey !== this._beatShown) {
          this._focusKey = this._beatShown;
          const set = new Set(ids);
          this._focusParts = this._parts.filter((q) => set.has(q.id));
        }
        const camId = this._beatObj?.camera || this._beatCard?.camera || null;
        // a beat's camera is a camera id from the manifest, or (1.3.0) a direction of its own, [x, y, z]
        const bc = Array.isArray(camId) ? { dir: camId } : camId ? cams.find((c) => c.id === camId) : null;
        const fdir = bc ? (this._svFd || (this._svFd = new THREE.Vector3())).set(...bc.dir).normalize().applyAxisAngle(Y_AXIS, az * 0.5) : dir;
        F = this._fitView(this._focusParts, fdir, L.focus, this._fvF || (this._fvF = {}));
        if (F) F.d = clamp(F.d, A.d * (this._beatObj?.focusMin ?? S.focusMin), A.d * 1.05);   // big, but never so close that you lose where it sits
      }
    }
    const mT = F ? 1 : 0;
    const mk = reduced || dt <= 0 ? 1 : 1 - Math.exp(-dt * 2.4);
    this._svCamMix = this._svCamMix ?? 0;
    if (Math.abs(this._svCamMix - mT) > 1e-3) { this._svCamMix += (mT - this._svCamMix) * mk; anim = true; } else this._svCamMix = mT;
    if (F) {
      const Fs = this._svFs;
      if (!Fs || this._svCamMix < 0.02 || mk === 1) {
        this._svFs = { t: F.t.clone(), dir: F.dir.clone(), d: F.d, cx: F.cx, cy: F.cy };
      } else {
        const moving = Fs.t.distanceTo(F.t) > this._radius * 1e-3 || Math.abs(Fs.d - F.d) > this._radius * 1e-3 || Fs.dir.distanceTo(F.dir) > 1e-3;
        Fs.t.lerp(F.t, mk); Fs.dir.lerp(F.dir, mk).normalize(); Fs.d = lerp(Fs.d, F.d, mk);
        Fs.cx = lerp(Fs.cx, F.cx, mk); Fs.cy = lerp(Fs.cy, F.cy, mk);
        if (moving) anim = true;
      }
    }
    const m = easeInOut(this._svCamMix), Fs = this._svFs;
    const T = (this._svT || (this._svT = new THREE.Vector3())).copy(A.t);
    const D = (this._svD || (this._svD = new THREE.Vector3())).copy(A.dir);
    let dist = A.d, cx = A.cx, cy = A.cy;
    if (Fs && m > 0) {
      T.lerp(Fs.t, m); D.lerp(Fs.dir, m).normalize();
      dist = lerp(A.d, Fs.d, m); cx = lerp(A.cx, Fs.cx, m); cy = lerp(A.cy, Fs.cy, m);
    }
    this._camera.position.copy(T).addScaledVector(D, dist);
    this._camera.lookAt(T);
    // draw the aim point at (cx, cy) on the stage: a shifted projection, so the model sits beside the words
    const ox = sw / 2 - cx, oy = sh / 2 - cy;
    const vk = this._viewOff;
    if (!vk || Math.abs(vk.ox - ox) > 0.05 || Math.abs(vk.oy - oy) > 0.05 || vk.w !== sw || vk.h !== sh) {
      this._viewOff = { ox, oy, w: sw, h: sh };
      this._camera.setViewOffset(sw, sh, ox, oy, sw, sh);
    }

    // the soft contact shadow belongs under him standing; it fades out as he comes apart
    if (this._shadow) { const so = 0.6 * (1 - kf); this._shadow.material.opacity = so; this._shadow.visible = so > 0.01; }

    // parts: layered explode, then the emphasis (lift + glow for the chosen part, everything else dims)
    const R = this._radius;
    const k = reduced || dt <= 0 ? 1 : 1 - Math.exp(-dt * 12);
    const set = this._svSet || new Set(), level = this._svLevel;
    const any = set.size > 0;
    const dimTo = level === 'beat' ? S.beatDim : S.dim;
    const glow = this._glowColour();
    const step = (cur, to) => (Math.abs(to - cur) < 1e-3 ? to : cur + (to - cur) * k);
    for (const part of this._parts) {
      const on = set.has(part.id);
      const gT = any && !on ? dimTo : 1, lT = on && level !== 'beat' ? 1 : 0, wT = on ? (level === 'beat' ? 0.3 : 0.4) : 0;
      const g0 = part.ghost, l0 = part.svLift, w0 = part.svGlow;
      part.ghost = step(g0, gT); part.svLift = step(l0, lT); part.svGlow = step(w0, wT);
      if (part.ghost !== gT || part.svLift !== lT || part.svGlow !== wT) anim = true;
      const win = this._svWin[part.svLayer] || this._svWin[0];
      part.offset.copy(part.svRest).multiplyScalar(easeInOut(clamp((e - win.a) / win.w)));
      for (const c of part.svCarry) { const cw = this._svWin[c.i]; part.offset.addScaledVector(c.by, easeInOut(clamp((e - cw.a) / cw.w))); }
      if (part.svLift > 0) part.offset.addScaledVector(part.explodeDir, 0.05 * R * easeOut(part.svLift));
      part.fade = 1;
      this._applyVisual(part, 1, part.ghost, part.svGlow, glow);
    }
    return anim;
  }

  /* 1.3.0: adaptive resolution for the full-screen canvas. The frame interval is sampled while it animates;
     if the median of a window says it is running under ~40 fps, the pixel ratio steps down (never below 0.8 of
     the cap); after a long smooth run it steps back up. Numbers are kept in this._perf for checking. */
  _perfTick(now, rendered) {
    const P = this._perf || (this._perf = { last: 0, win: [], log: [], steps: [], okWins: 0 });
    if (!rendered) { P.last = 0; return; }
    if (P.last) {
      const ft = now - P.last;
      if (ft < 250) { P.win.push(ft); P.log.push(+ft.toFixed(2)); if (P.log.length > 900) P.log.shift(); }
    }
    P.last = now;
    if (P.win.length < 40) return;
    const sorted = P.win.slice().sort((a, b) => a - b), med = sorted[sorted.length >> 1];
    P.win.length = 0;
    const s0 = this._prScale ?? 1;
    this._prScale = s0;
    if (med > 24 && s0 > 0.62) {
      this._prScale = Math.max(0.6, s0 - 0.15); P.okWins = 0;
    } else if (med < 13.5 && s0 < 1) {
      if (++P.okWins >= 5) { this._prScale = Math.min(1, s0 + 0.1); P.okWins = 0; }
    } else P.okWins = 0;
    if (this._prScale !== s0) {
      P.steps.push({ at: Math.round(now), median: +med.toFixed(1), scale: +this._prScale.toFixed(2) });
      this._applyPixelRatio();
    }
  }
  _applyPixelRatio() {
    if (!this._renderer || !this._stageW) return;
    const pr = Math.max(Math.min(1, this._prCap) * 0.8, this._prCap * (this._prScale ?? 1));
    if (Math.abs(this._renderer.getPixelRatio() - pr) < 1e-3) return;
    this._renderer.setPixelRatio(pr);
    this._renderer.setSize(this._stageW, this._stageH, false);
    this._needs = true;
  }

  /* ---------- render loop (renders only when something changed; pauses off screen) ---------- */
  _loop() {
    if (this._running || !this._renderer) return;
    this._running = true;
    this._clock.getDelta();
    const frame = () => {
      if (!this._renderer || !this._visible || document.hidden || !this.isConnected) { this._running = false; return; }
      const dt = Math.min(0.05, this._clock.getDelta());
      const anim = this._update(dt, this._clock.getElapsedTime());
      const draw = anim || this._needs;
      if (draw) {
        this._needs = false;
        this._renderer.render(this._scene, this._camera);
      }
      if (this._scrollMode) this._perfTick(performance.now(), draw);
      this._raf = requestAnimationFrame(frame);
    };
    this._raf = requestAnimationFrame(frame);
  }
}

if (!customElements.get('exploded-view')) customElements.define('exploded-view', ExplodedView);
export default ExplodedView;
export { VERSION };
