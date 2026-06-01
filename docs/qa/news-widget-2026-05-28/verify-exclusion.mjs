// Verify that the widget excludes the current article from its own card list.
import { chromium } from '../../../frontend/node_modules/playwright/index.mjs';

const tests = [
  'v5-3-0',
  'open-erp-own-your-stack',
  'v5-2-0',
  'v3-0-0',
  'v4-0-0',
];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
const page = await ctx.newPage();

let allGood = true;
for (const slug of tests) {
  await page.goto(`http://localhost:8765/news/${slug}.html`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  const hrefs = await page.$$eval(
    '.oce-more-rail--inline .oce-mini-card',
    (els) => els.map((e) => e.getAttribute('href'))
  );
  const selfHit = hrefs.find((h) => h && h.includes(`/${slug}.html`));
  const status = selfHit ? 'LEAK' : 'ok';
  if (selfHit) allGood = false;
  console.log(`${status.padEnd(4)} ${slug} (${hrefs.length} cards) self=${selfHit || '-'}`);
}
await browser.close();
process.exit(allGood ? 0 : 1);
