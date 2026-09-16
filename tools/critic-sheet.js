/* critic-sheet.js — a FIXED set of frames for the technique-3 critic.
   Same viewport, same scroll fractions, same filenames every round, so the
   only thing that changes between rounds is the design itself. */
const { chromium } = require('playwright');
const path = require('path'); const fs = require('fs');
const FRACS = [0, 0.08, 0.22, 0.38, 0.55, 0.76, 1.0];
(async () => {
  const target = process.argv[2] || 'home.local.html';
  const out = process.argv[3] || 'crit';
  fs.mkdirSync(out, { recursive: true });
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await p.goto('file://' + path.resolve(target), { waitUntil: 'load' });
  await p.waitForTimeout(900);
  const total = await p.evaluate(() => document.body.scrollHeight);
  for (let i = 0; i < FRACS.length; i++) {
    await p.evaluate((y) => window.scrollTo(0, y), Math.round(FRACS[i] * (total - 900)));
    await p.waitForTimeout(280);
    await p.screenshot({ path: path.join(out, `${String(i + 1).padStart(2, '0')}.png`) });
  }
  await b.close();
  console.log('critic sheet written to', out);
})();
