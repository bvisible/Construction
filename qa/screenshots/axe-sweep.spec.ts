/**
 * axe-sweep.spec.ts — accessibility sweep over the route grid.
 *
 * Mirrors the route catalogue used by full-app.spec.ts, but instead of
 * capturing screenshots it runs @axe-core/playwright's `AxeBuilder.analyze()`
 * against each route and aggregates the violations into a single JSON
 * report at `qa-report/axe-results-<YYYY-MM-DD>.json`.
 *
 * Output schema:
 *   {
 *     baseUrl: "https://…",
 *     locale: "en",
 *     totalRoutes: 70,
 *     totalViolations: 1234,
 *     ruleSummary: { "<ruleId>": { count, impact, helpUrl } },
 *     topRoutes: [ { route, violations } ],
 *     perRoute: [ { route, status, violations:[…] } ]
 *   }
 *
 * Env vars: same as full-app.spec.ts (QA_API_URL, QA_BASE_URL,
 *   QA_DEMO_EMAIL, QA_LOCALE), plus QA_AXE_OUT to override the JSON path.
 */
import { test, type APIRequestContext, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';

const API_URL = process.env.QA_API_URL ?? 'http://localhost:8000';
const BASE_URL = process.env.QA_BASE_URL ?? 'http://localhost:5180';
const DEMO_EMAIL = process.env.QA_DEMO_EMAIL ?? 'demo@openconstructionerp.com';
const FORCE_LOCALE = (process.env.QA_LOCALE ?? '').trim();
const TODAY = new Date().toISOString().slice(0, 10);
const OUT_PATH =
  process.env.QA_AXE_OUT ?? join(process.cwd(), 'qa-report', `axe-results-${TODAY}.json`);

// Trim to the most informative routes — full 70-route sweep takes ~25 min
// and produces a lot of redundant violations from shared chrome. This list
// covers each section once.
const AXE_ROUTES: Array<{ section: string; slug: string; path: string }> = [
  { section: '01_core', slug: 'dashboard', path: '/dashboard' },
  { section: '01_core', slug: 'projects', path: '/projects' },
  { section: '01_core', slug: 'files', path: '/files' },
  { section: '01_core', slug: 'notifications', path: '/notifications' },
  { section: '02_bim', slug: 'bim_federations', path: '/bim/federations' },
  { section: '02_bim', slug: 'coordination', path: '/coordination' },
  { section: '02_bim', slug: 'clash', path: '/clash' },
  { section: '02_bim', slug: 'match_elements', path: '/match-elements' },
  { section: '03_estimation', slug: 'boq_list', path: '/boq' },
  { section: '03_estimation', slug: 'costs', path: '/costs' },
  { section: '03_estimation', slug: 'assemblies', path: '/assemblies' },
  { section: '03_estimation', slug: 'validation', path: '/validation' },
  { section: '04_propdev', slug: 'property_dev', path: '/property-dev' },
  { section: '04_propdev', slug: 'accommodation', path: '/accommodation' },
  { section: '05_geo', slug: 'geo_hub', path: '/geo' },
  { section: '06_commercial', slug: 'tendering', path: '/tendering' },
  { section: '06_commercial', slug: 'contracts', path: '/contracts' },
  { section: '06_commercial', slug: 'crm', path: '/crm' },
  { section: '07_field', slug: 'rfi', path: '/rfi' },
  { section: '07_field', slug: 'submittals', path: '/submittals' },
  { section: '07_field', slug: 'hse_advanced', path: '/hse-advanced' },
  { section: '08_planning', slug: 'schedule', path: '/schedule' },
  { section: '08_planning', slug: 'finance', path: '/finance' },
  { section: '08_planning', slug: 'analytics', path: '/analytics' },
  { section: '09_ai', slug: 'ai_agents', path: '/ai-agents' },
  { section: '09_ai', slug: 'chat', path: '/chat' },
  { section: '10_admin', slug: 'settings', path: '/settings' },
  { section: '10_admin', slug: 'users', path: '/users' },
  { section: '10_admin', slug: 'modules', path: '/modules' },
];

async function getAccessToken(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${API_URL}/api/v1/users/auth/demo-login/`, {
    failOnStatusCode: false,
    data: { email: DEMO_EMAIL },
  });
  if (!res.ok()) throw new Error(`demo-login failed (status=${res.status()})`);
  const body = (await res.json()) as { access_token: string };
  return body.access_token;
}

async function hydrateAuth(page: Page, token: string): Promise<void> {
  const params = { token, forceLocale: FORCE_LOCALE };
  await page.addInitScript((p) => {
    localStorage.setItem('oe_access_token', p.token);
    localStorage.setItem('oe_refresh_token', p.token);
    localStorage.setItem('oe_remember', '1');
    localStorage.setItem('oe_user_email', 'demo@openconstructionerp.com');
    localStorage.setItem('oe_onboarding_completed', 'true');
    localStorage.setItem('oe_welcome_dismissed', 'true');
    localStorage.setItem('oe_tour_completed', 'true');
    localStorage.setItem('oe.tour_completed', 'true');
    sessionStorage.setItem('oe_access_token', p.token);
    sessionStorage.setItem('oe_refresh_token', p.token);
    sessionStorage.setItem('oe_demo_modal_dismissed', '1');
    if (p.forceLocale) {
      localStorage.setItem('i18nextLng', p.forceLocale);
      localStorage.setItem('oe_lang_explicit', '1');
    }
  }, params);
}

interface RuleAgg {
  count: number;
  impact: string;
  helpUrl: string;
  routes: Set<string>;
}

interface PerRoute {
  route: string;
  section: string;
  slug: string;
  status: 'ok' | 'error';
  error?: string;
  violationCount: number;
  violations: Array<{
    id: string;
    impact: string | null | undefined;
    nodes: number;
    help: string;
  }>;
}

test.describe('axe a11y sweep', () => {
  test('analyses every catalogued route', async ({ page, request }, testInfo) => {
    testInfo.setTimeout(1_800_000);

    const token = await getAccessToken(request);
    await hydrateAuth(page, token);

    const ruleAgg: Record<string, RuleAgg> = {};
    const perRoute: PerRoute[] = [];

    for (const r of AXE_ROUTES) {
      const url = new URL(r.path, BASE_URL).toString();
      const routeKey = `${r.section}/${r.slug}`;
      const entry: PerRoute = {
        route: routeKey,
        section: r.section,
        slug: r.slug,
        status: 'ok',
        violationCount: 0,
        violations: [],
      };
      try {
        await page.goto(url, { waitUntil: 'load', timeout: 45_000 });
        await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});
        await page.waitForTimeout(2_000);
        // Best-effort modal dismissal
        try {
          const btn = page.getByRole('button', { name: /I understand, continue/i });
          if (await btn.isVisible({ timeout: 1_000 }).catch(() => false)) {
            await btn.click({ force: true }).catch(() => {});
          }
        } catch {
          /* ignore */
        }
        const results = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
          .analyze();
        entry.violationCount = results.violations.length;
        for (const v of results.violations) {
          entry.violations.push({
            id: v.id,
            impact: v.impact,
            nodes: v.nodes.length,
            help: v.help,
          });
          const agg = (ruleAgg[v.id] ??= {
            count: 0,
            impact: v.impact ?? 'unknown',
            helpUrl: v.helpUrl,
            routes: new Set<string>(),
          });
          agg.count += v.nodes.length;
          agg.routes.add(routeKey);
        }
        // eslint-disable-next-line no-console
        console.log(
          `[axe-sweep] OK  ${routeKey} — ${entry.violationCount} unique rules / ` +
            `${entry.violations.reduce((s, vv) => s + vv.nodes, 0)} nodes`,
        );
      } catch (err) {
        entry.status = 'error';
        entry.error = err instanceof Error ? err.message : String(err);
        // eslint-disable-next-line no-console
        console.log(`[axe-sweep] ERR ${routeKey} — ${entry.error?.slice(0, 80)}`);
      }
      perRoute.push(entry);
    }

    const ruleSummary: Record<
      string,
      { count: number; impact: string; helpUrl: string; routeCount: number }
    > = {};
    for (const [id, agg] of Object.entries(ruleAgg)) {
      ruleSummary[id] = {
        count: agg.count,
        impact: agg.impact,
        helpUrl: agg.helpUrl,
        routeCount: agg.routes.size,
      };
    }

    const totalViolations = perRoute.reduce(
      (s, r) => s + r.violations.reduce((ss, v) => ss + v.nodes, 0),
      0,
    );

    const topRoutes = [...perRoute]
      .sort(
        (a, b) =>
          b.violations.reduce((s, v) => s + v.nodes, 0) -
          a.violations.reduce((s, v) => s + v.nodes, 0),
      )
      .slice(0, 10)
      .map((r) => ({
        route: r.route,
        nodes: r.violations.reduce((s, v) => s + v.nodes, 0),
        uniqueRules: r.violations.length,
      }));

    const report = {
      generatedAt: new Date().toISOString(),
      baseUrl: BASE_URL,
      locale: FORCE_LOCALE || 'en',
      totalRoutes: perRoute.length,
      totalViolations,
      uniqueRuleIds: Object.keys(ruleSummary).length,
      ruleSummary,
      topRoutes,
      perRoute,
    };

    mkdirSync(dirname(OUT_PATH), { recursive: true });
    writeFileSync(OUT_PATH, JSON.stringify(report, null, 2), 'utf8');
    // eslint-disable-next-line no-console
    console.log(
      `\n[axe-sweep] DONE — ${perRoute.length} routes, ${totalViolations} total violations, ` +
        `${Object.keys(ruleSummary).length} unique rules. Report → ${OUT_PATH}`,
    );
  });
});
