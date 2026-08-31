// Generate a branded 1200x630 cover card. No external sites, no volatile numbers.
//   node automation/make_cover.mjs "GROQ" "speed tested" images/groq_cover.jpg
//   node automation/make_cover.mjs "GROQ" "speed tested" images/groq_cover.jpg --accent=amber
//
// Design rules (deliberate — see the reasoning in the repo notes):
//   * Never bake a measured number into the image. Numbers change; images are
//     expensive to change. The subject and the *kind* of testing are stable.
//   * One dominant word so the card is identifiable at thumbnail size.
import { chromium } from 'playwright';
import { mkdirSync } from 'fs';
import { dirname, resolve } from 'path';

const args = process.argv.slice(2);
const flags = Object.fromEntries(
  args.filter(a => a.startsWith('--')).map(a => a.replace(/^--/, '').split('='))
);
const [title, kicker, outPath] = args.filter(a => !a.startsWith('--'));

if (!title || !outPath) {
  console.error('usage: node make_cover.mjs "<TITLE>" "<kicker>" <out.jpg> [--accent=green|amber|red|violet]');
  process.exit(1);
}

const ACCENTS = {
  green:  '#34d399',   // still free / verified
  amber:  '#fbbf24',   // caveats
  red:    '#f87171',   // no longer free
  violet: '#a78bfa',   // agents / harness
  blue:   '#60a5fa',   // default
};
const accent = ACCENTS[flags.accent] || ACCENTS.blue;

// Scale the headline down as it gets longer so it always fits on one line.
const len = title.length;
const size = len <= 6 ? 116 : len <= 12 ? 84 : len <= 18 ? 60 : len <= 24 ? 46 : 38;

const html = `<!doctype html><html><head><meta charset="utf-8">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    width:1200px; height:630px; display:flex; flex-direction:column;
    justify-content:center; align-items:center; text-align:center;
    /* Content sits inside a centred ~630px-wide safe zone so it survives the
       square crop WordPress applies to archive cards. */
    padding:0 250px;
    background:#0f172a;
    background-image:
      radial-gradient(1100px 520px at 88% -12%, rgba(96,165,250,.16), transparent 62%),
      radial-gradient(760px 460px at 6% 108%, ${accent}1f, transparent 60%);
    font-family:"Segoe UI","Helvetica Neue",Arial,sans-serif; color:#f8fafc;
    position:relative; overflow:hidden;
  }
  .rule { width:64px; height:6px; background:${accent}; border-radius:4px; margin-bottom:28px; }
  .kicker {
    font-size:25px; font-weight:600; letter-spacing:.15em; text-transform:uppercase;
    color:${accent}; margin-bottom:20px;
  }
  h1 { font-size:${size}px; font-weight:800; letter-spacing:-.02em; line-height:1.1;
       max-width:600px; overflow-wrap:break-word; }
  .foot {
    display:flex; align-items:center; justify-content:center; gap:12px;
    margin-top:34px; font-size:24px; color:#94a3b8; font-weight:500;
  }
  .dot { width:11px; height:11px; border-radius:50%; background:${accent}; }
  .grid {
    position:absolute; inset:0; opacity:.05;
    background-image:linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg,#fff 1px, transparent 1px);
    background-size:64px 64px;
  }
</style></head><body>
  <div class="grid"></div>
  <div class="rule"></div>
  ${kicker ? `<div class="kicker">${kicker}</div>` : ''}
  <h1>${title}</h1>
  <div class="foot"><span class="dot"></span><span>toolfreebie.com</span></div>
</body></html>`;

mkdirSync(dirname(resolve(outPath)), { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const page = await browser.newPage({
  viewport: { width: 1200, height: 630 },
  deviceScaleFactor: 2,
});
await page.setContent(html, { waitUntil: 'load' });
await page.screenshot({ path: outPath, type: 'jpeg', quality: 92 });
await browser.close();
console.log('wrote', outPath);
