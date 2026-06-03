/**
 * readme-feature-shots.spec.ts — recapture the README "Key Features" images
 * so each section shows its OWN screen.
 *
 * The numbered PNGs were reused under the wrong headings: Property Development
 * showed the generic projects list, the ERP chat section showed AI Estimate,
 * the coordination section showed the dashboard, and the 4D schedule section
 * showed the schedule project-picker rather than a Gantt. This captures the
 * actual page behind each heading into docs/screenshots/_feat_out/ so the
 * results can be inspected before they replace the README images.
 *
 * Run (backend serves API + built SPA on :8080):
 *   QA_API_URL=http://127.0.0.1:8080 QA_BASE_URL=http://127.0.0.1:8080 \
 *     npx playwright test --config qa/screenshots/readme-feature-shots.config.ts
 */
import { test, type APIRequestContext, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

const API_URL = process.env.QA_API_URL ?? 'http://127.0.0.1:8080';
const BASE_URL = process.env.QA_BASE_URL ?? 'http://127.0.0.1:8080';
const DEMO_EMAIL = process.env.QA_DEMO_EMAIL ?? 'demo@openconstructionerp.com';

const OUT_DIR = join(process.cwd(), 'docs', 'screenshots', '_feat_out');

const NETWORK_IDLE_MS = 12_000;
const SETTLE_MS = 3_000;

// Candidate routes per mismatched section. Some sections get two candidates so
// the best can be picked after inspection.
const SHOTS: Array<{ path: string; file: string; waitMs?: number }> = [
  { path: '/property-dev', file: 'propdev.png' },
  { path: '/property-dev/dashboards', file: 'propdev-dashboards.png' },
  { path: '/coordination', file: 'coordination.png' },
  { path: '/clash', file: 'clash.png' },
  { path: '/chat', file: 'chat.png' },
  { path: '/schedule', file: 'schedule.png' },
  { path: '/schedule-advanced', file: 'schedule-advanced.png' },
];

async function demoToken(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${API_URL}/api/v1/users/auth/demo-login/`, {
    failOnStatusCode: false,
    data: { email: DEMO_EMAIL },
  });
  if (!res.ok()) {
    throw new Error(`demo-login failed (status=${res.status()}); backend at ${API_URL}?`);
  }
  return ((await res.json()) as { access_token: string }).access_token;
}

async function firstProjectId(request: APIRequestContext, token: string): Promise<string | null> {
  const r = await request.get(`${API_URL}/api/v1/projects/`, {
    headers: { Authorization: `Bearer ${token}` },
    failOnStatusCode: false,
  });
  if (!r.ok()) return null;
  const body = (await r.json()) as unknown;
  const items: Array<{ id: string }> = Array.isArray(body)
    ? (body as Array<{ id: string }>)
    : ((body as { items?: Array<{ id: string }> }).items ?? []);
  return items[1]?.id ?? items[0]?.id ?? null;
}

async function hydrate(page: Page, token: string): Promise<void> {
  await page.addInitScript((t) => {
    localStorage.setItem('oe_access_token', t);
    localStorage.setItem('oe_refresh_token', t);
    localStorage.setItem('oe_remember', '1');
    localStorage.setItem('oe_user_email', 'demo@openconstructionerp.com');
    localStorage.setItem('oe_onboarding_completed', 'true');
    localStorage.setItem('oe_welcome_dismissed', 'true');
    localStorage.setItem('oe_tour_completed', 'true');
    localStorage.setItem('oe.tour_completed', 'true');
    for (const id of ['global', 'boq', 'accommodation', 'bim', 'geo', 'propdev', 'dashboard']) {
      localStorage.setItem(`oe.tour_completed.${id}`, 'true');
    }
    localStorage.setItem('oe.last_seen_version', '9999.0.0');
    localStorage.setItem('oe.v6_pg_notice_dismissed', '1');
    sessionStorage.setItem('oe_access_token', t);
    sessionStorage.setItem('oe_refresh_token', t);
    sessionStorage.setItem('oe_demo_modal_dismissed', '1');
  }, token);

  await page.addInitScript(() => {
    const inject = () => {
      if (document.getElementById('__qa_overlay_hider')) return;
      const style = document.createElement('style');
      style.id = '__qa_overlay_hider';
      style.textContent = `
        [data-testid="product-tour-overlay"],
        [data-testid="product-tour-spotlight"],
        [data-testid="product-tour-spotlight-ring"],
        [data-testid="product-tour-tooltip"],
        [data-product-tour] { display: none !important; }
        div.fixed.inset-0[class*="z-\\[200\\]"] { display: none !important; }
      `;
      (document.head || document.documentElement).appendChild(style);
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', inject, { once: true });
    } else {
      inject();
    }
  });
}

test.describe('README feature screenshots', () => {
  test('recapture section pages', async ({ page, request }, info) => {
    info.setTimeout(300_000);
    const token = await demoToken(request);
    const projectId = await firstProjectId(request, token);
    await hydrate(page, token);
    mkdirSync(OUT_DIR, { recursive: true });

    const shots = [...SHOTS];
    if (projectId) {
      // A project-scoped schedule should render an actual Gantt instead of
      // the project-picker landing.
      shots.push({ path: `/projects/${projectId}/schedule`, file: 'project-schedule.png', waitMs: 4000 });
      shots.push({ path: `/projects/${projectId}`, file: 'project-detail.png' });
    }

    for (const shot of shots) {
      try {
        const url = new URL(shot.path, BASE_URL).toString();
        await page.goto(url, { waitUntil: 'load', timeout: 45_000 });
        await page.waitForLoadState('networkidle', { timeout: NETWORK_IDLE_MS }).catch(() => {});
        await page.waitForTimeout(shot.waitMs ?? SETTLE_MS);
        await page.screenshot({ path: join(OUT_DIR, shot.file), fullPage: true });
        // eslint-disable-next-line no-console
        console.log(`[feat] ${shot.path} -> _feat_out/${shot.file}`);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn(`[feat] FAILED ${shot.path}: ${(err as Error).message}`);
      }
    }
  });
});
