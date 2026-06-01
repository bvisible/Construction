/**
 * full-app.spec.ts — route-grid screenshot QA.
 *
 * Walks a curated catalogue of ~40 application routes, demo-logs-in
 * exactly once, then captures a full-page PNG of each route into
 *   qa-report/screenshots/<YYYY-MM-DD>/<section>/<slug>.png
 *
 * Goals:
 *   1. Repeatable visual ground-truth a human (or a future Claude
 *      session) can flip through after each merge.
 *   2. Graceful degradation: a single route 500-ing must not abort the
 *      run — we capture the error frame and move on. Soft assertions
 *      collect failures into a single end-of-spec summary.
 *   3. Stable session: one demo-login at the top, tokens hydrated into
 *      localStorage via addInitScript so every navigation skips the
 *      login wall (the standard /auth/login/ endpoint is rate-limited
 *      at ~5 req/min/IP in dev, which a 40-login loop would trip).
 *
 * Run:
 *   npx playwright test --config qa/screenshots/playwright.config.ts
 *   make qa-screenshots
 */
import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { join } from 'node:path';

// ── Config ────────────────────────────────────────────────────────────
const API_URL = process.env.QA_API_URL ?? 'http://localhost:8000';
const BASE_URL = process.env.QA_BASE_URL ?? 'http://localhost:5180';
const DEMO_EMAIL = process.env.QA_DEMO_EMAIL ?? 'demo@openconstructionerp.com';

// Wave 16/17/18 parameterisation. Empty string / undefined = use app default.
//   QA_LOCALE   — i18next language code (en, de, ru, ar, ja, …) seeded into
//                 localStorage `i18nextLng` before first render.
//   QA_THEME    — light | dark | system (seeded into localStorage `oe_theme`).
//   QA_VIEWPORT — "WIDTHxHEIGHT" (e.g. "375x812"); overrides Playwright
//                 device viewport for mobile/tablet sweeps.
const FORCE_LOCALE = (process.env.QA_LOCALE ?? '').trim();
const FORCE_THEME = (process.env.QA_THEME ?? '').trim();
const FORCE_VIEWPORT = (process.env.QA_VIEWPORT ?? '').trim();

function parseViewport(spec: string): { width: number; height: number } | null {
  const m = /^(\d+)x(\d+)$/.exec(spec);
  if (!m) return null;
  return { width: parseInt(m[1], 10), height: parseInt(m[2], 10) };
}

const TODAY = new Date().toISOString().slice(0, 10); // YYYY-MM-DD
const SCREENSHOT_ROOT =
  process.env.QA_SCREENSHOT_DIR ?? join(process.cwd(), 'qa-report', 'screenshots', TODAY);

// Per-route timing budget. Pages with heavy 3D/JS chunks (BIM, Geo, BOQ
// editor) sometimes settle slowly; networkidle has a hard cap below.
const NETWORK_IDLE_MS = 15_000;
const ANIMATION_SETTLE_MS = 2_000;

// ── Route catalogue ──────────────────────────────────────────────────
// Routes verified against frontend/src/app/App.tsx (HEAD 715d9de8).
// `:tab` / `:id` placeholders are resolved from env vars or filled with
// known-good demo IDs in `resolveRoute()` below.
interface RouteSpec {
  section: string;
  slug: string;
  path: string;
  /** Optional pre-screenshot wait override (ms). */
  waitMs?: number;
}

