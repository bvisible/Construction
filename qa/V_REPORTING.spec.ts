// Wave V_REPORTING — /reports panel smoke. Verifies the new
// <GeneratedReportsHistory> panel mounts on /reports and the builder
// preset flow still works. Run via qa/playwright.config.ts.

import { test, expect } from '@playwright/test';
import path from 'node:path';

const DEMO_EMAIL = process.env.OE_TEST_DEMO_EMAIL ?? 'demo@openconstructionerp.com';
const DEMO_PASSWORD = process.env.OE_TEST_DEMO_PASSWORD ?? 'demo';
const SHOTS = path.resolve(__dirname, '..', 'qa-screenshots', 'V_REPORTING');

test.beforeEach(async ({ page, request }) => {
  const res = await request.post('/api/v1/users/auth/demo-login/', {
    data: { email: DEMO_EMAIL, password: DEMO_PASSWORD },
  });
  if (res.ok()) {
    const body = await res.json();
    const token = body.access_token ?? body.token;
    if (token) {
      await page.addInitScript((t) => {
        window.localStorage.setItem(
          'oe-auth',
          JSON.stringify({ state: { accessToken: t }, version: 0 }),
        );
      }, token);
    }
  }
});

test('@reporting reports page renders history panel', async ({ page }) => {
  await page.goto('/reports');
  await expect(page.getByRole('heading', { name: /Reports/i }).first()).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, '01-reports-landing.png'), fullPage: true });

  const historyPanel = page.getByTestId('generated-reports-history');
  await expect(historyPanel).toBeVisible({ timeout: 15_000 });
  await page.screenshot({ path: path.join(SHOTS, '02-history-panel.png'), fullPage: true });

  const hasRows = await page.getByTestId('history-row').count();
  const hasEmpty = await page.getByText(/No reports generated yet/i).count();
  expect(hasRows + hasEmpty).toBeGreaterThan(0);
});

test('@reporting custom builder preset selects sections', async ({ page }) => {
  await page.goto('/reports');
  await page.getByRole('button', { name: /Configure Sections/i }).click();
  await page.getByRole('button', { name: /Monthly Progress/i }).click();
  await expect(page.getByRole('button', { name: /Generate Report/i })).toBeVisible();
  await page.screenshot({ path: path.join(SHOTS, '03-builder-preset.png'), fullPage: true });
});
