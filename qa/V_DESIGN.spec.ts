/**
 * V_DESIGN — App-shell + design-token a11y verification.
 *
 * Cross-cutting verification suite for the fixes shipped on branch
 * `fix/design-system-a11y`:
 *   1) App-shell `button-name` (Header.tsx + Sidebar.tsx icon-only buttons).
 *   2) `color-contrast` for the two design tokens that were failing
 *      WCAG AA 4.5:1 (--oe-text-tertiary, --oe-text-quaternary).
 *
 * Runs axe-core on three highest-traffic routes that V1/V5/V6/V7/V8/V9/V10
 * verification waves repeatedly flagged for shell-level findings:
 *   /dashboard, /finance, /crm.
 *
 * Asserts:
 *   - zero `button-name` violations on every route (shell-level).
 *   - zero `color-contrast` violations on every route attributable to
 *     the bumped tokens.
 *
 * Run explicitly:
 *   npx playwright test qa/V_DESIGN.spec.ts
 *
 * Backend must be on :8021, vite dev server on :5191.
 */
import { test, expect, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import * as fs from 'node:fs';
import * as path from 'node:path';

const DEMO_USER = {
  email: process.env.E2E_USER_EMAIL ?? 'demo@openconstructionerp.com',
};

const ROUTES_UNDER_TEST = ['/dashboard', '/finance', '/crm'] as const;

async function login(page: Page): Promise<void> {
  await page.goto('/login');
  const res = await page.request.post('/api/v1/users/auth/demo-login/', {
    headers: { 'Content-Type': 'application/json' },
    data: { email: DEMO_USER.email },
  });
  if (!res.ok()) {
    throw new Error(`demo-login returned ${res.status()}`);
  }
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
    { tok: token, refresh: body.refresh_token, email: DEMO_USER.email },
  );
  await page.goto('/');
  await expect(page).not.toHaveURL(/\/login/, { timeout: 20_000 });
}

async function suppressTours(page: Page): Promise<void> {
  await page.addInitScript(() => {
    try {
      localStorage.setItem('oe.tour_completed', 'true');
      localStorage.setItem('oe_tour_completed', 'true');
    } catch {
      /* ignore */
    }
  });
}

interface RouteReport {
  route: string;
  totalViolations: number;
  buttonName: number;
  colorContrast: number;
  bySeverity: { critical: number; serious: number; moderate: number; minor: number };
  ruleSummary: Array<{ id: string; impact: string | null; nodeCount: number }>;
}

function summarize(
  route: string,
  violations: Array<{ id: string; impact?: string | null; nodes: unknown[] }>,
): RouteReport {
  const bySeverity = { critical: 0, serious: 0, moderate: 0, minor: 0 };
  let buttonName = 0;
  let colorContrast = 0;
  for (const v of violations) {
    const k = (v.impact ?? 'minor') as keyof typeof bySeverity;
    if (k in bySeverity) bySeverity[k] += v.nodes.length;
    if (v.id === 'button-name') buttonName += v.nodes.length;
    if (v.id === 'color-contrast') colorContrast += v.nodes.length;
  }
  return {
    route,
    totalViolations: violations.reduce((sum, v) => sum + v.nodes.length, 0),
    buttonName,
    colorContrast,
    bySeverity,
    ruleSummary: violations.map((v) => ({
      id: v.id,
      impact: v.impact ?? null,
      nodeCount: v.nodes.length,
    })),
  };
}

test.describe('V_DESIGN — app-shell + design-token a11y', () => {
  test.beforeEach(async ({ page }) => {
    await suppressTours(page);
    await login(page);
  });

  for (const route of ROUTES_UNDER_TEST) {
    test(`axe-core clean on ${route} — no shell button-name + no token contrast`, async ({ page }) => {
      await page.goto(route);
      // Allow lazy chunks + locale resources to settle before scanning.
      await page.waitForLoadState('networkidle');
      await page.waitForTimeout(500);

      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();

      const report = summarize(route, results.violations);

      // Persist per-route JSON so the report agent can diff before/after.
      const outDir = path.join(process.cwd(), '..', 'qa-screenshots', 'V_DESIGN');
      try {
        fs.mkdirSync(outDir, { recursive: true });
      } catch {
        /* ignore */
      }
      const slug = route.replace(/^\//, '').replace(/[^a-z0-9]/gi, '_') || 'root';
      fs.writeFileSync(
        path.join(outDir, `axe_${slug}.json`),
        JSON.stringify(report, null, 2),
      );

      // Hard asserts — fix targets these two rule families specifically.
      expect(report.buttonName, `button-name violations on ${route}`).toBe(0);
      expect(report.colorContrast, `color-contrast violations on ${route}`).toBe(0);
    });
  }
});