const ROUTES: RouteSpec[] = [
  // ── Core ──
  { section: '01_core', slug: 'dashboard', path: '/dashboard' },
  { section: '01_core', slug: 'projects', path: '/projects' },
  { section: '01_core', slug: 'project_detail', path: '/projects/:projectId' },
  { section: '01_core', slug: 'files', path: '/files' },
  { section: '01_core', slug: 'notifications', path: '/notifications' },
  { section: '01_core', slug: 'about', path: '/about' },

  // ── BIM / CAD / Coordination ──
  { section: '02_bim', slug: 'bim_viewer', path: '/bim/:modelId', waitMs: 4_000 },
  { section: '02_bim', slug: 'bim_federations', path: '/bim/federations' },
  { section: '02_bim', slug: 'bim_rules', path: '/bim/rules' },
  { section: '02_bim', slug: 'coordination', path: '/coordination' },
  { section: '02_bim', slug: 'clash', path: '/clash' },
  { section: '02_bim', slug: 'requirements_matrix', path: '/requirements/matrix' },
  { section: '02_bim', slug: 'data_explorer', path: '/data-explorer' },
  { section: '02_bim', slug: 'match_elements', path: '/match-elements' },
  { section: '02_bim', slug: 'assets', path: '/assets' },

  // ── BOQ / Costs / Estimation ──
  { section: '03_estimation', slug: 'boq_list', path: '/boq' },
  { section: '03_estimation', slug: 'takeoff', path: '/takeoff' },
  { section: '03_estimation', slug: 'dwg_takeoff', path: '/dwg-takeoff' },
  { section: '03_estimation', slug: 'costs', path: '/costs' },
  { section: '03_estimation', slug: 'assemblies', path: '/assemblies' },
  { section: '03_estimation', slug: 'assembly_library', path: '/assemblies/library' },
  { section: '03_estimation', slug: 'catalog', path: '/catalog' },
  { section: '03_estimation', slug: 'quantities', path: '/quantities' },
  { section: '03_estimation', slug: 'validation', path: '/validation' },

  // ── Property Development ──
  { section: '04_propdev', slug: 'property_dev', path: '/property-dev' },
  { section: '04_propdev', slug: 'propdev_dashboards', path: '/property-dev/dashboards' },
  { section: '04_propdev', slug: 'propdev_house_types', path: '/property-dev/settings/house-types' },
  {
    section: '04_propdev',
    slug: 'propdev_doc_templates',
    path: '/property-dev/settings/document-templates',
  },
  { section: '04_propdev', slug: 'accommodation', path: '/accommodation' },
  { section: '04_propdev', slug: 'accommodation_calendar', path: '/accommodation/calendar' },

  // ── Geo / Maps ──
  { section: '05_geo', slug: 'geo_hub', path: '/geo', waitMs: 4_000 },
  { section: '05_geo', slug: 'geo_admin', path: '/geo/admin' },

  // ── Commercial ──
  { section: '06_commercial', slug: 'tendering', path: '/tendering' },
  { section: '06_commercial', slug: 'bid_management', path: '/bid-management' },
  { section: '06_commercial', slug: 'contracts', path: '/contracts' },
  { section: '06_commercial', slug: 'variations', path: '/variations' },
  { section: '06_commercial', slug: 'changeorders', path: '/changeorders' },
  { section: '06_commercial', slug: 'subcontractors', path: '/subcontractors' },
  { section: '06_commercial', slug: 'procurement', path: '/procurement' },
  { section: '06_commercial', slug: 'supplier_catalogs', path: '/supplier-catalogs' },
  { section: '06_commercial', slug: 'crm', path: '/crm' },

  // ── Field / Quality / Safety ──
  { section: '07_field', slug: 'rfi', path: '/rfi' },
  { section: '07_field', slug: 'submittals', path: '/submittals' },
  { section: '07_field', slug: 'punchlist', path: '/punchlist' },
  { section: '07_field', slug: 'field_reports', path: '/field-reports' },
  { section: '07_field', slug: 'daily_diary', path: '/daily-diary' },
  { section: '07_field', slug: 'hse_advanced', path: '/hse-advanced' },
  { section: '07_field', slug: 'qms', path: '/qms' },
  { section: '07_field', slug: 'inspections', path: '/inspections' },
  { section: '07_field', slug: 'ncr', path: '/ncr' },

  // ── Schedule / Analytics / Finance ──
  { section: '08_planning', slug: 'schedule', path: '/schedule' },
  { section: '08_planning', slug: 'schedule_advanced', path: '/schedule-advanced' },
  { section: '08_planning', slug: 'analytics', path: '/analytics' },
  { section: '08_planning', slug: 'reporting', path: '/reporting' },
  { section: '08_planning', slug: 'reports', path: '/reports' },
  { section: '08_planning', slug: 'finance', path: '/finance' },
  { section: '08_planning', slug: 'carbon', path: '/carbon' },
  { section: '08_planning', slug: 'risks', path: '/risks' },
  { section: '08_planning', slug: 'bi_dashboards', path: '/bi-dashboards' },
  { section: '08_planning', slug: 'dashboards', path: '/dashboards' },

  // ── AI ──
  { section: '09_ai', slug: 'ai_quick_estimate', path: '/ai-estimate' },
  { section: '09_ai', slug: 'ai_agents', path: '/ai-agents' },
  { section: '09_ai', slug: 'advisor', path: '/advisor' },
  { section: '09_ai', slug: 'chat', path: '/chat' },
  { section: '09_ai', slug: 'project_intelligence', path: '/project-intelligence' },

  // ── Admin / Settings ──
  { section: '10_admin', slug: 'settings', path: '/settings' },
  { section: '10_admin', slug: 'settings_converters', path: '/settings?tab=converters' },
  { section: '10_admin', slug: 'users', path: '/users' },
  { section: '10_admin', slug: 'modules', path: '/modules' },
  { section: '10_admin', slug: 'integrations', path: '/integrations' },
  { section: '10_admin', slug: 'audit_log', path: '/admin/audit-log' },
  { section: '10_admin', slug: 'permissions_matrix', path: '/admin/permissions' },
  { section: '10_admin', slug: 'validation_rules', path: '/admin/validation-rules' },
];

