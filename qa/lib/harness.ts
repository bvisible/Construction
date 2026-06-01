// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Shared verification harness for V_* and INITIATIVE_* spec files.
 *
 * Extracted from the V_RFI / V_SUBMITTALS / V_HSE patterns so new specs
 * stop re-implementing login + screenshot + axe boilerplate.
 *
 * Env vars (with safe defaults):
 *   QA_API_URL       — backend API (default 'http://127.0.0.1:8000')
 *   QA_BASE_URL      — frontend SPA  (default 'http://127.0.0.1:5173')
 *   QA_DEMO_EMAIL    — default 'demo@openconstructionerp.com' (with 'r' — see feedback_demo_creds)
 *   QA_DEMO_PASSWORD — default 'DemoPass1234!'
 *   QA_SCREENSHOTS_ROOT — where to dump PNGs (default './qa-screenshots')
 *
 * Why no top-level baseURL change to playwright.config.ts: that file is
 * polyglot-do-not-modify per the architecture guide memory. Each spec sets its own
 * BASE_URL constant; the harness picks it up via `page.context()._options.baseURL`
 * or the QA_* env vars.
 */

import { Page, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import * as fs from 'node:fs';
import * as path from 'node:path';

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

export const QA_API_URL =
  process.env.QA_API_URL ?? process.env.OE_API_URL ?? 'http://127.0.0.1:8000';
export const QA_BASE_URL =
  process.env.QA_BASE_URL ?? process.env.OE_BASE_URL ?? 'http://127.0.0.1:5173';
export const QA_DEMO_EMAIL =
  process.env.QA_DEMO_EMAIL ?? process.env.OE_DEMO_EMAIL ?? 'demo@openconstructionerp.com';
export const QA_DEMO_PASSWORD =
  process.env.QA_DEMO_PASSWORD ?? process.env.OE_DEMO_PASSWORD ?? 'DemoPass1234!';
export const QA_SCREENSHOTS_ROOT =
  process.env.QA_SCREENSHOTS_ROOT ?? './qa-screenshots';

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------

/**
 * Log in as the demo user via the dedicated /demo-login/ endpoint and
 * seed the access/refresh tokens into localStorage so the SPA starts
 * authenticated on the next navigation.
 *
 * Throws if the backend returned non-2xx — fail-fast beats "tests run
 * but every page shows the login screen".
 */
export async function loginAsDemo(page: Page): Promise<void> {
  const apiBase = QA_API_URL;
  const tokenResp = await page.request.post(
    `${apiBase}/api/v1/users/auth/demo-login/`,
    {
      data: { email: QA_DEMO_EMAIL },
      headers: { 'Content-Type': 'application/json' },
    },
  );
  if (!tokenResp.ok()) {
    throw new Error(
      `[harness.loginAsDemo] demo-login failed: HTTP ${tokenResp.status()} ` +
        `from ${apiBase}/api/v1/users/auth/demo-login/`,
    );
  }
  const body = await tokenResp.json();
  const access: string = body.access_token ?? body.access;
  const refresh: string = body.refresh_token ?? body.refresh ?? access;
  if (!access) {
    throw new Error('[harness.loginAsDemo] response had no access token');
  }

  await page.goto('/');
  await page.evaluate(
    ([acc, refr]) => {
      localStorage.setItem('oe_access_token', acc);
      localStorage.setItem('oe_refresh_token', refr);
      localStorage.setItem('oe_remember_me', '1');
    },
    [access, refresh],
  );
  void QA_DEMO_PASSWORD; // silence unused-var for password (magic-link demo)
}

// ---------------------------------------------------------------------------
// Screenshots
// ---------------------------------------------------------------------------

export interface ScreenshotOptions {
  /** Subdirectory under QA_SCREENSHOTS_ROOT (e.g. 'initiative-B-notifications'). */
  bucket: string;
  /** File label without extension (e.g. '01_landing'). */
  label: string;
  /** Full-page screenshot? (default true). */
  fullPage?: boolean;
  /** Disable animations to make pixel-comparisons stable. */
  freezeAnimations?: boolean;
}

/**
 * Take a deterministic screenshot. Creates the target directory.
 * Returns the absolute file path so the analyst can Read it.
 */
export async function captureScreenshot(
  page: Page,
  opts: ScreenshotOptions,
): Promise<string> {
  const dir = path.join(QA_SCREENSHOTS_ROOT, opts.bucket);
  fs.mkdirSync(dir, { recursive: true });
  const filepath = path.join(dir, `${opts.label}.png`);

  if (opts.freezeAnimations !== false) {
    await page.addStyleTag({
      content: `
        *, *::before, *::after {
          transition: none !important;
          animation: none !important;
          caret-color: transparent !important;
        }
      `,
    });
  }

  await page.screenshot({
    path: filepath,
    fullPage: opts.fullPage !== false,
  });
  return path.resolve(filepath);
}

// ---------------------------------------------------------------------------
// a11y (axe-core)
// ---------------------------------------------------------------------------

export interface AxeReport {
  url: string;
  timestamp: string;
  violations: Array<{
    id: string;
    impact: string | null;
    description: string;
    nodes: number;
    helpUrl: string;
  }>;
  criticalCount: number;
  seriousCount: number;
}

/**
 * Run axe-core against the current page, return a normalized report.
 * Writes a JSON sibling to the screenshot so the analyst gets it in one
 * Read pass.
 */
export async function runAxe(
  page: Page,
  bucket: string,
  label: string,
): Promise<AxeReport> {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();

  const report: AxeReport = {
    url: page.url(),
    timestamp: new Date().toISOString(),
    violations: results.violations.map((v) => ({
      id: v.id,
      impact: v.impact ?? null,
      description: v.description,
      nodes: v.nodes.length,
      helpUrl: v.helpUrl,
    })),
    criticalCount: results.violations.filter((v) => v.impact === 'critical').length,
    seriousCount: results.violations.filter((v) => v.impact === 'serious').length,
  };

  const dir = path.join(QA_SCREENSHOTS_ROOT, bucket);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, `${label}.axe.json`),
    JSON.stringify(report, null, 2),
  );
  return report;
}

