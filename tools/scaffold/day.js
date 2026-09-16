/* =====================================================================
   The day — scroll-driven scrub engine.

   SCENES is injected by tools/build_scaffold.py from the data layer.
   Each scene owns a stretch of scroll travel; that travel scrubs its own
   clip forward and back. Scroll down it plays, scroll up it reverses,
   stop and it holds.

   Swapping placeholder motion for real footage is a DATA change:
   give a scene a `media` block and makeSource() returns a real source.
        media:{kind:"frames", pattern:"scenes/03/%d.webp", frames:56}
        media:{kind:"video",  src:"scenes/03.mp4", fps:24, frames:56}
   Nothing below this comment needs to change when the footage lands.
   ===================================================================== */
(function () {
  "use strict";

  var S = window.__SCENES__;
  var PPF = 20;                     // px of scroll per clip frame
  var RM = matchMedia("(prefers-reduced-motion: reduce)");

  /* ------------------------------------------------------------ colour */
  function hex(c) {
    return [parseInt(c.slice(1, 3), 16), parseInt(c.slice(3, 5), 16), parseInt(c.slice(5, 7), 16)];
  }
  function mix(a, b, t) {
    var x = hex(a), y = hex(b), o = "#";
    for (var i = 0; i < 3; i++) {
      var v = Math.round(x[i] + (y[i] - x[i]) * t);
      o += (v < 16 ? "0" : "") + v.toString(16);
    }
    return o;
  }
  function lum(c) {
    var v = hex(c).map(function (n) {
      n /= 255;
      return n <= 0.03928 ? n / 12.92 : Math.pow((n + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2];
  }
  function clock(min) {
    var m = Math.round(min), h = Math.floor(m / 60) % 24;
    m = m % 60;
    return (h < 10 ? "0" : "") + h + ":" + (m < 10 ? "0" : "") + m;
  }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }

  /* ================================================================== */
  /*  CLIP SOURCES — one interface, three implementations.              */
  /*                                                                    */
  /*    .frames                 how many frames the clip holds          */
  /*    .state                  idle | loading | ready | error          */
  /*    .load()   -> Promise    idempotent; the loader calls this       */
  /*    .draw(ctx,i,w,h) -> bool  paint frame i; false = not ready yet  */
  /*                                                                    */
  /*  A source NEVER blocks paint. When it returns false the engine     */
  /*  paints the flat day colour underneath, so a scene that has not    */
  /*  arrived still reads as the right hour.                            */
  /* ================================================================== */

  function cover(ctx, src, w, h) {
    var sw = src.videoWidth || src.width, sh = src.videoHeight || src.height;
    if (!sw || !sh) return false;
    var s = Math.max(w / sw, h / sh), dw = sw * s, dh = sh * s;
    ctx.drawImage(src, (w - dw) / 2, (h - dh) / 2, dw, dh);
    return true;
  }

  /* -- placeholder: flat colour through the day + the frame it is on -- */
  function PlaceholderSource(sc) {
    this.sc = sc; this.frames = sc.frames; this.state = "idle";
  }
  PlaceholderSource.prototype.load = function () {
    this.state = "ready";
    return Promise.resolve();
  };
  PlaceholderSource.prototype.draw = function (ctx, i, w, h) {
    var sc = this.sc, p = sc.frames > 1 ? i / (sc.frames - 1) : 0;
    var col = mix(sc.c0, sc.c1, p);
    ctx.fillStyle = col;
    ctx.fillRect(0, 0, w, h);

    /* A leader, not a debug overlay. The page type scrolls straight over
       the film, so this stays faint on purpose — the exact frame is read
       from the bar, which nothing ever covers. */
    var d = lum(col) < 0.42 ? "242,239,233" : "20,22,29";
    var acc = lum(col) < 0.42 ? "255,211,106" : "140,47,18";
    var wide = w >= 900;
    var x = wide ? 40 : 20;
    var y = Math.round(h * 0.17);
    var strip = Math.min(w - x * 2, wide ? 380 : 300);

    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = "rgba(" + d + ",.30)";
    ctx.font = '600 11px ui-monospace,"SFMono-Regular",Menlo,monospace';
    ctx.fillText("SCENE " + sc.n + "  \u00b7  " + sc.key.toUpperCase() + "  \u00b7  PLACEHOLDER", x, y);

    var big = wide ? 152 : 116;
    var base = y + big * 0.82;
    ctx.fillStyle = "rgba(" + d + ",.22)";
    ctx.font = '300 ' + big + 'px "Inter",system-ui,sans-serif';
    var n = String(i);
    while (n.length < 3) n = "0" + n;
    ctx.fillText(n, x - 3, base);
    var nw = ctx.measureText(n).width;

    ctx.fillStyle = "rgba(" + d + ",.26)";
    ctx.font = '500 13px ui-monospace,"SFMono-Regular",Menlo,monospace';
    ctx.fillText("/ " + (sc.frames - 1), x + nw + 10, base);

    var ty = base + 26;
    ctx.fillStyle = "rgba(" + d + ",.22)";
    ctx.fillRect(x, ty, strip, 1);
    for (var k = 0; k < sc.frames; k++) {
      var tx = x + (strip - 1) * (sc.frames > 1 ? k / (sc.frames - 1) : 0);
      var on = k === i;
      ctx.fillStyle = on ? "rgba(" + acc + ",.85)" : "rgba(" + d + ",.22)";
      ctx.fillRect(Math.round(tx), ty - (on ? 10 : 4), on ? 2 : 1, on ? 20 : 8);
    }
    return true;
  };

  /* -- numbered frame sequence painted to canvas (exact seek anywhere) - */
  function FrameSequenceSource(sc, m) {
    this.sc = sc; this.m = m;
    this.frames = m.frames || sc.frames;
    this.bmp = new Array(this.frames);
    this.have = 0; this.state = "idle";
  }
  FrameSequenceSource.prototype.url = function (i) {
    var pad = this.m.pad || 3, n = String(i + (this.m.start || 0));
    while (n.length < pad) n = "0" + n;
    return this.m.pattern.replace("%d", n);
  };
  FrameSequenceSource.prototype.load = function () {
    if (this._p) return this._p;
    var self = this, conc = this.m.concurrency || 6, next = 0;
    this.state = "loading";
    function worker() {
      if (next >= self.frames) return Promise.resolve();
      var i = next++;
      return fetch(self.url(i), { mode: "cors" })
        .then(function (r) { return r.blob(); })
        .then(createImageBitmap)
        .then(function (b) {
          self.bmp[i] = b;
          if (++self.have === 1) self.state = "ready";
          self.sc.dirty = true; kick();
        })
        .catch(function () { /* hole; draw() falls back to the nearest */ })
        .then(worker);
    }
    var pool = [];
    for (var k = 0; k < conc; k++) pool.push(worker());
    this._p = Promise.all(pool).then(function () {
      self.state = self.have ? "ready" : "error";
    });
    return this._p;
  };
  FrameSequenceSource.prototype.draw = function (ctx, i, w, h) {
    var b = this.bmp[i];
    if (!b) {
      for (var d = 1; d < this.frames && !b; d++) b = this.bmp[i - d] || this.bmp[i + d];
      if (!b) return false;
    }
    return cover(ctx, b, w, h);
  };

  /* -- short-GOP mp4 seeked by currentTime ---------------------------- */
  function VideoSource(sc, m) {
    this.sc = sc; this.m = m;
    this.fps = m.fps || 24;
    this.frames = m.frames || sc.frames;
    this.state = "idle";
  }
  VideoSource.prototype.load = function () {
    if (this._p) return this._p;
    var self = this, v = document.createElement("video");
    v.src = this.m.src; v.preload = "auto"; v.muted = true;
    v.playsInline = true; v.crossOrigin = "anonymous";
    this.v = v; this.state = "loading";
    this._p = new Promise(function (res) {
      v.addEventListener("loadeddata", function () {
        self.state = "ready"; self.sc.dirty = true; kick(); res();
      }, { once: true });
      v.addEventListener("error", function () { self.state = "error"; res(); }, { once: true });
    });
    v.load();
    return this._p;
  };
  VideoSource.prototype.draw = function (ctx, i, w, h) {
    var v = this.v, self = this;
    if (!v || this.state !== "ready" || !v.videoWidth) return false;
    var t = Math.min(i / this.fps, (v.duration || 1e9) - 1e-3);
    if (!this._seek && Math.abs(v.currentTime - t) > 0.5 / this.fps) {
      this._seek = true;
      v.addEventListener("seeked", function () {
        self._seek = false; self.sc.dirty = true; kick();
      }, { once: true });
      try { v.currentTime = t; } catch (e) { this._seek = false; }
    }
    return cover(ctx, v, w, h);
  };

  function makeSource(sc) {
    var m = sc.media;
    if (m && m.kind === "frames") return new FrameSequenceSource(sc, m);
    if (m && m.kind === "video") return new VideoSource(sc, m);
    return new PlaceholderSource(sc);
  }

  /* ================================================================== */
  /*  WIRE UP                                                           */
  /* ================================================================== */
  var root = document.documentElement;
  var elClock = document.getElementById("clock");
  var elBeat = document.getElementById("barbeat");
  var elDay = document.getElementById("daybar");
  var elHud = document.getElementById("hud");

  S.forEach(function (sc) {
    sc.el = document.getElementById("scene-" + sc.n);
    sc.stage = sc.el.querySelector(".stage");
    sc.cv = sc.el.querySelector("canvas");
    sc.ctx = sc.cv.getContext("2d", { alpha: false });
    sc.frame = -1;
    sc.dirty = true;
    sc.src = makeSource(sc);
  });

  /* ---- loading: scene 1 eager, the rest pulled as they approach ----- */
  function onScreen(sc) {
    var y = window.scrollY;
    return sc.top < y + window.innerHeight && sc.top + sc.h > y;
  }
  function ensure(sc) {
    if (!sc || sc.src.state !== "idle") return;
    sc.src.load().then(function () {
      sc.dirty = true;
      if (reduced) stillFrame(sc); else kick();
      // Warm the next one ONLY while this one is actually on screen. An
      // unconditional chain cascades the whole day on the first load —
      // invisible with placeholders, fatal with footage.
      if (onScreen(sc)) ensure(S[sc.n]);
    });
  }

  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (e) {
        if (!e.isIntersecting) return;
        var sc = S[+e.target.dataset.scene - 1];
        ensure(sc);
        io.unobserve(e.target);
      });
    }, { rootMargin: "120% 0px" });
    S.forEach(function (sc) { if (sc.n > 1) io.observe(sc.el); });
  } else {
    S.forEach(ensure);
  }
  // Scene 1 after first paint — eager, but never in front of it.
  requestAnimationFrame(function () {
    requestAnimationFrame(function () { ensure(S[0]); });
  });

  /* ---- geometry ----------------------------------------------------- */
  var vh = 0, dpr = 1;
  function measure() {
    vh = window.innerHeight;
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    S.forEach(function (sc) {
      sc.top = sc.el.offsetTop;
      sc.h = sc.el.offsetHeight;
      sc.stageH = sc.stage.offsetHeight;
      sc.travel = Math.max(1, Math.min(sc.frames * PPF, sc.h - sc.stageH));
      sc.w = sc.stage.clientWidth;
      sc.ch = sc.stage.clientHeight;
      var bw = Math.round(sc.w * dpr), bh = Math.round(sc.ch * dpr);
      if (sc.cv.width !== bw || sc.cv.height !== bh) {
        sc.cv.width = bw; sc.cv.height = bh;
      }
      sc.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      sc.dirty = true;
    });
  }

  function hold(ctx, sc, i, w, h) {      // flat day colour under a clip
    var p = sc.frames > 1 ? i / (sc.frames - 1) : 0;
    ctx.fillStyle = mix(sc.c0, sc.c1, p);
    ctx.fillRect(0, 0, w, h);
  }

  function paint(sc, i) {
    if (!sc.src.draw(sc.ctx, i, sc.w, sc.ch)) hold(sc.ctx, sc, i, sc.w, sc.ch);
  }

  /* ---- chrome ------------------------------------------------------- */
  var lastInk = "";
  function chrome(sc, p) {
    if (!sc) {                       // above the first beat, or past the last
      var last = S[S.length - 1];
      if (window.scrollY >= last.top + last.h) { sc = last; p = 1; }
      else { sc = S[0]; p = 0; }
    }
    elClock.textContent = clock(sc.t0 + (sc.t1 - sc.t0) * p);
    elBeat.textContent = sc.title;
    elHud.textContent = "S" + sc.n + " " + String(Math.max(sc.frame, 0)).padStart(3, "0")
                      + "/" + (sc.frames - 1);
    var col = mix(sc.c0, sc.c1, p), light = lum(col) > 0.42;
    var ink = light ? "d" : "l";
    if (ink !== lastInk) {
      lastInk = ink;
      root.style.setProperty("--ink", light ? "#15171e" : "#f4f1ec");
      root.style.setProperty("--ink-dim", light ? "rgba(21,23,30,.76)" : "rgba(244,241,236,.68)");
      root.style.setProperty("--scrim", light ? "rgba(250,246,238,.72)" : "rgba(8,9,14,.62)");
      root.style.setProperty("--scrim-bar", light ? "rgba(250,246,238,.86)" : "rgba(8,9,14,.82)");
      root.style.setProperty("--rule", light ? "rgba(21,23,30,.2)" : "rgba(255,255,255,.16)");
    }
    var doc = document.documentElement.scrollHeight - vh;
    elDay.style.width = (doc > 0 ? clamp(window.scrollY / doc, 0, 1) * 100 : 0) + "%";
  }

  /* ---- the scrub ---------------------------------------------------- */
  var queued = false, reduced = RM.matches;
  function kick() {
    if (reduced) return;          // nothing scrubs; stills are already painted
    if (!queued) { queued = true; requestAnimationFrame(render); }
  }
  function render() {
    queued = false;
    var y = window.scrollY, cur = null, curP = 0;
    for (var k = 0; k < S.length; k++) {
      var sc = S[k];
      if (y + vh <= sc.top || y >= sc.top + sc.h) continue;       // off screen
      var p = clamp((y - sc.top) / sc.travel, 0, 1);
      var i = Math.round(p * (sc.frames - 1));
      if (i !== sc.frame || sc.dirty) {
        sc.frame = i; sc.dirty = false; paint(sc, i);
      }
      if (y >= sc.top && y < sc.top + sc.h) { cur = sc; curP = p; }
    }
    chrome(cur, curP);
  }

  /* ---- reduced motion: one still per scene, no loop ------------------ */
  function stillFrame(sc) {
    var i = Math.round((sc.frames - 1) / 2);
    sc.frame = i; sc.dirty = false; paint(sc, i);
  }
  function still() {
    S.forEach(stillFrame);
    root.style.setProperty("--ink", "#f4f1ec");
    root.style.setProperty("--ink-dim", "rgba(244,241,236,.68)");
    root.classList.add("rm");     // the bar's scrub instruments go away
    elBeat.textContent = "The day";
  }
  function start() {
    measure();
    if (reduced) { still(); return; }
    root.classList.remove("rm");
    render();
    addEventListener("scroll", kick, { passive: true });
  }
  function restart() {
    measure();
    if (reduced) still(); else render();
  }

  var lastW = window.innerWidth;
  addEventListener("resize", function () {
    // A height-only change is the mobile toolbar moving, not a new layout.
    // Nothing is sized to it, so just note the new height and carry on —
    // a full re-measure here is what made scroll-up catch.
    // Desktop is different: dragging a window's height DOES change the large
    // viewport, so check the stage really held its size before skipping.
    if (window.innerWidth === lastW && S[0].stage.offsetHeight === S[0].stageH) {
      vh = window.innerHeight;
      if (!reduced) kick();
      return;
    }
    lastW = window.innerWidth;
    clearTimeout(window.__rz);
    window.__rz = setTimeout(restart, 120);
  }, { passive: true });
  RM.addEventListener("change", function (e) {
    reduced = e.matches;
    if (reduced) removeEventListener("scroll", kick);
    else addEventListener("scroll", kick, { passive: true });
    restart();
  });
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(restart);

  start();

  /* ---- beat index --------------------------------------------------- */
  var sheet = document.getElementById("sheet"), btn = document.getElementById("beatsbtn");
  function setSheet(on) {
    sheet.classList.toggle("on", on);
    btn.setAttribute("aria-expanded", on ? "true" : "false");
    if (on) sheet.querySelector("a").focus();
    else btn.focus();
  }
  btn.addEventListener("click", function () { setSheet(!sheet.classList.contains("on")); });
  document.getElementById("sheetclose").addEventListener("click", function () { setSheet(false); });
  sheet.addEventListener("click", function (e) { if (e.target.closest("a")) setSheet(false); });
  addEventListener("keydown", function (e) {
    if (e.key === "Escape" && sheet.classList.contains("on")) setSheet(false);
  });

  /* ---- handle for measuring, and for the day the footage lands ------- */
  window.DAY = {
    scenes: S,
    render: render,
    remeasure: restart,
    ppf: PPF,
    /* Cost of a scrub: walk a scene's travel and time the render path.
       Synchronous on purpose — requestAnimationFrame is throttled in a
       background tab, which would measure the browser, not the page.
       Only the steps where the frame index actually changed are counted;
       the steps that hold are free by design, and are reported apart. */
    bench: function (n, steps) {
      n = n || 1; steps = steps || 600;
      var sc = S[n - 1], y0 = window.scrollY, drawn = [], all = [], i, t0, dt, was;
      for (i = 0; i < steps; i++) {
        window.scrollTo(0, sc.top + sc.travel * (i / (steps - 1)));
        was = sc.frame;
        t0 = performance.now();
        render();
        dt = performance.now() - t0;
        all.push(dt);
        if (sc.frame !== was) drawn.push(dt);
      }
      window.scrollTo(0, y0);
      function q(a, f) {
        var z = a.slice().sort(function (x, y) { return x - y; });
        return z.length ? +z[Math.min(z.length - 1, Math.floor(z.length * f))].toFixed(3) : 0;
      }
      function mean(a) {
        return +(a.reduce(function (x, y) { return x + y; }, 0) / (a.length || 1)).toFixed(3);
      }
      return {
        scene: n, frames: sc.frames, travelPx: Math.round(sc.travel),
        pxPerFrame: +(sc.travel / (sc.frames - 1)).toFixed(1),
        steps: steps, redraws: drawn.length,
        canvas: sc.cv.width + "x" + sc.cv.height, dpr: dpr,
        redrawMs: { mean: mean(drawn), p50: q(drawn, .5), p95: q(drawn, .95), max: q(drawn, 1) },
        allStepsMs: { mean: mean(all), p95: q(all, .95) }
      };
    }
  };
})();