// QA_ROUTE_LIMIT=N → pick N routes spread across all sections (round-robin
// by section) so trimmed parametrised sweeps (locale/theme/viewport) still
// exercise core/bim/estimation/takeoff/commercial/field/planning/ai/admin.
const _routeLimit = parseInt(process.env.QA_ROUTE_LIMIT ?? '', 10);
function _pickRoundRobin(all: RouteSpec[], n: number): RouteSpec[] {
  const bySection = new Map<string, RouteSpec[]>();
  for (const r of all) {
    if (!bySection.has(r.section)) bySection.set(r.section, []);
    bySection.get(r.section)!.push(r);
  }
  const buckets = [...bySection.values()];
  const out: RouteSpec[] = [];
  for (let i = 0; out.length < n; i++) {
    let added = false;
    for (const b of buckets) {
      if (i < b.length && out.length < n) { out.push(b[i]); added = true; }
    }
    if (!added) break;
  }
  return out;
}
const ROUTES_EFFECTIVE = Number.isFinite(_routeLimit) && _routeLimit > 0
  ? _pickRoundRobin(ROUTES, _routeLimit)
  : ROUTES;

// ── Helpers ──────────────────────────────────────────────────────────
interface DemoFixtures {
  accessToken: string;
  projectId: string | null;
  bimModelId: string | null;
}

