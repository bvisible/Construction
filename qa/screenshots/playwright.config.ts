import { defineConfig, devices } from '@playwright/test';

/**
 * Standalone Playwright config for the route-grid screenshot QA suite.
 *
 * Deliberately does NOT extend qa/playwright.config.ts (the polyglot
 * V_*.spec.ts harness) — that config is do-not-modify and its testMatch
 * pattern `V_*.spec.ts` would skip our `full-app.spec.ts`. Keeping this
 * config local to qa/screenshots/ avoids cross-coupling.
 *
 * Run:
 *   npx playwright test --config qa/screenshots/playwright.config.ts
 *   make qa-screenshots          # equivalent
 *
 * Env vars:
 *   QA_BASE_URL      — frontend URL (default http://localhost:5180,
 *                      falls back to 5173 if 5180 is unreachable —
 *                      see full-app.spec.ts).
 *   QA_API_URL       — backend URL (default http://localhost:8000)
 *   QA_DEMO_EMAIL    — demo account (default demo@openconstructionerp.com)
 *   QA_PROJECT_ID    — demo project id (defaults to first project
 *                      returned by /api/v1/projects/).
 *   QA_BIM_MODEL_ID  — demo BIM model id (defaults to first model
 *                      returned by /api/v1/bim-hub/?project_id=...).
 *   QA_SCREENSHOT_DIR — override screenshot output dir (default
 *                       qa-report/screenshots/<YYYY-MM-DD>/).
 */
export default defineConfig({
  testDir: '.',
  testMatch: ['full-app.spec.ts'],
  // The screenshot suite is intentionally serial: the same demo account
  // navigates through every route; running parallel workers against one
  // session is fragile and produces duplicate auth requests that trip
  // the backend's login rate-limiter.
  fullyParallel: false,
  workers: 1,
  retries: 0,
  // Generous timeout: ~70 routes × ~13 s each (measured) = ~15 min,
  // plus headroom for cold backend / heavy 3D pages (Cesium, BIM viewer).
  timeout: 1_800_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  outputDir: './_pw_artifacts',
  use: {
    baseURL: process.env.QA_BASE_URL ?? 'http://localhost:5180',
    headless: true,
    actionTimeout: 10_000,
    navigationTimeout: 45_000,
    // Screenshots are taken explicitly inside the spec; we still let
    // Playwright capture a failure artefact so flaky routes are
    // diagnosable from the run output.
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
