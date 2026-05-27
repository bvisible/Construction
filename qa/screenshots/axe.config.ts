import { defineConfig, devices } from '@playwright/test';

/**
 * Standalone Playwright config for the axe a11y sweep
 * (axe-sweep.spec.ts). Mirrors playwright.config.ts but matches the axe spec.
 */
export default defineConfig({
  testDir: '.',
  testMatch: ['axe-sweep.spec.ts'],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 1_800_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  outputDir: './_pw_artifacts',
  use: {
    baseURL: process.env.QA_BASE_URL ?? 'http://localhost:5180',
    headless: true,
    actionTimeout: 10_000,
    navigationTimeout: 45_000,
    screenshot: 'only-on-failure',
    video: 'off',
    trace: 'off',
    ignoreHTTPSErrors: true,
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: 'desktop-chromium',
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
  ],
});
