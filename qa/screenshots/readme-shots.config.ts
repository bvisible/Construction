import { defineConfig, devices } from '@playwright/test';

/**
 * Config for readme-shots.spec.ts — the focused recapture of the four
 * numbered README screenshots. Kept separate from playwright.config.ts so
 * the full-app testMatch does not pull in this spec (and vice versa).
 *
 * Run:
 *   QA_API_URL=http://127.0.0.1:8080 QA_BASE_URL=http://127.0.0.1:8080 \
 *     npx playwright test --config qa/screenshots/readme-shots.config.ts
 */
export default defineConfig({
  testDir: '.',
  testMatch: ['readme-shots.spec.ts'],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 300_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  outputDir: './_pw_artifacts_readme',
  use: {
    baseURL: process.env.QA_BASE_URL ?? 'http://127.0.0.1:8080',
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
