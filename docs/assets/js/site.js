/* Spike website - small, dependency-free behaviour for every page.
   Content that changes often lives in data/site.json and data/updates.json (see UPDATING.md). */
(function () {
  "use strict";
  var doc = document.documentElement;
  doc.classList.remove("no-js");
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function getJSON(url) { return fetch(url, { cache: "no-cache" }).then(function (r) { if (!r.ok) throw new Error(url + " " + r.status); return r.json(); }); }

  /* ---- header: hairline on scroll, mobile menu ---- */
  var header = $(".site-header");
  if (header) {
    var onScroll = function () { header.classList.toggle("is-scrolled", window.scrollY > 8); };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    var btn = $(".menu-btn", header);
    if (btn) {
      btn.addEventListener("click", function () {
        var open = header.classList.toggle("menu-open");
        btn.setAttribute("aria-expanded", String(open));
        btn.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      });
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && header.classList.contains("menu-open")) { header.classList.remove("menu-open"); btn.setAttribute("aria-expanded", "false"); btn.focus(); }
      });
    }
  }

  /* ---- reveal on scroll ---- */
  function watchReveals() {
    var els = $all(".reveal:not(.is-in)");
    if (reduceMotion || !("IntersectionObserver" in window)) { els.forEach(function (el) { el.classList.add("is-in"); }); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("is-in"); io.unobserve(en.target); } });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.08 });
    els.forEach(function (el) { io.observe(el); });
  }
  watchReveals();

  /* ---- stage: Face / Asleep / Off ---- */
  $all("[data-stage]").forEach(function (stage) {
    var imgs = $all(".stage-img", stage);
    $all(".stage-controls button", stage).forEach(function (b) {
      b.addEventListener("click", function () {
        var want = b.getAttribute("data-show");
        imgs.forEach(function (img) { img.classList.toggle("is-hidden", img.getAttribute("data-state") !== want); });
        $all(".stage-controls button", stage).forEach(function (o) { o.setAttribute("aria-pressed", String(o === b)); });
      });
    });
  });

  /* ---- gallery tabs (The App) ---- */
  $all("[data-gallery]").forEach(function (g) {
    var tabs = $all('[role="tab"]', g);
    function select(t, focus) {
      tabs.forEach(function (o) {
        var on = o === t;
        o.setAttribute("aria-selected", String(on));
        o.tabIndex = on ? 0 : -1;
        var p = document.getElementById(o.getAttribute("aria-controls"));
        if (p) p.hidden = !on;
      });
      if (focus) t.focus();
    }
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { select(t); });
      t.addEventListener("keydown", function (e) {
        var n = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (n) { e.preventDefault(); select(tabs[(i + n + tabs.length) % tabs.length], true); }
      });
    });
  });

  /* ---- interactive 3D: loads only when asked (it is 1.5 MB) ---- */
  $all("[data-viewer3d]").forEach(function (box) {
    var b = $(".load3d", box);
    if (!b) return;
    b.addEventListener("click", function () {
      var f = document.createElement("iframe");
      f.src = box.getAttribute("data-viewer3d");
      f.title = "Spike in 3D: drag to turn him, pinch or scroll to zoom";
      f.setAttribute("allow", "fullscreen");
      box.appendChild(f);
      box.classList.add("is-live");
      f.addEventListener("load", function () { try { f.focus(); } catch (e) { /* ignore */ } });
    });
  });

  /* ---- data: names, links, statuses ---- */
  var siteData = getJSON("data/site.json").then(function (d) {
    $all("[data-brand]").forEach(function (el) { var v = d.brand[el.getAttribute("data-brand")]; if (v) el.textContent = v; });
    $all("[data-link]").forEach(function (el) { var v = d.links[el.getAttribute("data-link")]; if (v) el.setAttribute("href", v); });
    $all("[data-status]").forEach(function (el) {
      var s = d.status[el.getAttribute("data-status")];
      if (!s) return;
      el.textContent = s.label;
      el.className = el.className.replace(/\bpill--\w+/g, "").trim() + " pill--" + s.state;
    });
    $all("[data-version]").forEach(function (el) { var s = d.status[el.getAttribute("data-version")]; if (s && s.version) el.textContent = s.version; });
    var build = $("#robot-build");
    if (build && d.robotBuild) {
      build.style.setProperty("--n", d.robotBuild.length);
      build.innerHTML = d.robotBuild.map(function (s) {
        var label = s.state === "done" ? "Done" : s.state === "now" ? "Now" : "Next";
        return '<li class="' + esc(s.state) + '"><div><h3>' + esc(s.title) + '<span class="sr-only"> (' + label + ')</span></h3><p>' + esc(s.text) + "</p></div></li>";
      }).join("");
    }
    return d;
  }).catch(function () { /* the static text in the page stays */ });

  /* ---- data: updates ---- */
  var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  function fmt(iso) { var p = iso.split("-"); return +p[2] + " " + months[+p[1] - 1] + " " + p[0]; }
  var listEl = $("#updates-list"), latestEl = $("#latest-updates");
  if (listEl || latestEl) {
    getJSON("data/updates.json").then(function (d) {
      var items = (d.updates || []).slice().sort(function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : 0; });
      if (latestEl) {
        latestEl.innerHTML = items.slice(0, 3).map(function (u) {
          var href = u.link || "updates.html";
          return '<a class="card card--link reveal" href="' + esc(href) + '"><div class="card-top"><span class="tag">' + esc(u.tag) + '</span><time datetime="' + esc(u.date) + '">' + fmt(u.date) + '</time></div><h3 class="h3">' + esc(u.title) + "</h3><p>" + esc(u.text) + "</p></a>";
        }).join("");
      }
      if (listEl) {
        var render = function (tag) {
          listEl.innerHTML = items.filter(function (u) { return !tag || u.tag === tag; }).map(function (u) {
            var more = u.link ? '<a class="more" href="' + esc(u.link) + '">' + esc(u.linkText || "Read more") + " &rarr;</a>" : "";
            return '<li class="update reveal"><div class="update-meta"><time datetime="' + esc(u.date) + '">' + fmt(u.date) + '</time><span class="tag">' + esc(u.tag) + '</span></div><h3>' + esc(u.title) + "</h3><p>" + esc(u.text) + "</p>" + more + "</li>";
          }).join("");
          watchReveals();
        };
        var filters = $("#update-filters");
        if (filters) {
          var tags = [];
          items.forEach(function (u) { if (tags.indexOf(u.tag) < 0) tags.push(u.tag); });
          filters.innerHTML = '<button type="button" aria-pressed="true" data-tag="">All</button>' + tags.map(function (t) { return '<button type="button" aria-pressed="false" data-tag="' + esc(t) + '">' + esc(t) + "</button>"; }).join("");
          filters.addEventListener("click", function (e) {
            var b = e.target.closest("button"); if (!b) return;
            $all("button", filters).forEach(function (o) { o.setAttribute("aria-pressed", String(o === b)); });
            render(b.getAttribute("data-tag"));
          });
        }
        render("");
      }
      watchReveals();
    }).catch(function () {
      var msg = '<p class="muted">Updates could not be loaded. They are also listed in <a href="data/updates.json">data/updates.json</a>.</p>';
      if (listEl) listEl.outerHTML = msg;
      if (latestEl) latestEl.outerHTML = msg;
    });
  }

  /* ---- footer year ---- */
  $all("[data-year]").forEach(function (el) { el.textContent = String(new Date().getFullYear()); });
  void siteData;
})();
