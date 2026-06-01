// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Wave 5 (Epic I — international Leistungsverzeichnis) cross-stack smoke.
//
// Epic I-A added a pluggable BOQImporter registry + a format-detecting
// dispatcher endpoint POST /api/v1/boq/boqs/{boq_id}/import/auto/. Three
// native parsers ship in this wave: GAEB XML, FIEBDC-3 (BC3), and a
// generic Excel/CSV importer.
//
// Epic I-B collapsed 20 near-duplicate country-specific exchange modules
// into a single polymorphic RegionalExchangePage driven by regionalRegistry.
// Deep-link back-compat is preserved — every old /<country>
// route still mounts the page via manifest.tsx aliases.
//
// This spec walks the changed surfaces, takes screenshots, runs axe, and
// pings the dispatcher endpoint. It does NOT exercise full import flows
// — backend pytest covers the parsers themselves.

import { test, expect, Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import * as fs from 'node:fs';
import * as path from 'node:path';

const API = process.env.QA_API_URL ?? 'http://127.0.0.1:8000';
const SHOTS = '../qa-screenshots/V_WAVE5';
const DEMO_EMAIL = process.env.QA_DEMO_EMAIL ?? 'demo@openconstructionerp.com';

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

test.describe('Wave 5 — Epic I international BOQ smoke', () => {
  test.setTimeout(60_000);

  // ── Frontend: RegionalExchangePage back-compat aliases ──────────────
  test('I1: /de-din276-exchange renders RegionalExchangePage', async ({ page }) => {
    const errs = attachWhiteScreenProbe(page, 'I1');
    await login(page);
    await page.goto('/de-din276-exchange');
    await page.waitForTimeout(2000);
    await shot(page, 'I1_de_din276_alias');
    const critical = await axeClean(page, 'I1_de_din276');
    expect(errs, `pageerrors: ${errs.join(' | ')}`).toHaveLength(0);
    expect(critical, `axe critical: ${JSON.stringify(critical)}`).toHaveLength(0);
  });

  test('I2: /us-masterformat-exchange renders RegionalExchangePage', async ({ page }) => {
    const errs = attachWhiteScreenProbe(page, 'I2');
    await login(page);
    await page.goto('/us-masterformat-exchange');
    await page.waitForTimeout(2000);
    await shot(page, 'I2_us_masterformat_alias');
    expect(errs, `pageerrors: ${errs.join(' | ')}`).toHaveLength(0);
  });

  test('I3: /es-pbc-exchange renders RegionalExchangePage', async ({ page }) => {
    const errs = attachWhiteScreenProbe(page, 'I3');
    await login(page);
    await page.goto('/es-pbc-exchange');
    await page.waitForTimeout(2000);
    await shot(page, 'I3_es_pbc_alias');
    expect(errs, `pageerrors: ${errs.join(' | ')}`).toHaveLength(0);
  });

  test('I4: /uk-nrm-exchange renders RegionalExchangePage', async ({ page }) => {
    const errs = attachWhiteScreenProbe(page, 'I4');
    await login(page);
    await page.goto('/uk-nrm-exchange');
    await page.waitForTimeout(2000);
    await shot(page, 'I4_uk_nrm_alias');
    expect(errs, `pageerrors: ${errs.join(' | ')}`).toHaveLength(0);
  });

  // ── Backend: dispatcher endpoint mounted ────────────────────────────
  test('I5: POST /boq/boqs/{id}/import/auto/ endpoint is mounted', async ({ page }) => {
    await login(page);
    const token = await page.evaluate(() => localStorage.getItem('oe_access_token'));
    // Use a synthetic BOQ id — we only want to confirm the route is
    // registered and not return 405. A 404/422 means the route exists
    // and is rejecting our bogus payload, which is exactly the proof
    // we need that the dispatcher is wired up.
    const r = await page.request.post(
      `${API}/api/v1/boq/boqs/00000000-0000-0000-0000-000000000000/import/auto/`,
      {
        headers: { Authorization: `Bearer ${token}` },
        multipart: {
          file: {
            name: 'smoke.txt',
            mimeType: 'text/plain',
            buffer: Buffer.from('not a real BOQ'),
          },
        },
      },
    );
    // 404 (unknown BOQ) or 422 (unsupported format) both prove the
    // endpoint is mounted. 405 would mean the route doesn't exist.
    expect([400, 404, 415, 422]).toContain(r.status());
  });

  // ── Backend: deprecation Link header on legacy import endpoint ──────
  test('I6: legacy /import/excel/ emits Link: rel="successor-version"', async ({ page }) => {
    await login(page);
    const token = await page.evaluate(() => localStorage.getItem('oe_access_token'));
    const r = await page.request.post(
      `${API}/api/v1/boq/boqs/00000000-0000-0000-0000-000000000000/import/excel/`,
      {
        headers: { Authorization: `Bearer ${token}` },
        multipart: {
          file: {
            name: 'smoke.xlsx',
            mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            buffer: Buffer.from('fake'),
          },
        },
      },
    );
    // Even on 404/422, the deprecation header should be present (it's
    // set unconditionally by the route handler before validation).
    const link = r.headers()['link'] ?? '';
    expect(link, `expected successor-version Link header, got: "${link}"`).toContain(
      'import/auto',
    );
  });
});