// ---------------------------------------------------------------------------
// Network error capture
// ---------------------------------------------------------------------------

export interface NetworkProbe {
  /** Attach to a page before navigation. */
  attach(page: Page): void;
  /** Snapshot what was captured since attach (or since last reset). */
  snapshot(): NetworkSnapshot;
  /** Clear captured state. */
  reset(): void;
}

export interface NetworkSnapshot {
  failedRequests: Array<{ url: string; failure: string }>;
  httpErrors: Array<{ url: string; status: number; statusText: string }>;
  consoleErrors: string[];
  uncaughtExceptions: string[];
}

/**
 * Create a NetworkProbe that captures: failed requests, 4xx/5xx responses,
 * console.error lines, page.on('pageerror') (uncaught exceptions).
 *
 * Why this matters: the Max Tamariz "white screen on click" bug class is
 * exactly an uncaught exception that React error boundary catches and the
 * page goes blank. Without `pageerror` capture, the spec sees a blank page
 * and can't tell why.
 */
export function createNetworkProbe(): NetworkProbe {
  let failedRequests: NetworkSnapshot['failedRequests'] = [];
  let httpErrors: NetworkSnapshot['httpErrors'] = [];
  let consoleErrors: string[] = [];
  let uncaughtExceptions: string[] = [];

  return {
    attach(page: Page) {
      page.on('requestfailed', (req) => {
        failedRequests.push({
          url: req.url(),
          failure: req.failure()?.errorText ?? 'unknown',
        });
      });
      page.on('response', (resp) => {
        const status = resp.status();
        if (status >= 400) {
          httpErrors.push({
            url: resp.url(),
            status,
            statusText: resp.statusText(),
          });
        }
      });
      page.on('console', (msg) => {
        if (msg.type() === 'error') {
          consoleErrors.push(msg.text());
        }
      });
      page.on('pageerror', (err) => {
        uncaughtExceptions.push(`${err.name}: ${err.message}\n${err.stack ?? ''}`);
      });
    },
    snapshot() {
      return {
        failedRequests: [...failedRequests],
        httpErrors: [...httpErrors],
        consoleErrors: [...consoleErrors],
        uncaughtExceptions: [...uncaughtExceptions],
      };
    },
    reset() {
      failedRequests = [];
      httpErrors = [];
      consoleErrors = [];
      uncaughtExceptions = [];
    },
  };
}

// ---------------------------------------------------------------------------
// Pre-flight check
// ---------------------------------------------------------------------------

export interface PreflightResult {
  apiUp: boolean;
  apiHealthBody?: object;
  frontUp: boolean;
  alembicHead?: string | null;
  demoLoginWorks: boolean;
  errors: string[];
}

/**
 * Verify the local backend + frontend are reachable AND the demo login
 * actually mints a token. Call this from beforeAll() — if it returns
 * apiUp=false, abort the suite rather than wasting time on screenshots.
 */