async function fetchDemoFixtures(request: APIRequestContext): Promise<DemoFixtures> {
  const loginRes = await request.post(`${API_URL}/api/v1/users/auth/demo-login/`, {
    failOnStatusCode: false,
    data: { email: DEMO_EMAIL },
  });
  if (!loginRes.ok()) {
    throw new Error(
      `demo-login failed (status=${loginRes.status()}). Backend reachable at ${API_URL}?`,
    );
  }
  const loginJson = (await loginRes.json()) as { access_token: string };
  const accessToken = loginJson.access_token;

  // Resolve demo project id (env override > first project from API).
  let projectId: string | null = process.env.QA_PROJECT_ID ?? null;
  if (!projectId) {
    const r = await request.get(`${API_URL}/api/v1/projects/`, {
      headers: { Authorization: `Bearer ${accessToken}` },
      failOnStatusCode: false,
    });
    if (r.ok()) {
      const body = (await r.json()) as unknown;
      const items: Array<{ id: string }> = Array.isArray(body)
        ? (body as Array<{ id: string }>)
        : ((body as { items?: Array<{ id: string }> }).items ?? []);
      // Prefer the second seed project (richer fixtures than BareProject_NoReqs).
      projectId = items[1]?.id ?? items[0]?.id ?? null;
    }
  }

  // Resolve demo BIM model id, scoped to the chosen project.
  let bimModelId: string | null = process.env.QA_BIM_MODEL_ID ?? null;
  if (!bimModelId && projectId) {
    const r = await request.get(
      `${API_URL}/api/v1/bim-hub/?project_id=${encodeURIComponent(projectId)}`,
      {
        headers: { Authorization: `Bearer ${accessToken}` },
        failOnStatusCode: false,
      },
    );
    if (r.ok()) {
      const body = (await r.json()) as unknown;
      const items: Array<{ id: string }> = Array.isArray(body)
        ? (body as Array<{ id: string }>)
        : ((body as { items?: Array<{ id: string }>; models?: Array<{ id: string }> }).items ??
          (body as { models?: Array<{ id: string }> }).models ??
          []);
      bimModelId = items[0]?.id ?? null;
    }
  }

  return { accessToken, projectId, bimModelId };
}

function resolveRoute(path: string, fixtures: DemoFixtures): string {
  return path
    .replace(':projectId', fixtures.projectId ?? 'unknown-project')
    .replace(':modelId', fixtures.bimModelId ?? 'unknown-model');
}

async function hydrateAuth(page: Page, accessToken: string): Promise<void> {
  const params = {
    token: accessToken,
    forceLocale: FORCE_LOCALE,
    forceTheme: FORCE_THEME,
  };
  await page.addInitScript((p) => {
    localStorage.setItem('oe_access_token', p.token);
    localStorage.setItem('oe_refresh_token', p.token);
    localStorage.setItem('oe_remember', '1');
    localStorage.setItem('oe_user_email', 'demo@openconstructionerp.com');
    // Suppress onboarding/tour overlays — they paint above page content
    // and would pollute every screenshot.
    localStorage.setItem('oe_onboarding_completed', 'true');
    localStorage.setItem('oe_welcome_dismissed', 'true');
    localStorage.setItem('oe_tour_completed', 'true');
    localStorage.setItem('oe.tour_completed', 'true');
    sessionStorage.setItem('oe_access_token', p.token);
    sessionStorage.setItem('oe_refresh_token', p.token);
    // Dismiss the public-demo modal on the hosted demo VPS
    // (see frontend/src/shared/ui/DemoBanner.tsx — gated by
    // sessionStorage key `oe_demo_modal_dismissed`). On local-dev runs
    // demo_mode is false and the key is simply ignored.
    sessionStorage.setItem('oe_demo_modal_dismissed', '1');
    // Wave 16: locale override (i18next reads `i18nextLng` from localStorage,
    // see frontend/src/app/i18n.ts ~line 146). Also flag as explicit so the
    // onboarding wizard's auto-detect doesn't overwrite us mid-flight.
    if (p.forceLocale) {
      localStorage.setItem('i18nextLng', p.forceLocale);
      localStorage.setItem('oe_lang_explicit', '1');
    }
    // Wave 17: theme override (useThemeStore reads `oe_theme`).
    if (p.forceTheme) {
      localStorage.setItem('oe_theme', p.forceTheme);
    }
  }, params);
}

/**
 * Inject CSS that hides the public-demo modal in case the React app
 * opens it before our sessionStorage seed is read (race condition: the
 * `useEffect` reads `sessionStorage` AFTER /api/system/status resolves
 * and AFTER the addInitScript has run, so this should be redundant — but
 * we keep it as defence in depth). The selector matches the modal's
 * outermost backdrop (`fixed inset-0 z-[200]`), which Tailwind compiles
 * to `.z-\[200\]` in the production stylesheet. We hide the whole
 * stacking layer so the modal contents don't bleed through.
 *
 * No-op on local dev (where the modal is never rendered) and on the
 * marketing landing page (which doesn't load the React bundle).
 */
