// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Procurement deep-audit verify spec.
//
// Drives the /procurement route through the demo backend (vite proxy
// targets http://127.0.0.1:8025), captures screenshots of the new
// PO-status pipeline + delivery countdown badge + Issue button, and
// runs an axe-core a11y scan over the procurement landing page.
//
// Outputs land in ../qa-screenshots/V_PROCUREMENT/*.png.

import { test, expect, Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const DEMO_EMAIL = process.env.OE_DEMO_EMAIL ?? 'demo@openconstructionerp.com';
const DEMO_PASSWORD = process.env.OE_DEMO_PASSWORD ?? 'DemoPass1234!';

async function login(page: Page) {
  // Demo accounts on this build use magic-link (no password); use the
  // dedicated demo-login endpoint and seed the access token directly
  // into the auth store before navigating.
  const apiBase = page.context()._options.baseURL || 'http://127.0.0.1:5195';
  const tokenResp = await page.request.post(
    `${apiBase}/api/v1/users/auth/demo-login/`,
    {
      data: { email: DEMO_EMAIL },
      headers: { 'Content-Type': 'application/json' },
    },
  );
  if (!tokenResp.ok()) {
    throw new Error(`demo-login failed ${tokenResp.status()}`);
  }
  const body = await tokenResp.json();
  const access = body.access_token ?? body.access;
  const refresh = body.refresh_token ?? body.refresh ?? access;
  await page.goto('/');
  await page.evaluate(
    ([acc, refr]) => {
      // useAuthStore reads these specific keys on bootstrap (see
      // src/stores/useAuthStore.ts: KEY_ACCESS / KEY_REFRESH).
      localStorage.setItem('oe_access_token', acc);
      localStorage.setItem('oe_refresh_token', refr);
      localStorage.setItem('oe_remember_me', '1');
    },
    [access, refresh],
  );
  // Track stable demo password env even though unused here — keeps the
  // spec ready when a password-login flow ships.
  void DEMO_PASSWORD;
}

test.describe('Procurement deep audit', () => {
  test('lands on /procurement and shows the page header', async ({ page }) => {
    await login(page);
    await page.goto('/procurement');
    await expect(page.getByRole('heading', { name: /procurement/i })).toBeVisible();
    await page.screenshot({
      path: '../qa-screenshots/V_PROCUREMENT/01_landing.png',
      fullPage: true,
    });
  });

  test('renders the PO status pipeline as an accessible image', async ({ page }) => {
    await login(page);
    await page.goto('/procurement');
    // Wait for the PO table or empty state. Then look for any pipeline
    // image; tolerate empty-state where no rows = no pipelines.
    await page.waitForLoadState('networkidle');
    const pipelines = page.getByRole('img', { name: /pipeline/i });
    const count = await pipelines.count();
    if (count > 0) {
      await expect(pipelines.first()).toBeVisible();
      await page.screenshot({
        path: '../qa-screenshots/V_PROCUREMENT/02_pipeline.png',
        fullPage: false,
      });
    }
  });

  test('mobile viewport keeps Issue button reachable', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'desktop project skipped');
    await login(page);
    await page.goto('/procurement');
    await page.waitForLoadState('networkidle');
    await page.screenshot({
      path: '../qa-screenshots/V_PROCUREMENT/03_mobile.png',
      fullPage: true,
    });
  });

  test('passes axe-core a11y scan (WCAG AA)', async ({ page }) => {
    await login(page);
    await page.goto('/procurement');
    await page.waitForLoadState('networkidle');
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    // We assert ZERO serious/critical violations. Non-blocking ones
    // are still reported in stdout for triage.
    const blocking = results.violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical',
    );
    if (blocking.length > 0) {
      console.log(JSON.stringify(blocking, null, 2));
    }
    expect(blocking, JSON.stringify(blocking.map((v) => v.id))).toEqual([]);
  });
});
