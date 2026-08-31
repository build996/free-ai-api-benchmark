// Batch version of make_cover.mjs — one browser for the whole set.
// Launching Chrome per card takes ~1.5 s; reusing one page makes 70 cards a
// few seconds instead of two minutes.
//   node automation/make_covers_batch.mjs theme/cover_plan.json images/covers
import { chromium } from 'playwright';
import { readFileSync, mkdirSync, existsSync } from 'fs';

const [, , planPath, outDir] = process.argv;
if (!planPath || !outDir) {
  console.error('usage: node make_covers_batch.mjs <plan.json> <outDir>');
  process.exit(1);
}

const ACCENTS = {
  green: '#34d399', amber: '#fbbf24', red: '#f87171',
  violet: '#a78bfa', blue: '#60a5fa',
};

function cardHtml(title, kicker, accentName) {
  const accent = ACCENTS[accentName] || ACCENTS.blue;
  const len = title.length;
  const size = len <= 6 ? 116 : len <= 12 ? 84 : len <= 18 ? 60 : len <= 24 ? 46 : 38;
  return `<!doctype html><html><head><meta charset="utf-8"><style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    width:1200px; height:630px; display:flex; flex-direction:column;
    justify-content:center; align-items:center; text-align:center;
    padding:0 250px;
    background:#0f172a;
    background-image:
      radial-gradient(1100px 520px at 88% -12%, rgba(96,165,250,.16), transparent 62%),
      radial-gradient(760px 460px at 6% 108%, ${accent}1f, transparent 60%);
    font-family:"Segoe UI","Helvetica Neue",Arial,sans-serif; color:#f8fafc;
    position:relative; overflow:hidden;
  }
  .rule { width:64px; height:6px; background:${accent}; border-radius:4px; margin-bottom:28px; }
  .kicker { font-size:25px; font-weight:600; letter-spacing:.15em; text-transform:uppercase;
            color:${accent}; margin-bottom:20px; }
  h1 { font-size:${size}px; font-weight:800; letter-spacing:-.02em; line-height:1.1;
       max-width:600px; overflow-wrap:break-word; }
  .foot { display:flex; align-items:center; justify-content:center; gap:12px;
          margin-top:34px; font-size:24px; color:#94a3b8; font-weight:500; }
  .dot { width:11px; height:11px; border-radius:50%; background:${accent}; }
  .grid { position:absolute; inset:0; opacity:.05;
          background-image:linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg,#fff 1px, transparent 1px);
          background-size:64px 64px; }
</style></head><body>
  <div class="grid"></div>
  <div class="rule"></div>
  ${kicker ? `<div class="kicker">${kicker}</div>` : ''}
  <h1>${title}</h1>
  <div class="foot"><span class="dot"></span><span>toolfreebie.com</span></div>
</body></html>`;
}

const plan = JSON.parse(readFileSync(planPath, 'utf-8'));
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 2 });

let made = 0, skipped = 0;
for (const item of plan) {
  const out = `${outDir}/${item.slug}.jpg`;
  if (existsSync(out)) { skipped++; continue; }
  await page.setContent(cardHtml(item.subject, item.kicker, item.accent), { waitUntil: 'load' });
  await page.screenshot({ path: out, type: 'jpeg', quality: 92 });
  made++;
  if (made % 10 === 0) process.stdout.write(`${made} `);
}
await browser.close();
console.log(`\ndone — ${made} generated, ${skipped} already present`);
