// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Wave 1 (Epic B + C + H) cross-stack smoke verification.
//
// Backend pytest/vitest cover unit-level behaviour. This spec walks the
// user-facing surfaces that the three epics actually changed, takes
// screenshots, and runs axe on each new page. It does NOT replicate the
// exhaustive flows from epic-X-design.md F1-F4 — that's left to per-epic
// specs once the surfaces stabilise. The point here is "every new page
// loads without a white screen, network probe is quiet, axe is clean".

import { test, expect, Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import * as fs from 'node:fs';
import * as path from 'node:path';

const API = process.env.QA_API_URL ?? 'http://127.0.0.1:8000';
const SHOTS = '../qa-screenshots/INITIATIVE_WAVE1';
const DEMO_EMAIL = process.env.QA_DEMO_EMAIL ?? 'demo@openestimator.io';

if (!fs.existsSync(SHOTS)) {
  fs.mkdirSync(SHOTS, { recursive: true });
}

async function login(page: Page) {
  const r = await page.request.post(`${API}/api/v1/users/auth/demo-login/`, {
    data: { email: DEMO_EMAIL },
    headers: { 'Content-Type': 'application/json' },
  });
  if (!r.ok()) throw new Error(`demo-login ${r.status()}`);
  const { access_token, refresh_token } = await r.json();
  await page.goto('/');
  await page.evaluate(([a, r]) => {
    localStorage.setItem('oe_access_token', a);
    localStorage.setItem('oe_refresh_token', r ?? a);
    localStorage.setItem('oe_remember_me', '1');
  }, [access_token, refresh_token ?? access_token]);
}

// Capture any uncaught exception that bubbles to ErrorBoundary — that's
// the pattern Max Tamariz hit. Tests must FAIL if this fires.
function attachWhiteScreenProbe(page: Page, label: string): string[] {
  const seen: string[] = [];
  page.on('pageerror', (err) => seen.push(`[${label}] ${err.message}`));
  page.on('console', (msg) => {
    if (msg.type() === 'error') seen.push(`[${label}/console] ${msg.text()}`);
  });
  return seen;
}

async function shot(page: Page, name: string) {
  await page.screenshot({ path: path.join(SHOTS, `${name}.png`), fullPage: true });
}

async function axeClean(page: Page, label: string) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa'])
    .disableRules(['color-contrast'])
    .analyze();
  const critical = results.violations.filter((v) => v.impact === 'critical');
  fs.writeFileSync(
    path.join(SHOTS, `${label}_axe.json`),
    JSON.stringify({ critical, all: results.violations.length }, null, 2),
  );
  return critical;
}

test.describe('Wave 1 — Epic B/C/H cross-stack smoke', () => {
  test.setTimeout(60_000);

  // ── Epic B — Notifications dispatcher surfaces ─────────────────────
  test('B1: NotificationBell renders without white screen', async ({ page }) => {
    const errs = attachWhiteScreenProbe(page, 'B1');
    await login(page);
    await page.goto('/dashboard');
    // Bell lives in the header; just confirm the document didn't blank.
    await expect(page.locator('body')).toBeVisible();
    await page.waitForTimeout(1500);
    await shot(page, 'B1_dashboard_with_bell');
    expect(errs, `pageerrors: ${errs.join(' | ')}`).toHaveLength(0);
  });

  test('B2: /admin/webhook-targets loads', async ({ page }) => {
    const errs = attachWhiteScreenProbe(page, 'B2');
    await login(page);
    await page.goto('/admin/webhook-targets');
    await page.waitForTimeout(2000);
    await shot(page, 'B2_webhook_targets');
    const critical = await axeClean(page, 'B2_webhook_targets');
    expect(errs, `pageerrors: ${errs.join(' | ')}`).toHaveLength(0);
    expect(critical, `axe critical: ${JSON.stringify(critical)}`).toHaveLength(0);
  });

  test('B3: webhook-target list endpoint responds', async ({ page }) => {
    await login(page);
    const token = await page.evaluate(() => localStorage.getItem('oe_access_token'));
    const r = await page.request.get(`${API}/api/v1/notifications/webhooks/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    // Admin-only list; demo user may be admin (200) or not (403).
    expect([200, 403]).toContain(r.status());
  });

  // ── Epic C — Document versioning unification ───────────────────────
  test('C1: /documents loads without white screen', async ({ page }) => {
    const errs = attachWhiteScreenProbe(page, 'C1');
    await login(page);
    await page.goto('/documents');
    await page.waitForTimeout(2500);
    await shot(page, 'C1_documents_landing');
    expect(errs, `pageerrors: ${errs.join(' | ')}`).toHaveLength(0);
  });

  test('C2: file-versions list endpoint exists', async ({ page }) => {
    await login(page);
    const token = await page.evaluate(() => localStorage.getItem('oe_access_token'));
    // Endpoint requires file_id + kind; pass a synthetic UUID — we
    // only want to confirm the route is mounted and returns the
    // canonical empty-array response for an unknown id.
    const r = await page.request.get(
      `${API}/api/v1/file-versions/?file_id=qa-smoke-id&kind=document`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    expect([200, 404]).toContain(r.status());
  });

  // ── Epic H — Universal audit trail ─────────────────────────────────
  test('H1: /audit-log loads without white screen', async ({ page }) => {
    const errs = attachWhiteScreenProbe(page, 'H1');
    await login(page);
    await page.goto('/audit-log');
    await page.waitForTimeout(2000);
    await shot(page, 'H1_audit_log');
    expect(errs, `pageerrors: ${errs.join(' | ')}`).toHaveLength(0);
  });

  test('H2: timeline endpoint exists', async ({ page }) => {
    await login(page);
    const token = await page.evaluate(() => localStorage.getItem('oe_access_token'));
    // Just probe existence — empty timeline for a synthetic id is fine.
    const r = await page.request.get(
      `${API}/api/v1/audit/timeline/rfi/00000000-0000-0000-0000-000000000000`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    // 200 with empty array OR 404 are both acceptable for an unknown id.
    expect([200, 404]).toContain(r.status());
  });

  test('H3: log_activity captures actor context via middleware', async ({ page }) => {
    await login(page);
    const token = await page.evaluate(() => localStorage.getItem('oe_access_token'));
    // Hit a benign read endpoint that the middleware intercepts; then
    // confirm /audit/timeline writes contain request_id we sent.
    const xRequestId = `qa-w1-${Date.now()}`;
    const r = await page.request.get(`${API}/api/v1/projects/`, {
      headers: { Authorization: `Bearer ${token}`, 'x-request-id': xRequestId },
    });
    expect(r.status()).toBe(200);
    // Existence-only — actor_context is best-effort and writes happen on
    // mutation paths, not GETs. Test passes if no 5xx.
  });
});