export async function preflight(): Promise<PreflightResult> {
  const errors: string[] = [];
  const result: PreflightResult = {
    apiUp: false,
    frontUp: false,
    demoLoginWorks: false,
    errors,
  };

  try {
    const r = await fetch(`${QA_API_URL}/api/health`, { signal: AbortSignal.timeout(5000) });
    if (r.ok) {
      result.apiUp = true;
      try {
        result.apiHealthBody = (await r.json()) as object;
        // Some installs expose alembic head in the health body — capture
        // it for the verification report.
        const body = result.apiHealthBody as Record<string, unknown>;
        const head = body['alembic_head'] ?? body['alembic_current'];
        if (typeof head === 'string') {
          result.alembicHead = head;
        }
      } catch {
        // health endpoint returned non-JSON — fine, just no metadata
      }
    } else {
      errors.push(`API health returned ${r.status}`);
    }
  } catch (e) {
    errors.push(`API health unreachable: ${(e as Error).message}`);
  }

  try {
    const r = await fetch(QA_BASE_URL, { signal: AbortSignal.timeout(5000) });
    result.frontUp = r.ok;
    if (!r.ok) errors.push(`Frontend returned ${r.status}`);
  } catch (e) {
    errors.push(`Frontend unreachable: ${(e as Error).message}`);
  }

  if (result.apiUp) {
    try {
      const r = await fetch(`${QA_API_URL}/api/v1/users/auth/demo-login/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: QA_DEMO_EMAIL }),
        signal: AbortSignal.timeout(5000),
      });
      result.demoLoginWorks = r.ok;
      if (!r.ok) errors.push(`demo-login returned ${r.status}`);
    } catch (e) {
      errors.push(`demo-login unreachable: ${(e as Error).message}`);
    }
  }

  return result;
}

// ---------------------------------------------------------------------------
// Flow runner — captures a sequence of (action, screenshot, axe) tuples
// ---------------------------------------------------------------------------

export interface FlowStep {
  label: string;
  action?: (page: Page) => Promise<void>;
  axe?: boolean;
  waitForSelector?: string;
  /** Skip screenshot for this step (for pure navigation steps). */
  skipScreenshot?: boolean;
}

export interface FlowReport {
  flowName: string;
  bucket: string;
  startedAt: string;
  finishedAt: string;
  steps: Array<{
    label: string;
    screenshot?: string;
    axe?: AxeReport;
    network: NetworkSnapshot;
    durationMs: number;
  }>;
  passed: boolean;
}

/**
 * Run a sequence of steps, capture screenshot + axe + network probe after
 * each. Saves a JSON report and returns it.
 *
 * Use this in specs:
 *
 *     const report = await runFlow(page, 'B_notifications_click', [
 *       { label: '01_login', action: async (p) => loginAsDemo(p) },
 *       { label: '02_open_notifications',
 *         action: async (p) => p.click('[data-testid=notifications-bell]') },
 *       { label: '03_click_first_item',
 *         action: async (p) => p.locator('.notification-item').first().click() },
 *     ]);
 *     expect(report.passed).toBe(true);
 */
export async function runFlow(
  page: Page,
  flowName: string,
  steps: FlowStep[],
): Promise<FlowReport> {
  const bucket = `initiative/${flowName}`;
  const probe = createNetworkProbe();
  probe.attach(page);

  const stepReports: FlowReport['steps'] = [];
  let passed = true;
  const startedAt = new Date().toISOString();

  for (const step of steps) {
    const t0 = Date.now();
    try {
      if (step.action) {
        await step.action(page);
      }
      if (step.waitForSelector) {
        await page.waitForSelector(step.waitForSelector, { timeout: 10_000 });
      }
    } catch (e) {
      passed = false;
      stepReports.push({
        label: `${step.label}_ACTION_FAILED`,
        network: probe.snapshot(),
        durationMs: Date.now() - t0,
      });
      // Even on failure, capture the screenshot — it shows the broken state
      try {
        const sp = await captureScreenshot(page, {
          bucket,
          label: `${step.label}_failed`,
        });
        stepReports[stepReports.length - 1].screenshot = sp;
      } catch {
        /* page may be too broken for screenshot */
      }
      continue;
    }

    let screenshotPath: string | undefined;
    if (!step.skipScreenshot) {
      try {
        screenshotPath = await captureScreenshot(page, {
          bucket,
          label: step.label,
        });
      } catch (e) {
        passed = false;
      }
    }

    let axeReport: AxeReport | undefined;
    if (step.axe) {
      try {
        axeReport = await runAxe(page, bucket, step.label);
      } catch (e) {
        passed = false;
      }
    }

    const snap = probe.snapshot();
    if (snap.uncaughtExceptions.length > 0) {
      // An uncaught exception during a step = white-screen risk. Flag.
      passed = false;
    }

    stepReports.push({
      label: step.label,
      screenshot: screenshotPath,
      axe: axeReport,
      network: snap,
      durationMs: Date.now() - t0,
    });
    probe.reset();
  }

  const report: FlowReport = {
    flowName,
    bucket,
    startedAt,
    finishedAt: new Date().toISOString(),
    steps: stepReports,
    passed,
  };

  const dir = path.join(QA_SCREENSHOTS_ROOT, bucket);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(
    path.join(dir, 'flow_report.json'),
    JSON.stringify(report, null, 2),
  );
  return report;
}

// Re-exports for downstream specs
export { expect, AxeBuilder };
