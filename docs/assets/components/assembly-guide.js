/* assembly-guide.js - renders a guidekit guide (window.ASSEMBLY_GUIDE) as a phone bench page or a print page.
 * Made by Nur Ifran Arpon / SpaceZ. No framework, no build step.
 *
 * Page contract:
 *   <div id="ag-root"></div>
 *   <script>window.AG_BASE = 'assets/guide/';</script>     (where img/ and placements.json live; '' for same folder)
 *   <script src=".../spike-guide-data.js"></script>          (sets window.ASSEMBLY_GUIDE)
 *   <script src=".../assembly-guide.js" defer></script>
 * Print mode: window.AG_PRINT = true, or ?print=1 in the URL. Everything is expanded, no buttons.
 * Ticks and the last step you looked at are kept in localStorage (wrapped in try/catch: a private window
 * or blocked storage just means nothing is remembered).
 */
(function () {
  'use strict';
  const G = window.ASSEMBLY_GUIDE;
  const root = document.getElementById('ag-root');
  if (!G || !root) { if (root) root.textContent = 'The guide data did not load.'; return; }
  const BASE = window.AG_BASE || '';
  const PRINT = !!window.AG_PRINT || /[?&]print=1/.test(location.search);
  const KEY = 'ag:' + (G.storage_key || G.product || 'guide');
  document.documentElement.classList.toggle('ag-print', PRINT);

  /* ---------- storage (never throws) ---------- */
  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  function save(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* storage blocked: fine */ } }
  let state = load();
  state.done = state.done || {};

  /* ---------- tiny DOM helper ---------- */
  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    if (attrs) for (const k in attrs) {
      const v = attrs[k];
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') n.className = v;
      else if (k === 'html') n.innerHTML = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? '' : v);
    }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) n.append(c.nodeType ? c : document.createTextNode(c));
    return n;
  }
  const WIRE = { red: '#d62828', black: '#2b2b2b', orange: '#f08a24', yellow: '#e3b505', blue: '#1d6fd8', green: '#2a9d8f',
    white: '#cfcfcf', purple: '#7b2cbf', grey: '#8d99ae', brown: '#8b5a2b', pink: '#e07aa8' };

  /* ---------- pieces ---------- */
  /* small line icons for parts without a photo (24 x 24, stroke = currentColor) */
  const ICONS = {
    magnet: '<path d="M6 4v8a6 6 0 0 0 12 0V4"/><path d="M6 4h4v8a2 2 0 0 0 4 0V4h4"/><path d="M6 8h4M14 8h4"/>',
    wire: '<path d="M3 17c4 0 4-10 9-10s5 10 9 10"/><circle cx="3" cy="17" r="1.6"/><circle cx="21" cy="17" r="1.6"/>',
    screw: '<path d="M8 4h8l-1 3H9z"/><path d="M12 7v13"/><path d="M9.5 10l5 1.5M9.5 13l5 1.5M9.5 16l5 1.5"/>',
    meter: '<rect x="5" y="2.5" width="14" height="19" rx="2"/><rect x="8" y="5.5" width="8" height="4" rx="1"/><circle cx="12" cy="15" r="3"/><path d="M12 15l1.6-1.6"/>',
    battery: '<rect x="7" y="4" width="10" height="17" rx="2"/><path d="M10 2.5h4"/><path d="M12 8v4M10 10h4"/>',
    tape: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/><path d="M20 12h2"/>',
    laptop: '<rect x="5" y="5" width="14" height="10" rx="1.5"/><path d="M2.5 18.5h19"/>',
    pins: '<path d="M4 15h16"/><path d="M6 15V6M10 15V6M14 15V6M18 15V6"/><path d="M6 15v4M10 15v4M14 15v4M18 15v4"/>',
    cutters: '<path d="M8 3l3 9M16 3l-3 9"/><circle cx="8" cy="17" r="3"/><circle cx="16" cy="17" r="3"/><path d="M11 12l-1.5 2.5M13 12l1.5 2.5"/>',
    resistor: '<path d="M2 12h4l1.5-3 3 6 3-6 3 6 1.5-3h4"/>',
    capacitor: '<path d="M2 12h8M14 12h8"/><path d="M10 6v12M14 6v12"/>',
    diode: '<path d="M2 12h20"/><path d="M8 6l8 6-8 6z"/><path d="M16 6v12"/>',
    compass: '<circle cx="12" cy="12" r="9"/><path d="M14.5 9.5L10 14l-.5-4.5z"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2"/>',
    scale: '<path d="M4 20h16l-2-9H6z"/><path d="M12 11V6"/><path d="M8 6h8"/>',
    bar: '<rect x="2.5" y="9" width="19" height="6" rx="1"/><path d="M7 9v6M17 9v6"/>',
    saw: '<path d="M3 15l12-12 3 3-12 12z"/><path d="M15 3l5 5-3 3"/><path d="M6 15l1 1M8 13l1 1M10 11l1 1M12 9l1 1"/>',
    glue: '<rect x="8" y="9" width="8" height="12" rx="2"/><path d="M10 9V6h4v3"/><path d="M12 6V3"/>',
    tie: '<path d="M4 18c0-8 16-8 16 0"/><rect x="9" y="15" width="6" height="5" rx="1"/>',
    foil: '<path d="M4 6h12l4 4v8H4z"/><path d="M16 6v4h4"/>',
    pin: '<path d="M10 3h4v14l-2 4-2-4z"/>',
    usb: '<rect x="6" y="8" width="12" height="8" rx="4"/><path d="M9 12h6"/>',
    fuse: '<rect x="6" y="8" width="12" height="8" rx="2"/><path d="M2 12h4M18 12h4M9 12c1-2 2 2 3 0s2 2 3 0"/>',
    board: '<rect x="4" y="6" width="16" height="12" rx="1.5"/><circle cx="8" cy="10" r="1"/><circle cx="12" cy="10" r="1"/><circle cx="16" cy="10" r="1"/><circle cx="8" cy="14" r="1"/><circle cx="12" cy="14" r="1"/><circle cx="16" cy="14" r="1"/>',
    ring: '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="4.5"/>',
    printer: '<path d="M6 3h12v6H6z"/><path d="M4 9h16v8H4z"/><path d="M8 17h8v4H8z"/>',
    caliper: '<path d="M4 4h16v4H4z"/><path d="M6 8v10l2 2V8M16 8v12"/>',
    part: '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/>',
  };
  function icon(name) {
    const d = ICONS[name] || ICONS.part;
    return el('span', { class: 'ag-icon', 'aria-hidden': 'true', html: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${d}</svg>` });
  }
  function sourceLine(info) {
    if (info.kind === 'printed') return 'Printed part: ' + (info.listing || 'see the print list');
    if (info.kind === 'home') return 'From home';
    if (info.made) return 'You make it from ' + info.made;
    if (info.from) return 'From ' + info.from;
    const shop = [info.shop, info.code].filter(Boolean).join(' \u00b7 ');
    if (info.buy) return 'To buy' + (shop ? ' \u00b7 ' + shop : '') + ': ' + info.buy;
    if (info.listing) return (shop ? shop + ': ' : '') + '\u201c' + info.listing + '\u201d';
    return shop || null;
  }

  function partsList(st) {
    if (!st.parts || !st.parts.length) return null;
    const ul = el('ul', { class: 'ag-parts' });
    for (const p of st.parts) {
      const info = G.parts[p.key] || { name: p.key };
      const pic = info.photo
        ? el('img', { src: BASE + (PRINT && info.photo_print ? info.photo_print : info.photo), alt: info.name, loading: 'lazy', width: 64, height: 64, class: info.kind === 'printed' ? 'ag-thumb' : null })
        : icon(info.icon);
      const nameNode = info.link && !PRINT ? el('a', { href: info.link, target: '_blank', rel: 'noopener' }, info.name) : info.name;
      const src = sourceLine(info);
      ul.append(el('li', null, pic, el('div', { class: 'ag-pinfo' },
        el('div', { class: 'ag-pname' }, el('b', { class: 'ag-qty' }, p.qty + ' \u00d7 '), nameNode),
        p.note ? el('div', { class: 'ag-pnote' }, p.note) : null,
        src ? el('div', { class: 'ag-listing' + (info.buy ? ' ag-tobuy' : '') }, src) : null)));
    }
    return el('section', { class: 'ag-block' }, el('h4', null, 'You need'), ul,
      st.tools && st.tools.length ? el('p', { class: 'ag-tools' }, 'Also: ' + st.tools.join(' \u00b7 ')) : null);
  }

  function pictures(st) {
    if (!st.pictures || !st.pictures.length) return null;
    const box = el('section', { class: 'ag-pics' });
    for (const pic of st.pictures) {
      if (pic.kind === 'svg') {
        const fig = el('figure', { class: 'ag-fig ag-fig-svg' });
        fig.append(...[el('div', { class: 'ag-svgwrap', html: pic.svg }),
          (parseFloat((pic.svg.match(/width="([\d.]+)"/) || [])[1]) || 0) > 400 ? el('p', { class: 'ag-swipe' }, '↔ Swipe the picture sideways to see every board.') : null,
          pic.caption ? el('figcaption', null, pic.caption) : null].filter(Boolean));
        box.append(fig);
      } else if (pic.kind === 'photo' || pic.kind === 'render') {
        const wrap = el('div', { class: 'ag-photo' }, el('img', { src: BASE + pic.src, alt: pic.caption || '', loading: 'lazy' }));
        for (const a of pic.arrows || []) {
          wrap.append(el('span', { class: 'ag-arrow', style: `left:${a[0]}%;top:${a[1]}%` }, el('i', { 'aria-hidden': 'true' }), el('b', null, a[2])));
        }
        box.append(el('figure', { class: 'ag-fig' }, wrap, el('figcaption', null, pic.caption || '',
          pic.needs_rerender ? el('span', { class: 'ag-flag' }, ' ' + (pic.rerender_note || 'Picture to be re-rendered.')) : null)));
      } else if (pic.kind === 'placeholder') {
        box.append(el('figure', { class: 'ag-fig ag-ph' }, el('div', null, pic.text || 'Picture to come'), el('figcaption', null, pic.caption || '')));
      }
    }
    return box;
  }

  function flow(st) {
    const ol = el('ol', { class: 'ag-flow' });
    st.flow.forEach((f, i) => {
      if (i) ol.append(el('li', { class: 'ag-down', 'aria-hidden': 'true' }, '↓'));
      ol.append(el('li', { class: 'ag-line ag-k-' + f.kind },
        el('span', { class: 'ag-n' }, String(f.n)),
        el('span', { class: 'ag-t' }, f.text, f.sub ? el('small', null, f.sub) : null)));
    });
    return el('section', { class: 'ag-block' }, el('h4', null, 'Do this, top to bottom'), ol);
  }

  function expect(st) {
    if (!st.expect.length && !(st.record || []).length) return null;
    const ul = el('ul', { class: 'ag-expect' });
    for (const e of st.expect) {
      ul.append(el('li', null, e.meter ? el('span', { class: 'ag-meter' }, e.text + ' ') : null,
        el('b', null, 'Expect: '), e.meter ? e.want : (e.want ? e.text + ' ' + e.want : e.text)));
    }
    const rec = (st.record || []).length ? el('div', { class: 'ag-record' }, el('b', null, 'Write down: '),
      ...st.record.map((r) => el('span', null, r))) : null;
    return el('section', { class: 'ag-block ag-expectbox' }, el('h4', null, 'Check before you go on'), ul, rec);
  }

  function ledger(st) {
    if (!st.ledger.length) return null;
    const added = new Set(st.added);
    const tb = el('tbody');
    const rows = PRINT && !st._full ? st.ledger.filter((r) => r.since === st.id) : st.ledger;   // print: only this step's rows
    if (!rows.length) return null;
    for (const r of rows) {
      const sw = r.colour ? el('i', { class: 'ag-sw', style: 'background:' + (WIRE[r.colour] || r.colour) }) : null;
      tb.append(el('tr', { class: added.has(r.loc) ? 'ag-new' : null },
        el('td', { 'data-l': 'Where' }, r.where), el('td', { 'data-l': 'What' }, el('span', null, sw, r.what)),
        el('td', { 'data-l': 'Other end', class: r.to ? null : 'ag-empty' }, r.to || ''), el('td', { class: 'ag-since', 'data-l': 'Step' }, r.since)));
    }
    const table = el('table', { class: 'ag-ledger' }, el('thead', null, el('tr', null, el('th', null, 'Where'), el('th', null, 'What is in it'), el('th', null, 'Other end'), el('th', null, 'Step'))), tb);
    const removed = st.removed.length ? el('p', { class: 'ag-removed' }, 'Taken out in this step: ' + st.removed.length + ' place(s) now empty.') : null;
    const body = el('div', { class: 'ag-ledgerwrap' }, table);
    if (PRINT) return el('section', { class: 'ag-block ag-where' }, el('h4', null, st._full ? st._full : 'Placed in this step (' + st.id + ')'), body, removed);
    return el('details', { class: 'ag-block ag-where' },
      el('summary', null, 'What’s where now ', el('span', { class: 'ag-count' }, st.ledger.length + ' places')), body, removed);
  }

  function seeItMove(st) {
    if (!st.see_it_move || !G.see_it_move_url) return null;
    const url = G.see_it_move_url.replace('{n}', st.see_it_move);
    const where = 'Inside Spike, step ' + st.see_it_move + (st.see_it_move_title ? ': ' + st.see_it_move_title : '');
    if (PRINT) {
      const purl = (G.see_it_move_print || G.see_it_move_url).replace('{n}', st.see_it_move);
      return el('p', { class: 'ag-move-print' }, 'See it move (' + where + '): ' + purl);
    }
    return el('div', { class: 'ag-move' },
      el('a', { class: 'ag-btn ag-btn-move', href: url, target: '_blank', rel: 'noopener' }, el('span', { 'aria-hidden': 'true' }, '▶'), ' See it move'),
      el('span', { class: 'ag-move-where' }, where));
  }

  function stepCard(st, idx, total) {
    const done = !!state.done[st.id];
    const box = el('input', { type: 'checkbox', id: 'tick-' + st.id, class: 'ag-tickbox', checked: done || null,
      onchange: (e) => { setDone(st.id, e.target.checked); } });
    const head = el('header', { class: 'ag-head' },
      el('span', { class: 'ag-id' }, st.id),
      el('h3', null, st.title),
      el('div', { class: 'ag-meta' }, st.time ? el('span', { class: 'ag-chip' }, '⏱ ' + st.time) : null,
        el('span', { class: 'ag-chip ag-chip-muted' }, 'Step ' + (idx + 1) + ' of ' + total)),
      el('label', { class: 'ag-tick', for: 'tick-' + st.id }, box, el('span', null, 'Done')));
    const card = el('article', { class: 'ag-step' + (done ? ' is-done' : ''), id: 'step-' + st.id, 'data-step': st.id },
      head,
      st.why ? el('p', { class: 'ag-why' }, st.why) : null,
      el('div', { class: 'ag-body' },
        el('div', { class: 'ag-col-text' }, partsList(st), flow(st), expect(st),
          st.mistake ? el('p', { class: 'ag-warn' }, el('b', null, '⚠ Common mistake: '), st.mistake) : null,
          st.stop ? el('p', { class: 'ag-stop' }, el('b', null, '✋ Stop rule: '), st.stop) : null,
          (st.ifsee || []).length ? el('div', { class: 'ag-ifsee' }, el('h4', null, 'If you see…'),
            ...st.ifsee.map((r) => el('div', { class: 'ag-if-row' }, el('p', { class: 'ag-if-see' }, r[0]),
              el('p', { class: 'ag-if-do' }, el('b', null, '→ '), r[1])))) : null,
          st.note ? el('p', { class: 'ag-note' }, st.note) : null,
          el('div', { class: 'ag-actions' }, seeItMove(st))),
        el('div', { class: 'ag-col-pic' }, pictures(st))),
      ledger(st));
    return card;
  }

  /* ---------- progress, ticks, resume ---------- */
  const steps = G.steps;
  let bar, count;
  function setDone(id, on) {
    if (on) state.done[id] = new Date().toISOString(); else delete state.done[id];
    state.last = id;
    save(state);
    const c = document.getElementById('step-' + id);
    if (c) c.classList.toggle('is-done', on);
    progress();
  }
  function progress() {
    if (!bar) return;
    const n = steps.filter((s) => state.done[s.id]).length;
    bar.style.width = (100 * n / steps.length).toFixed(1) + '%';
    count.textContent = n + ' of ' + steps.length + ' steps done';
  }
  function resume() {
    const next = steps.find((s) => !state.done[s.id]) || steps[steps.length - 1];
    const c = document.getElementById('step-' + next.id);
    if (c) { c.scrollIntoView({ behavior: 'smooth', block: 'start' }); c.classList.add('is-flash'); setTimeout(() => c.classList.remove('is-flash'), 1600); }
  }

  /* ---------- page ---------- */
  const top = el('div', { class: 'ag-top' },
    el('p', { class: 'ag-kicker' }, G.version || ''),
    el('h1', { class: 'ag-title' }, G.title || 'Build guide'),
    G.subtitle ? el('p', { class: 'ag-sub' }, G.subtitle) : null);
  root.append(top);
  if (!PRINT) {
    bar = el('i');
    count = el('span', { class: 'ag-count' });
    root.append(el('div', { class: 'ag-progress', role: 'group', 'aria-label': 'Progress' },
      el('div', { class: 'ag-bar' }, bar), count,
      el('button', { type: 'button', class: 'ag-btn ag-btn-primary', onclick: resume }, 'Resume where I stopped')));
    root.append(el('div', { class: 'ag-tools-row' },
      G.placements_url ? el('a', { class: 'ag-btn', href: BASE + G.placements_url.replace(/^.*\//, ''), download: 'placements.json' }, 'Download placements.json') : null,
      el('button', { type: 'button', class: 'ag-btn ag-btn-quiet', onclick: () => {
        if (confirm('Clear every tick on this device?')) { state = { done: {} }; save(state); document.querySelectorAll('.ag-tickbox').forEach((b) => { b.checked = false; }); document.querySelectorAll('.ag-step').forEach((c) => c.classList.remove('is-done')); progress(); }
      } }, 'Clear ticks')));
  }
  if (G.rules && G.rules.length) {
    root.append(el('section', { class: 'ag-rules' }, el('h2', null, G.rules_title || 'Rules that never change'),
      el('ol', null, G.rules.map((r) => el('li', null, r)))));
  }
  if (G.how_to_read) root.append(el('section', { class: 'ag-howto' }, el('h2', null, 'How each step works'), el('ul', null, G.how_to_read.map((r) => el('li', null, r)))));

  const total = steps.length;
  for (const ph of G.phases || []) {
    const sec = el('section', { class: 'ag-phase', id: 'phase-' + ph.id }, el('h2', { class: 'ag-phase-title' }, ph.title), ph.intro ? el('p', { class: 'ag-phase-intro' }, ph.intro) : null);
    if (ph.placeholder) {
      sec.append(el('div', { class: 'ag-coming' }, el('p', null, el('b', null, ph.placeholder.title)), el('ul', null, (ph.placeholder.items || []).map((t) => el('li', null, t)))));
    }
    steps.forEach((st, i) => { if (st.phase === ph.id) sec.append(stepCard(st, i, total)); });
    root.append(sec);
  }
  if (PRINT && steps.length) {
    const last = Object.assign({}, steps[steps.length - 1], { _full: 'Everything on the bench after step ' + steps[steps.length - 1].id, removed: [] });
    root.append(el('section', { class: 'ag-phase ag-appendix' }, el('h2', { class: 'ag-phase-title' }, 'Appendix · What’s where at the end'),
      el('p', { class: 'ag-phase-intro' }, 'Every hole, pin, pad and screw terminal in use after the last bench step. The same list is in placements.json.'),
      ledger(last)));
  }
  root.append(el('footer', { class: 'ag-foot' }, 'Generated ' + G.generated.replace('T', ' ') + ' by guidekit ' + G.engine + '. One data source: the web page, the PDF and placements.json all come from it.'));
  progress();

  if (!PRINT && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver((ents) => {
      for (const e of ents) if (e.isIntersecting) { state.seen = e.target.dataset.step; save(state); }
    }, { rootMargin: '-40% 0px -55% 0px' });
    document.querySelectorAll('.ag-step').forEach((c) => io.observe(c));
  }
  if (!PRINT && location.hash && location.hash.startsWith('#step-')) {
    const c = document.getElementById(location.hash.slice(1));
    if (c) setTimeout(() => c.scrollIntoView(), 50);
  }
  window.AG_READY = true;
}());
