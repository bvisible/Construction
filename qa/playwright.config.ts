import { defineConfig, devices } from '@playwright/test';

/**
 * Polyglot Playwright config for all V_* verification specs.
 *
 * Run:  npx playwright test --config qa/playwright.config.ts
 * Single wave:  npx playwright test --config qa/playwright.config.ts V_HSE
 *
 * Env vars:
 *   QA_BASE_URL     — vite dev URL (default per-wave; see spec headers)
 *   QA_API_URL      — backend URL (default per-wave)
 *   QA_DEMO_EMAIL   — defaults to demo@openconstructionerp.com
 *   QA_DEMO_PASSWORD — defaults to demo (real password generated per install)
 */
export default defineConfig({
  testDir: '.',
  // Inclusive: matches V_REPORTING / V_HSE / V_TENDERING / V_PROCUREMENT / V_DESIGN /
  // any future V_* spec. Per-wave specs override BASE_URL via top-of-file constant.
  testMatch: ['V_*.spec.ts'],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  outputDir: './_pw_artifacts',
  use: {
    baseURL: process.env.QA_BASE_URL ?? 'http://127.0.0.1:5173',
    headless: true,
    actionTimeout: 5_000,
    navigationTimeout: 30_000,
    screenshot: 'only-on-failure',
    video: 'off',
    trace: 'off',
    ignoreHTTPSErrors: true,
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'mobile-chromium',
      use: { ...devices['iPhone SE'], viewport: { width: 375, height: 667 } },
      grep: /@mobile/,
    },
  ],
});
