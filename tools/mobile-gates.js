/* mobile-gates.js — the phone bar for a page, checked rather than hoped for.

     node tools/mobile-gates.js <url-or-file> [outDir]
     node tools/mobile-gates.js http://localhost:8080/home.html mobile

   Exits non-zero if any gate fails. Gates, not goals.

   WHERE THIS RUNS: the Claude cloud sandbox, which is where Playwright and
   Chromium live (/opt/pw-browsers). Peter's desktop workspace has node but no
   browsers, so this is Claude's tool to run, not a command for Peter's
   Terminal. Same arrangement as tools/shots.js and tools/gates.js.

   WHAT IT CANNOT SEE: Chromium emulating an iPhone is not Safari. Device
   profiles reproduce viewport, DPR, touch and user agent — they do NOT
   reproduce WebKit's rendering or the collapsing address bar that makes
   100vh wrong on iOS. WebKit is unavailable here (its download is blocked by
   network policy), so anything WebKit-specific is caught by the STATIC rules
   below instead of by looking at a picture. Before anything ships, open it on
   a real iPhone once. This narrows that check; it does not replace it. */

const { chromium, devices } = require('playwright');
const fs = require('fs');
const path = require('path');

const TARGET = process.argv[2] || 'http://localhost:8080/home.html';
const OUT = process.argv[3] || 'mobile';

// Smallest-common first: if it survives an iPhone SE it survives most things.
const PROFILES = [
  ['iPhone SE',      devices['iPhone SE']],
  ['iPhone 15 Pro',  devices['iPhone 15 Pro']],
  ['Pixel 7',        devices['Pixel 7']],
  ['iPad Mini',      devices['iPad Mini']],
];

const TAP_MIN = 44;   // Apple HIG minimum, and a good floor on Android too
const results = [];
function gate(name, pass, detail) {
  results.push({ name, pass: !!pass, detail: detail || '' });
  console.log(`  ${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  — ' + detail : ''}`);
}

async function sourceOf(target) {
  if (/^https?:/.test(target)) {
    const b = await chromium.launch();
    const p = await b.newPage();
    await p.goto(target, { waitUntil: 'load' });
    const html = await p.content();
    await b.close();
    return html;
  }
  return fs.readFileSync(target, 'utf8');
}

/* Static rules — the WebKit-shaped things a Chromium screenshot will not
   reveal. Cheap, deterministic, and they catch the bugs that only appear on
   someone else's phone. */
