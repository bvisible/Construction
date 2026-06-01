/**
 * V_BIM_QUALITY — verify the new 4-mode render-quality segment on /bim/:id.
 *
 * Asserts:
 *   1) The radiogroup [data-testid="bim-quality-mode"] renders.
 *   2) All four buttons exist: fast / default / visual / walk.
 *   3) Default-active matches the persisted localStorage choice (or
 *      'default' on a fresh session).
 *   4) Clicking each button:
 *        a) flips aria-checked on the corresponding button,
 *        b) writes the value to localStorage['oe_bim_quality_mode'],
 *        c) does not throw a runtime error in the canvas/manager layer.
 *   5) The radiogroup has accessible role + aria-label (a11y baseline).
 *
 * Backend: :8000 (factory). Vite: :5180.
 * Run:  QA_BASE_URL=http://127.0.0.1:5180 npx playwright test --config qa/playwright.config.ts qa/V_BIM_QUALITY.spec.ts
 */
import { test, expect, type Page } from '@playwright/test';

const DEMO_EMAIL = process.env.E2E_USER_EMAIL ?? 'demo@openconstructionerp.com';
const MODES = ['fast', 'default', 'visual', 'walk'] as const;

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  const res = await page.request.post('/api/v1/users/auth/demo-login/', {
    headers: { 'Content-Type': 'application/json' },
    data: { email: DEMO_EMAIL },
  });
  if (!res.ok()) throw new Error(`demo-login returned ${res.status()}`);
  const body = await res.json();
  const token = body.access_token as string | undefined;
  if (!token) throw new Error('demo-login response missing access_token');
  await page.evaluate(
    ({ tok, refresh, email }: { tok: string; refresh?: string; email: string }) => {
      sessionStorage.setItem('oe_access_token', tok);
      localStorage.setItem('oe_access_token', tok);
      if (refresh) {
        sessionStorage.setItem('oe_refresh_token', refresh);
        localStorage.setItem('oe_refresh_token', refresh);
      }
      localStorage.setItem('oe_user_email', email);
    },
    { tok: token, refresh: body.refresh_token, email: DEMO_EMAIL },
  );
  await page.goto('/');
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
}

test.describe('BIM render-quality segment', () => {
  test('renders, swaps modes, and persists choice', async ({ page }) => {
    const consoleErrors: string[] = [];
    page.on('pageerror', (err) => consoleErrors.push(String(err)));
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });

    await login(page);

    // Clear any stale quality-mode preference from a prior run so we
    // start the assertion chain from a known state.
    await page.evaluate(() => localStorage.removeItem('oe_bim_quality_mode'));

    // Navigate to the BIM hub and open the first model card.
    await page.goto('/bim');
    const firstCard = page
      .locator('[data-testid^="bim-model-card-"], a[href^="/bim/"]')
      .first();
    await firstCard.waitFor({ state: 'visible', timeout: 30_000 });
    await firstCard.click();

    // Wait for the viewer toolbar (color-by select is the closest
    // landmark — same toolbar row as our new segment).
    await page.locator('[data-testid="bim-color-mode-select"]').waitFor({
      state: 'visible',
      timeout: 30_000,
    });

    // The segment itself.
    const segment = page.locator('[data-testid="bim-quality-mode"]');
    await expect(segment).toBeVisible();
    await expect(segment).toHaveAttribute('role', 'radiogroup');
    await expect(segment).toHaveAttribute('aria-label', /quality/i);

    // All four buttons.
    for (const mode of MODES) {
      const btn = page.locator(`[data-testid="bim-quality-${mode}"]`);
      await expect(btn, `mode button "${mode}" must render`).toBeVisible();
      await expect(btn).toHaveAttribute('role', 'radio');
    }

    // Fresh session = 'default' active.
    await expect(
      page.locator('[data-testid="bim-quality-default"]'),
    ).toHaveAttribute('aria-checked', 'true');

    // Click each mode, verify aria-checked flip + localStorage persistence.
    for (const mode of MODES) {
      await page.locator(`[data-testid="bim-quality-${mode}"]`).click();
      await expect(
        page.locator(`[data-testid="bim-quality-${mode}"]`),
      ).toHaveAttribute('aria-checked', 'true');

      const stored = await page.evaluate(() =>
        localStorage.getItem('oe_bim_quality_mode'),
      );
      expect(stored, `localStorage value after clicking "${mode}"`).toBe(mode);
    }

    // Sanity: no uncaught errors from SceneManager / ElementManager.
    const relevant = consoleErrors.filter(
      (e) =>
        !/Failed to load resource|favicon|sourcemap|404|net::ERR_/i.test(e),
    );
    expect(relevant, 'no JS runtime errors during mode swaps').toEqual([]);
  });
});