async function injectDemoModalHiderCSS(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const css = `
      /* Hide the public-demo modal overlay (DemoBanner.tsx). */
      div.fixed.inset-0[class*="z-\\[200\\]"] {
        display: none !important;
      }
    `;
    const inject = () => {
      if (document.getElementById('__qa_demo_modal_hider')) return;
      const style = document.createElement('style');
      style.id = '__qa_demo_modal_hider';
      style.textContent = css;
      (document.head || document.documentElement).appendChild(style);
    };
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', inject, { once: true });
    } else {
      inject();
    }
  });
}

/**
 * Best-effort dismissal of the public-demo modal (see
 * frontend/src/shared/ui/DemoBanner.tsx). The addInitScript sessionStorage
 * seed (`oe_demo_modal_dismissed=1`) suppresses it on initial mount, but
 * the modal is opened from a useEffect that runs only AFTER the
 * /api/system/status query resolves — which on the hosted demo VPS can
 * happen after our `networkidle` + settle window. So we also click the
 * modal away if it appears. On local-dev runs `demo_mode=false` and the
 * modal never mounts, so this is a no-op.
 *
 * Additionally seeds sessionStorage on the live page after dismissal so
 * the modal does not re-appear if the next navigation somehow misses the
 * init script (defence in depth).
 */
async function dismissDemoModalIfPresent(page: Page): Promise<void> {
  try {
    // Re-assert sessionStorage on the live document. This is cheap and
    // covers the (theoretical) case where addInitScript ran in an early
    // origin context but the React app reads from a fresher one.
    await page
      .evaluate(() => {
        try {
          sessionStorage.setItem('oe_demo_modal_dismissed', '1');
        } catch {
          /* sandboxed about:blank — ignore */
        }
      })
      .catch(() => {});

    const btn = page.getByRole('button', { name: /I understand, continue/i });
    // Give the modal up to 1.5s to materialise after the demo-mode query
    // resolves. If it never appears (local dev, demo_mode=false), this
    // simply times out cheaply.
    if (await btn.isVisible({ timeout: 1_500 }).catch(() => false)) {
      await btn.click({ timeout: 2_000, force: true }).catch(() => {});
      await btn.waitFor({ state: 'hidden', timeout: 2_000 }).catch(() => {});
    }
  } catch {
    /* swallow — best-effort dismissal */
  }
}

interface RouteResult {
  section: string;
  slug: string;
  resolvedPath: string;
  ok: boolean;
  error?: string;
  fileBytes?: number;
}

// ── Spec ─────────────────────────────────────────────────────────────
// Wave 18: viewport override applied at the describe level so it propagates
// to the page fixture. Falls back to playwright.config.ts default if unset.
const _vp = parseViewport(FORCE_VIEWPORT);
if (_vp) {
  test.use({ viewport: _vp });
}