function staticGates(html) {
  console.log('\nStatic rules (what emulation cannot show)\n');

  const vp = html.match(/<meta[^>]+name=["']viewport["'][^>]*>/i);
  gate('viewport meta present', !!vp, vp ? vp[0].slice(0, 80) : 'MISSING — iOS will render at 980px and shrink everything');
  if (vp) {
    const c = (vp[0].match(/content=["']([^"']+)/i) || [])[1] || '';
    gate('viewport width=device-width', /width\s*=\s*device-width/i.test(c), c);
    gate('viewport does not block zoom',
      !/user-scalable\s*=\s*no/i.test(c) && !/maximum-scale\s*=\s*1/i.test(c),
      /user-scalable|maximum-scale/i.test(c) ? 'blocks pinch-zoom — an accessibility failure' : 'pinch-zoom allowed');
  }

  // 100vh is taller than the visible area on iOS while the address bar shows.
  const vh = (html.match(/:\s*[^;{}]*\b100vh\b/g) || []).length;
  const svh = (html.match(/\b100svh\b|\b100dvh\b/g) || []).length;
  gate('100vh has an svh/dvh companion', vh === 0 || svh > 0,
    vh === 0 ? 'no 100vh used' :
      (svh > 0 ? `${vh} x 100vh, ${svh} x svh/dvh override — correct fallback order`
               : `${vh} x 100vh and NO svh/dvh — will overflow on iOS Safari`));

  // Anything pinned to the bottom needs the home-indicator inset.
  const pinnedBottom = /position\s*:\s*(fixed|sticky)[^;{}]*;[^{}]*bottom\s*:\s*0/i.test(html)
                    || /bottom\s*:\s*0[^{}]*;[^{}]*position\s*:\s*(fixed|sticky)/i.test(html);
  const safeArea = /env\(\s*safe-area-inset/i.test(html);
  gate('bottom-pinned UI clears the home indicator', !pinnedBottom || safeArea,
    !pinnedBottom ? 'nothing pinned to the bottom'
      : (safeArea ? 'uses env(safe-area-inset-*)'
                  : 'fixed/sticky bottom with no env(safe-area-inset-bottom) — sits under the home bar'));

  // <16px on an input makes iOS Safari zoom the whole page on focus.
  const smallInput = /(input|select|textarea)[^{}]*\{[^{}]*font-size\s*:\s*(1[0-5](\.\d+)?px|0?\.\d+rem)/i.test(html);
  gate('inputs are >= 16px', !smallInput, smallInput ? 'an input under 16px — iOS zooms the page on focus' : 'no undersized inputs found');

  gate('has responsive breakpoints', /@media[^{]*max-width/i.test(html),
    `${(html.match(/@media[^{]*(max|min)-width/gi) || []).length} width media queries`);
}

async function deviceGates(browser, label, profile) {
  console.log(`\n${label}  (${profile.viewport.width}x${profile.viewport.height} @${profile.deviceScaleFactor}x)\n`);
  const ctx = await browser.newContext(profile);
  const page = await ctx.newPage();
  await page.goto(/^https?:/.test(TARGET) ? TARGET : 'file://' + path.resolve(TARGET),
    { waitUntil: 'load' });
  await page.waitForTimeout(700);

  const m = await page.evaluate((TAP_MIN) => {
    const de = document.documentElement;
    const vw = de.clientWidth;

    // An element only "sticks out" if nothing clips it. Two big sources of
    // false positives, both legitimate: children of an <svg> are clipped by
    // its viewBox, and anything inside an overflow-hidden ancestor (tickers,
    // carousels, marquees) is deliberately wider than its frame.
    const clipped = (el) => {
      if (el.closest && el.closest('svg')) return true;
      for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        const s = getComputedStyle(a);
        if (/hidden|clip|auto|scroll/.test(s.overflowX + ' ' + s.overflow)) return true;
      }
      return false;
    };

    const wide = [];
    for (const el of document.querySelectorAll('body *')) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      const cs = getComputedStyle(el);
      if (cs.position === 'fixed' || cs.overflowX === 'auto' || cs.overflowX === 'scroll') continue;
      if (clipped(el)) continue;
      if (r.right > vw + 1 || r.left < -1) {
        wide.push((el.tagName.toLowerCase()
          + (el.id ? '#' + el.id : '')
          + (el.className && typeof el.className === 'string'
              ? '.' + el.className.trim().split(/\s+/).slice(0, 2).join('.') : ''))
          + ` [${Math.round(r.left)}..${Math.round(r.right)}]`);
      }
      if (wide.length > 6) break;
    }

    const small = [];
    const seenTap = new Set();
    for (const el of document.querySelectorAll('a,button,[role="button"],input,select,summary')) {
      const r = el.getBoundingClientRect();
      if (r.width === 0 || r.height === 0) continue;
      if (getComputedStyle(el).visibility === 'hidden') continue;
      if (r.width < TAP_MIN || r.height < TAP_MIN) {
        const name = (el.getAttribute('aria-label') || el.title
          || (el.textContent || '').trim().slice(0, 18) || el.className || '').toString().trim();
        const key = `${el.tagName}|${name}|${Math.round(r.width)}x${Math.round(r.height)}`;
        if (seenTap.has(key)) continue;      // one row per distinct control
        seenTap.add(key);
        small.push(`${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}`
          + (name ? ` "${name}"` : '') + ` ${Math.round(r.width)}x${Math.round(r.height)}`);
      }
      if (small.length > 6) break;
    }

    const overflowImgs = [...document.images]
      .filter(i => i.getBoundingClientRect().width > vw + 1).length;

    return { vw, scrollW: de.scrollWidth, clientW: de.clientWidth,
             wide, small, overflowImgs,
             docH: de.scrollHeight, vh: de.clientHeight };
  }, TAP_MIN);

  gate(`${label}: no sideways scrolling`, m.scrollW <= m.clientW + 1,
    `content ${m.scrollW}px in a ${m.clientW}px screen${m.scrollW > m.clientW + 1 ? ' — the page slides left/right' : ''}`);
  gate(`${label}: nothing sticks out past the edge`, m.wide.length === 0,
    m.wide.length ? m.wide.join(' | ') : 'every element inside the screen');
  gate(`${label}: images fit`, m.overflowImgs === 0,
    m.overflowImgs ? `${m.overflowImgs} image(s) wider than the screen — add max-width:100%` : 'all images fit');
  gate(`${label}: tap targets >= ${TAP_MIN}px`, m.small.length === 0,
    m.small.length ? m.small.join(' | ') : 'all comfortably tappable');

  fs.mkdirSync(OUT, { recursive: true });
  const slug = label.toLowerCase().replace(/[^a-z0-9]+/g, '-');
  await page.screenshot({ path: path.join(OUT, `${slug}-top.png`) });
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(OUT, `${slug}-bottom.png`) });

  await ctx.close();
  console.log(`        page is ${(m.docH / m.vh).toFixed(1)} screens tall; shots -> ${OUT}/${slug}-*.png`);
}

(async () => {
  console.log(`Mobile gates — ${TARGET}`);
  staticGates(await sourceOf(TARGET));
  const browser = await chromium.launch();
  for (const [label, profile] of PROFILES) await deviceGates(browser, label, profile);
  await browser.close();

  const failed = results.filter(r => !r.pass);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  if (failed.length) {
    console.log('\nFailed:');
    for (const f of failed) console.log(`  - ${f.name}: ${f.detail}`);
    console.log('\nReminder: Chromium is not Safari. Open it on a real iPhone before shipping.');
    process.exit(1);
  }
  console.log('\nAll gates pass. Still open it on a real iPhone once before shipping.');
})();
