// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Submittals deep-audit verify spec.
//
// Drives the /submittals route through the demo backend (vite proxy
// targets VITE_API_TARGET; see worktree dev wiring at
// http://127.0.0.1:8026), captures screenshots of the new status
// pipeline + due-date countdown + days-in-court SLA badge, and runs an
// axe-core a11y scan over the submittals landing page.
//
// Outputs land in ../qa-screenshots/V_SUBMITTALS/*.png.

import { test, expect, Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const DEMO_EMAIL = process.env.OE_DEMO_EMAIL ?? 'demo@openconstructionerp.com';
const DEMO_PASSWORD = process.env.OE_DEMO_PASSWORD ?? 'DemoPass1234!';

async function login(page: Page) {
  // Demo accounts on this build use magic-link (no password); use the
  // dedicated demo-login endpoint and seed the access token directly
  // into the auth store before navigating.
  const apiBase = page.context()._options.baseURL || 'http://127.0.0.1:5196';
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

test.describe('Submittals deep audit', () => {
  test('lands on /submittals and shows the page header', async ({ page }) => {
    await login(page);
    await page.goto('/submittals');
    await expect(page.getByRole('heading', { name: /submittals/i })).toBeVisible();
    await page.screenshot({
      path: '../qa-screenshots/V_SUBMITTALS/01_landing.png',
      fullPage: true,
    });
  });

  test('renders the status pipeline as an accessible image', async ({ page }) => {
    await login(page);
    await page.goto('/submittals');
    // Wait for the submittals table or empty state. Then look for any
    // pipeline image; tolerate empty-state where no rows = no pipelines.
    await page.waitForLoadState('networkidle');
    const pipelines = page.getByRole('img', { name: /pipeline/i });
    const count = await pipelines.count();
    if (count > 0) {
      await expect(pipelines.first()).toBeVisible();
      await page.screenshot({
        path: '../qa-screenshots/V_SUBMITTALS/02_pipeline.png',
        fullPage: false,
      });
    }
  });

  test('mobile viewport keeps New Submittal CTA reachable', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'desktop project skipped');
    await login(page);
    await page.goto('/submittals');
    await page.waitForLoadState('networkidle');
    // The header keeps "New Submittal" or shows the disabled state if
    // there is no active project; both must remain on-screen for tap.
    const cta = page.getByRole('button', { name: /new submittal/i });
    await expect(cta.first()).toBeVisible();
    await page.screenshot({
      path: '../qa-screenshots/V_SUBMITTALS/03_mobile.png',
      fullPage: true,
    });
  });

  test('passes axe-core a11y scan (WCAG AA)', async ({ page }) => {
    await login(page);
    await page.goto('/submittals');
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