test.describe('Full-app screenshot grid', () => {
  test('captures every catalogued route', async ({ page, request }, testInfo) => {
    // Single test that loops every route — keeps a stable browser context
    // (one set of cookies + storage) and minimises auth chatter against
    // the backend.
    testInfo.setTimeout(1_800_000);

    const fixtures = await fetchDemoFixtures(request);
    if (!fixtures.projectId) {
      // No projects in DB → skip dynamic-id routes silently; static ones
      // still get captured.
      // eslint-disable-next-line no-console
      console.warn('[qa-screenshots] No demo project found — :projectId routes will 404.');
    }
    if (!fixtures.bimModelId) {
      // eslint-disable-next-line no-console
      console.warn('[qa-screenshots] No BIM model found — :modelId routes will show empty state.');
    }
    await hydrateAuth(page, fixtures.accessToken);
    await injectDemoModalHiderCSS(page);

    // Ensure output dir exists up-front; per-section subdirs created
    // lazily inside the loop.
    mkdirSync(SCREENSHOT_ROOT, { recursive: true });

    const results: RouteResult[] = [];

    for (const route of ROUTES_EFFECTIVE) {
      const resolvedPath = resolveRoute(route.path, fixtures);
      const sectionDir = join(SCREENSHOT_ROOT, route.section);
      mkdirSync(sectionDir, { recursive: true });
      const outFile = join(sectionDir, `${route.slug}.png`);

      const result: RouteResult = {
        section: route.section,
        slug: route.slug,
        resolvedPath,
        ok: false,
      };

      try {
        const url = new URL(resolvedPath, BASE_URL).toString();
        // Use 'load' as the navigation gate (cheap, deterministic) then
        // poll for networkidle with a soft cap — heavy pages (BIM, Geo)
        // hold sockets open indefinitely on dev servers.
        await page.goto(url, { waitUntil: 'load', timeout: 45_000 });
        await page
          .waitForLoadState('networkidle', { timeout: NETWORK_IDLE_MS })
          .catch(() => {
            /* idle timeout is benign — Cesium / WebSocket subscriptions
               can keep the network busy forever. Screenshot anyway. */
          });
        const settleMs = route.waitMs ?? ANIMATION_SETTLE_MS;
        await page.waitForTimeout(settleMs);
        // Best-effort modal dismissal AFTER settle: the DemoBanner modal
        // opens from a useEffect that runs only after /api/system/status
        // resolves, which on the hosted demo VPS can land after our
        // initial networkidle gate. Running this after settle gives the
        // modal time to mount before we try to dismiss it.
        await dismissDemoModalIfPresent(page);
        const buf = await page.screenshot({ path: outFile, fullPage: true });
        result.ok = true;
        result.fileBytes = buf.byteLength;
      } catch (err) {
        result.error = err instanceof Error ? err.message : String(err);
        // Best-effort: capture whatever the page currently shows so the
        // human reviewer can see if it was a 500, a blank screen, or a
        // mid-render hang.
        try {
          await page.screenshot({ path: outFile, fullPage: true });
        } catch {
          /* nothing more we can do */
        }
      }

      results.push(result);
      // eslint-disable-next-line no-console
      console.log(
        `[qa-screenshots] ${result.ok ? 'OK ' : 'ERR'} ${route.section}/${route.slug} → ${resolvedPath}` +
          (result.error ? ` (${result.error.slice(0, 80)})` : ''),
      );
    }

    // ── Summary ──
    const okCount = results.filter((r) => r.ok).length;
    const failCount = results.length - okCount;
    const totalBytes = results.reduce((s, r) => s + (r.fileBytes ?? 0), 0);
    // eslint-disable-next-line no-console
    console.log(
      `\n[qa-screenshots] DONE — ${okCount}/${results.length} routes, ` +
        `${(totalBytes / 1024 / 1024).toFixed(1)} MB written to ${SCREENSHOT_ROOT}`,
    );
    if (failCount > 0) {
      // eslint-disable-next-line no-console
      console.log(
        '[qa-screenshots] Failed routes:\n' +
          results
            .filter((r) => !r.ok)
            .map((r) => `  - ${r.section}/${r.slug} (${r.resolvedPath}): ${r.error ?? '?'}`)
            .join('\n'),
      );
    }

    // Soft assertion: the suite is allowed to be partially red, but at
    // least the dashboard + projects pages should render — those are
    // canaries for a totally broken environment.
    const dashboardOk = results.find((r) => r.slug === 'dashboard')?.ok;
    const projectsOk = results.find((r) => r.slug === 'projects')?.ok;
    expect(dashboardOk, 'dashboard route must render').toBe(true);
    expect(projectsOk, 'projects route must render').toBe(true);
  });
});
