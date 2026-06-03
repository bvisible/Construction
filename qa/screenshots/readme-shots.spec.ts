/**
 * readme-shots.spec.ts — regenerate the four numbered README screenshots.
 *
 * The committed docs/screenshots/02-dashboard.png, 03-projects.png,
 * 06-schedule.png and 07-ai-estimate.png were captured on an old April
 * layout WITH the product-tour spotlight active, so they carry a dark
 * dimming backdrop (and an obsolete sidebar). This spec recaptures just
 * those four routes from the current build with the tour, onboarding and
 * what's-new overlays fully suppressed, writing straight into
 * docs/screenshots/ under the canonical filenames.
 *
 * It reuses the exact auth + overlay-suppression approach proven in
 * full-app.spec.ts, trimmed to the four routes the README embeds.
 *
 * Run (backend serves both API and built SPA on :8080):
 *   QA_API_URL=http://127.0.0.1:8080 QA_BASE_URL=http://127.0.0.1:8080 \
 *     npx playwright test --config qa/screenshots/readme-shots.config.ts
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

const API_URL = process.env.QA_API_URL ?? 'http://127.0.0.1:8080';
const BASE_URL = process.env.QA_BASE_URL ?? 'http://127.0.0.1:8080';
const DEMO_EMAIL = process.env.QA_DEMO_EMAIL ?? 'demo@openconstructionerp.com';

const OUT_DIR = join(process.cwd(), 'docs', 'screenshots');

const NETWORK_IDLE_MS = 12_000;
const SETTLE_MS = 2_500;

// README path -> canonical docs/screenshots filename.
const SHOTS: Array<{ path: string; file: string; waitMs?: number }> = [
  { path: '/dashboard', file: '02-dashboard.png' },
  { path: '/projects', file: '03-projects.png' },
  { path: '/schedule', file: '06-schedule.png' },
  { path: '/ai-estimate', file: '07-ai-estimate.png' },
];

async function demoToken(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${API_URL}/api/v1/users/auth/demo-login/`, {
    failOnStatusCode: false,
    data: { email: DEMO_EMAIL },
  });
  if (!res.ok()) {
    throw new Error(`demo-login failed (status=${res.status()}); backend reachable at ${API_URL}?`);
  }
  const json = (await res.json()) as { access_token: string };
  return json.access_token;
}

async function hydrate(page: Page, token: string): Promise<void> {
  await page.addInitScript((t) => {
    localStorage.setItem('oe_access_token', t);
    localStorage.setItem('oe_refresh_token', t);
    localStorage.setItem('oe_remember', '1');
    localStorage.setItem('oe_user_email', 'demo@openconstructionerp.com');
    // Suppress the onboarding wizard, product tour, legacy tour and the
    // what's-new card — all of which paint a dimming/spotlight overlay.
    localStorage.setItem('oe_onboarding_completed', 'true');
    localStorage.setItem('oe_welcome_dismissed', 'true');
    localStorage.setItem('oe_tour_completed', 'true');
    localStorage.setItem('oe.tour_completed', 'true');
    for (const id of ['global', 'boq', 'accommodation', 'bim', 'geo', 'propdev', 'dashboard']) {
      localStorage.setItem(`oe.tour_completed.${id}`, 'true');
    }
    localStorage.setItem('oe.last_seen_version', '9999.0.0');
    // Suppress the v6 SQLite->PostgreSQL migration notice strip
    // (PostgresMigrationNotice.tsx) — a real notice for v6/PG users, but
    // it must not sit atop a marketing screenshot.
    localStorage.setItem('oe.v6_pg_notice_dismissed', '1');
    sessionStorage.setItem('oe_access_token', t);
    sessionStorage.setItem('oe_refresh_token', t);
    sessionStorage.setItem('oe_demo_modal_dismissed', '1');
  }, token);

  // Defence in depth: hide the tour spotlight backdrop + the demo modal
  // by stable testids/classes, in case a flag key ever drifts.
  await page.addInitScript(() => {
    const inject = () => {
      if (document.getElementById('__qa_overlay_hider')) return;
      const style = document.createElement('style');
      style.id = '__qa_overlay_hider';
      style.textContent = `
        [data-testid="product-tour-overlay"],
        [data-testid="product-tour-spotlight"],
        [data-testid="product-tour-spotlight-ring"],
        [data-testid="product-tour-tooltip"],
        [data-product-tour] { display: none !important; }
        div.fixed.inset-0[class*="z-\\[200\\]"] { display: none !important; }
      `;
      (document.head || document.documentElement).appendChild(style);
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', inject, { once: true });
    } else {
      inject();
    }
  });
}

test.describe('README numbered screenshots', () => {
  test('recapture dashboard / projects / schedule / ai-estimate', async ({ page, request }, info) => {
    info.setTimeout(300_000);
    const token = await demoToken(request);
    await hydrate(page, token);
    mkdirSync(OUT_DIR, { recursive: true });

    for (const shot of SHOTS) {
      const url = new URL(shot.path, BASE_URL).toString();
      await page.goto(url, { waitUntil: 'load', timeout: 45_000 });
      await page.waitForLoadState('networkidle', { timeout: NETWORK_IDLE_MS }).catch(() => {});
      await page.waitForTimeout(shot.waitMs ?? SETTLE_MS);

      // Hard guard: the tour spotlight backdrop must not be visible.
      const tour = page.locator('[data-testid="product-tour-overlay"]');
      expect(await tour.isVisible().catch(() => false), `tour overlay leaked on ${shot.path}`).toBe(
        false,
      );

      const out = join(OUT_DIR, shot.file);
      await page.screenshot({ path: out, fullPage: true });
      // eslint-disable-next-line no-console
      console.log(`[readme-shots] ${shot.path} -> docs/screenshots/${shot.file}`);
    }
  });
});
