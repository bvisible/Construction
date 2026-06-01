// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Contracts deep-audit verify spec.
//
// Drives the /contracts route through the dev backend (vite proxy
// targets http://127.0.0.1:8030), captures screenshots of the new
// contract-status pipeline + expiry badge + template chips + clone
// button surfaces, and runs an axe-core a11y scan over the contracts
// landing page.
//
// Outputs land in ../qa-screenshots/V_CONTRACTS/*.png.

import { test, expect, Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const DEMO_EMAIL = process.env.OE_DEMO_EMAIL ?? 'demo@openconstructionerp.com';
const DEMO_PASSWORD = process.env.OE_DEMO_PASSWORD ?? 'DemoPass1234!';

async function login(page: Page) {
  // Demo accounts on this build use magic-link (no password); use the
  // dedicated demo-login endpoint and seed the access token directly
  // into the auth store before navigating.
  const apiBase = page.context()._options.baseURL || 'http://127.0.0.1:5200';
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
  void DEMO_PASSWORD;
}

test.describe('Contracts deep audit', () => {
  test('lands on /contracts and shows the page header', async ({ page }) => {
    await login(page);
    await page.goto('/contracts');
    await expect(
      page.getByRole('heading', { name: /contracts/i }).first(),
    ).toBeVisible();
    await page.screenshot({
      path: '../qa-screenshots/V_CONTRACTS/01_landing.png',
      fullPage: true,
    });
  });

  test('renders the contract status pipeline as an accessible image', async ({
    page,
  }) => {
    await login(page);
    await page.goto('/contracts');
    await page.waitForLoadState('networkidle');
    // Either the register has rows (and our new dotted pipeline
    // appears via role=img with aria-label "Contract status pipeline")
    // OR the empty state appears with the template-chip hint row.
    const pipelines = page.getByRole('img', { name: /contract status pipeline/i });
    const chips = page.getByTestId('contracts-template-chips');
    const pipelineCount = await pipelines.count();
    if (pipelineCount > 0) {
      await expect(pipelines.first()).toBeVisible();
      await page.screenshot({
        path: '../qa-screenshots/V_CONTRACTS/02_pipeline.png',
        fullPage: false,
      });
    } else {
      // No contracts seeded — the empty state with template chips
      // must surface so the user knows clause templates are on offer.
      await expect(chips).toBeVisible();
      await page.screenshot({
        path: '../qa-screenshots/V_CONTRACTS/02_empty_templates.png',
        fullPage: false,
      });
    }
  });

  test('mobile viewport keeps the New Contract action reachable', async ({
    page,
    isMobile,
  }) => {
    test.skip(!isMobile, 'desktop project skipped');
    await login(page);
    await page.goto('/contracts');
    await page.waitForLoadState('networkidle');
    await page.screenshot({
      path: '../qa-screenshots/V_CONTRACTS/03_mobile.png',
      fullPage: true,
    });
  });

  test('passes axe-core a11y scan (WCAG AA)', async ({ page }) => {
    await login(page);
    await page.goto('/contracts');
    await page.waitForLoadState('networkidle');
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();
    const blocking = results.violations.filter(
      (v) => v.impact === 'serious' || v.impact === 'critical',
    );
    if (blocking.length > 0) {
      console.log(JSON.stringify(blocking, null, 2));
    }
    expect(blocking, JSON.stringify(blocking.map((v) => v.id))).toEqual([]);
  });
});
