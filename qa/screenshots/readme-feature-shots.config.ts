import { defineConfig, devices } from '@playwright/test';

/** Config for readme-feature-shots.spec.ts (Key Features section recapture). */
export default defineConfig({
  testDir: '.',
  testMatch: ['readme-feature-shots.spec.ts'],
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 300_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  outputDir: './_pw_artifacts_feat',
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
