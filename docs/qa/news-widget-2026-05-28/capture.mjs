// Capture screenshots of the news right-rail widget at three viewports
// across two sample articles. Talks to a local static server at
// http://localhost:8765 serving marketing-site/.
import { chromium } from '../../../frontend/node_modules/playwright/index.mjs';
import { mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';

const OUT_DIR = dirname(fileURLToPath(import.meta.url));
await mkdir(OUT_DIR, { recursive: true });

const BASE = 'http://localhost:8765';

const ARTICLES = [
  { slug: 'v5-3-0', label: 'release-v5-3-0' },
  { slug: 'open-erp-own-your-stack', label: 'concept-paper' },
];

const VIEWPORTS = [
  { name: 'desktop-wide-1600', width: 1600, height: 900 },
  { name: 'desktop-1280', width: 1280, height: 800 },
  { name: 'mobile-375', width: 375, height: 812 },
];

const browser = await chromium.launch();
try {
  for (const article of ARTICLES) {
    for (const vp of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: vp.width, height: vp.height },
        deviceScaleFactor: vp.deviceScaleFactor || 1,
        isMobile: !!vp.isMobile,
        hasTouch: !!vp.hasTouch,
      });
      const page = await context.newPage();
      const url = `${BASE}/news/${article.slug}.html`;
      console.log(`\n=== ${article.label} @ ${vp.name} (${vp.width}x${vp.height}) ===`);
      await page.goto(url, { waitUntil: 'networkidle' });
      await page.waitForTimeout(400);
      const inlineCount = await page.locator('.oce-more-rail--inline').count();
      const railCount = await page.locator('.oce-more-rail--rail').count();
      console.log(`  inline=${inlineCount} rail=${railCount}`);

      // Use behavior:instant to bypass the page's `scroll-behavior: smooth`.
      if (vp.width >= 1500) {
        await page.evaluate(() => window.scrollTo({ top: document.body.scrollHeight * 0.45, behavior: 'instant' }));
      } else {
        await page.evaluate(() => {
          const el = document.querySelector('.oce-more-rail--inline');
          if (el) {
            const r = el.getBoundingClientRect();
            const target = window.scrollY + r.top - 60;
            window.scrollTo({ top: target, behavior: 'instant' });
          }
        });
      }
      await page.waitForTimeout(500);

      const outPath = `${OUT_DIR}/${article.label}__${vp.name}.png`;
      await page.screenshot({ path: outPath, fullPage: false });
      console.log(`  -> ${outPath}`);

      const outFull = `${OUT_DIR}/${article.label}__${vp.name}__full.png`;
      await page.screenshot({ path: outFull, fullPage: true });
      console.log(`  -> ${outFull}`);

      await context.close();
    }
  }
} finally {
  await browser.close();
}
console.log('\nDone.');
