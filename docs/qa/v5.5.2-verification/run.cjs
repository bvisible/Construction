/* eslint-disable */
// v5.5.2 verification — drives Playwright directly via node.
// Run from frontend/ where playwright is installed.
const { chromium } = require('playwright');
const path = require('path');
const fs = require('fs');

const OUT_DIR = path.resolve(__dirname);
const FE = process.env.QA_FE || 'http://127.0.0.1:5173';
const PROJECT_ID = process.env.QA_PROJECT_ID || '0cefc29a-4e20-4287-be24-8ea0c2e4343b';
const BOQ_ID = process.env.QA_BOQ_ID || '0567be11-dc10-4be8-b085-bbbb679e1357';
const BIM_FED_ID = '6eb959f4-4450-4a45-89fc-753f06ba6dbc';
const BIM_SEL_ID = '747b8136-2a36-47ff-86c5-2aed7b6c812f';

const results = [];

function logResult(slug, status, note) {
  results.push({ slug, status, note, file: `${slug}.png` });
  console.log(`[${status}] ${slug} :: ${note}`);
}

async function login(page) {
  const resp = await page.request.post(`${FE}/api/v1/users/auth/demo-login/`, {
    data: { email: 'demo@openconstructionerp.com' },
    headers: { 'Content-Type': 'application/json' },
  });
  if (!resp.ok()) throw new Error(`demo-login HTTP ${resp.status()}`);
  const body = await resp.json();
  const access = body.access_token ?? body.access;
  const refresh = body.refresh_token ?? body.refresh ?? access;
  await page.goto(`${FE}/`);
  await page.evaluate(([acc, refr]) => {
    localStorage.setItem('oe_access_token', acc);
    localStorage.setItem('oe_refresh_token', refr);
    localStorage.setItem('oe_remember', '1');
    localStorage.setItem('oe_user_email', 'demo@openconstructionerp.com');
    // Mark onboarding/tour done so it doesn't auto-open
    localStorage.setItem('oe_tour_dismissed', '1');
    localStorage.setItem('oe_onboarding_complete', '1');
    localStorage.setItem('oe_whats_new_dismissed', '1');
  }, [access, refresh]);
}

async function shot(page, slug) {
  const file = path.join(OUT_DIR, `${slug}.png`);
  await page.screenshot({ path: file, fullPage: true });
  return file;
}

async function dismissAnyModal(page) {
  try {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    await page.keyboard.press('Escape');
  } catch {}
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  const consoleErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  page.on('pageerror', (e) => consoleErrors.push(`PAGEERR: ${e.message}`));

  try {
    await login(page);
  } catch (e) {
    console.error('LOGIN FAIL:', e.message);
    await browser.close();
    process.exit(2);
  }

  // ─────────────── 1) BOQ FX popover ───────────────
  try {
    // The /projects/{id}/boq route is the BOQ list; the editor (where rows
    // with currency-popover live) is at /boq/{boqId}. Use the first BOQ for
    // the target project.
    const url = `${FE}/boq/${BOQ_ID}`;
    await page.goto(url, { waitUntil: 'networkidle', timeout: 45000 }).catch(() => {});
    // Wait for "Loading..." to disappear
    try {
      await page.waitForSelector('.ag-root, .ag-root-wrapper, [role="grid"]', { timeout: 25000 });
    } catch {}
    await page.waitForTimeout(3500);
    await dismissAnyModal(page);
    await page.waitForTimeout(800);
    // BOQ grid: ag-grid first
    const gridFound = await page.locator('.ag-root, .ag-root-wrapper, [role="grid"], table tbody tr').count();
    let opened = false;
    let attempted = '';
    if (gridFound > 0) {
      // Try to expand all parent rows so resource currency chips become reachable.
      // ag-grid expand affordance has aria-label "Expand" / "Expand row".
      try {
        const expanders = page.locator('span.ag-group-contracted, [aria-label*="Expand" i]:visible');
        const eCount = await expanders.count();
        for (let i = 0; i < Math.min(eCount, 12); i++) {
          try { await expanders.nth(i).click({ timeout: 1000 }); } catch {}
        }
        await page.waitForTimeout(1500);
      } catch {}
      // Resource currency chip — h-4 px-1 inline button with aria-haspopup="listbox"
      // Localized aria-label (Currency / Devise / etc); use the popup-id selector instead.
      const ccyButtons = page.locator('button[aria-haspopup="listbox"][aria-label]:visible').filter({ hasText: /^[A-Z]{3}$/ });
      let ccyCount = await ccyButtons.count();
      // Fallback: chips with raw 3-letter ISO text
      if (ccyCount === 0) {
        const alt = page.locator('button:visible').filter({ hasText: /^[A-Z]{3}$/ });
        ccyCount = await alt.count();
        attempted = `aria_currency=0, raw_iso_chips=${ccyCount}`;
        for (let i = 0; i < Math.min(ccyCount, 12); i++) {
          try {
            const btn = alt.nth(i);
            const txt = (await btn.innerText()).trim();
            // Skip base BRL chips — pick a non-BRL chip ideally
            await btn.scrollIntoViewIfNeeded({ timeout: 1500 });
            await btn.click({ timeout: 2500, force: true });
            await page.waitForTimeout(900);
            if (await page.locator('#oe-currency-popover').count() > 0) {
              opened = true;
              attempted += ` ; opened_chip="${txt}"`;
              break;
            }
          } catch {}
        }
      } else {
        attempted = `aria_currency=${ccyCount}`;
        for (let i = 0; i < Math.min(ccyCount, 12); i++) {
          try {
            const btn = ccyButtons.nth(i);
            const txt = (await btn.innerText()).trim();
            await btn.scrollIntoViewIfNeeded({ timeout: 1500 });
            await page.waitForTimeout(200);
            await btn.click({ timeout: 2500, force: true });
            await page.waitForTimeout(900);
            const visPopover = await page.locator('#oe-currency-popover').count();
            if (visPopover > 0) {
              opened = true;
              attempted += ` ; opened on i=${i} txt="${txt}"`;
              break;
            }
          } catch (err) {
            attempted += ` ; click_err_i=${i}:${(err.message || '').slice(0, 60)}`;
          }
        }
      }
      // If popover opened, capture state showing it's open and check auto-focus.
      let searchAutoFocused = false;
      let popoverAfterPick = 0;
      if (opened) {
        await page.waitForTimeout(500);
        // Check auto-focus on search input
        try {
          searchAutoFocused = await page.evaluate(() => {
            const pop = document.getElementById('oe-currency-popover');
            if (!pop) return false;
            const input = pop.querySelector('input[type="text"]');
            return input === document.activeElement;
          });
        } catch {}
        await shot(page, 'boq-fx-popover-open');
        // Now try picking an exotic foreign currency
        const popover = page.locator('#oe-currency-popover');
        const searchInput = popover.locator('input[type="text"]').first();
        if (await searchInput.count()) {
          try {
            await searchInput.fill('NZD', { timeout: 2000 });
            await page.waitForTimeout(400);
            await searchInput.press('Enter');
            await page.waitForTimeout(1500);
          } catch {}
        }
        popoverAfterPick = await page.locator('#oe-currency-popover').count();
        attempted += ` ; auto_focus=${searchAutoFocused}; popover_after_pick=${popoverAfterPick}`;
      }
    } else {
      attempted = `no_grid_found, gridFound=${gridFound}`;
    }
    await page.waitForTimeout(500);
    await shot(page, 'boq-fx-popover');
    const popoverOpen = await page.locator('#oe-currency-popover').count();
    const fxInputs = await page.locator('input[type="number"]:visible, input[placeholder*="rate" i]:visible, input[aria-label*="rate" i]:visible').count();
    logResult(
      'boq-fx-popover',
      opened ? 'PASS' : 'FAIL',
      `grid=${gridFound}; ${attempted}; final_popover=${popoverOpen}; fx_inputs=${fxInputs}`,
    );
  } catch (e) {
    logResult('boq-fx-popover', 'FAIL', `exception: ${e.message}`);
    try { await shot(page, 'boq-fx-popover'); } catch {}
  }

  // ─────────────── 2) /integrations ───────────────
  try {
    await page.goto(`${FE}/integrations`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(2500);
    await dismissAnyModal(page);
    await shot(page, 'integrations-no-orphans');
    const orphans = await page.getByText(/Example webhook \(disabled\)/i).count();
    const testBtns = page.locator('button:visible', { hasText: /^Test$/i });
    const nTest = await testBtns.count();
    let testNote = `no Test buttons visible (nTest=${nTest})`;
    let r404 = 0;
    if (nTest > 0) {
      const responses = [];
      const listener = (r) => responses.push({ url: r.url(), status: r.status() });
      page.on('response', listener);
      try {
        await testBtns.first().click({ timeout: 2500 });
        await page.waitForTimeout(2000);
      } catch (e) {
        testNote = `Test click failed: ${e.message}`;
      }
      page.off('response', listener);
      r404 = responses.filter((r) => r.status === 404 && r.url.includes('/api/')).length;
      const apiCount = responses.filter(r => r.url.includes('/api/')).length;
      testNote = `Test click; api_responses=${apiCount}; 404=${r404}`;
    }
    logResult(
      'integrations-no-orphans',
      orphans === 0 && r404 === 0 ? 'PASS' : 'FAIL',
      `orphan_rows=${orphans}; ${testNote}`,
    );
  } catch (e) {
    logResult('integrations-no-orphans', 'FAIL', `exception: ${e.message}`);
    try { await shot(page, 'integrations-no-orphans'); } catch {}
  }

  // ─────────────── 3) BIM viewer trio ───────────────
  const bimUrl = `${FE}/bim/${BIM_FED_ID}?sel=${BIM_SEL_ID}`;

  // 3a) default mode - full geometry visible
  try {
    await page.goto(bimUrl, { waitUntil: 'networkidle', timeout: 45000 }).catch(() => {});
    // BIM 3D viewer needs Three.js to initialise + IFC parse
    await page.waitForTimeout(12000);
    await dismissAnyModal(page);
    await page.waitForTimeout(1500);
    await shot(page, 'bim-default-full-geom');
    const isolatedIndicator = await page.getByText(/Isolated|Isolation/i).count();
    const canvasCount = await page.locator('canvas').count();
    logResult(
      'bim-default-full-geom',
      canvasCount > 0 ? (isolatedIndicator === 0 ? 'PASS' : 'PARTIAL') : 'FAIL',
      `canvas=${canvasCount}, isolated_text=${isolatedIndicator}`,
    );
  } catch (e) {
    logResult('bim-default-full-geom', 'FAIL', `exception: ${e.message}`);
    try { await shot(page, 'bim-default-full-geom'); } catch {}
  }

  // 3b) property search (continues same page)
  try {
    // Look broadly for any search-like input in the BIM page
    const candidates = [
      'input[placeholder*="property" i]',
      'input[placeholder*="search" i]:visible',
      '[data-testid*="property-search"]',
      '[data-testid*="search"]',
    ];
    let typed = false;
    let foundSelector = '';
    for (const sel of candidates) {
      const loc = page.locator(sel);
      const c = await loc.count();
      if (c > 0) {
        try {
          const first = loc.first();
          await first.scrollIntoViewIfNeeded({ timeout: 1500 });
          await first.fill('Wall', { timeout: 2500 });
          await page.waitForTimeout(2000);
          typed = true;
          foundSelector = sel;
          break;
        } catch {}
      }
    }
    await shot(page, 'bim-property-search');
    logResult(
      'bim-property-search',
      typed ? 'PARTIAL' : 'FAIL',
      typed ? `typed "Wall" into ${foundSelector}; screenshot captured` : 'no property-search input located',
    );
  } catch (e) {
    logResult('bim-property-search', 'FAIL', `exception: ${e.message}`);
    try { await shot(page, 'bim-property-search'); } catch {}
  }

  // 3c) Begehung at top toolbar, no duplicates at bottom
  try {
    await page.goto(bimUrl, { waitUntil: 'networkidle', timeout: 45000 }).catch(() => {});
    await page.waitForTimeout(10000);
    await dismissAnyModal(page);
    await page.waitForTimeout(1500);
    await shot(page, 'bim-begehung-top');
    // Detect "Begehung" / "Walk" button positions. Use Footprints icon's aria-label or text.
    const begehungBtns = page.locator('button:visible, [role="button"]:visible').filter({ hasText: /Begehung|Walk/i });
    const n = await begehungBtns.count();
    const positions = [];
    for (let i = 0; i < n; i++) {
      try {
        const box = await begehungBtns.nth(i).boundingBox();
        if (box) positions.push({ y: Math.round(box.y), x: Math.round(box.x) });
      } catch {}
    }
    const ruler = await page.locator('button:visible, [role="button"]:visible').filter({ hasText: /Ruler|Measure|Section/i }).count();
    const viewport = page.viewportSize();
    const topHalfBtns = positions.filter((p) => p.y < viewport.height / 2).length;
    const bottomHalfBtns = positions.filter((p) => p.y >= viewport.height / 2).length;
    logResult(
      'bim-begehung-top',
      n > 0 && topHalfBtns > 0 ? 'PARTIAL' : 'FAIL',
      `begehung_count=${n}; top_half=${topHalfBtns}, bottom_half=${bottomHalfBtns}; positions=${JSON.stringify(positions)}; ruler/section_btns=${ruler}`,
    );
  } catch (e) {
    logResult('bim-begehung-top', 'FAIL', `exception: ${e.message}`);
    try { await shot(page, 'bim-begehung-top'); } catch {}
  }

  // ─────────────── 4a) Document templates locale chips ───────────────
  try {
    await page.goto(`${FE}/property-dev/settings/document-templates`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(4000);
    // Some pages auto-open "Request a custom module" modal — dismiss
    await dismissAnyModal(page);
    await page.waitForTimeout(800);
    await dismissAnyModal(page);
    await page.waitForTimeout(500);
    // Wait for at least one locale chip to render
    try {
      await page.waitForSelector('[data-testid^="locale-chip-"]', { timeout: 10000 });
    } catch {}
    await shot(page, 'doc-templates-locale-chips-initial');
    const chips = page.locator('[data-testid^="locale-chip-"]');
    const cCount = await chips.count();
    let chipText = '';
    let modalOpen = 0;
    if (cCount > 0) {
      try {
        chipText = (await chips.first().innerText()).slice(0, 120);
        await chips.first().click({ timeout: 2500 });
        await page.waitForTimeout(1500);
        modalOpen = await page.locator('[role="dialog"]:visible, .modal:visible').count();
      } catch {}
    }
    await shot(page, 'doc-templates-locale-chips');
    const textareaCount = await page.locator('textarea:visible').count();
    logResult(
      'doc-templates-locale-chips',
      cCount > 0 && modalOpen > 0 ? 'PASS' : (cCount > 0 ? 'PARTIAL' : 'FAIL'),
      `chips=${cCount}; sample="${chipText.replace(/\n/g, ' ')}"; modal_after_click=${modalOpen}; textareas=${textareaCount}`,
    );
    // Dismiss modal
    await dismissAnyModal(page);
    await page.waitForTimeout(800);
  } catch (e) {
    logResult('doc-templates-locale-chips', 'FAIL', `exception: ${e.message}`);
    try { await shot(page, 'doc-templates-locale-chips'); } catch {}
  }

  // 4b) Add / edit translation flow
  try {
    await page.goto(`${FE}/property-dev/settings/document-templates`, { waitUntil: 'networkidle', timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(4000);
    await dismissAnyModal(page);
    await page.waitForTimeout(500);
    await dismissAnyModal(page);
    await page.waitForTimeout(500);
    // Use data-testid first
    const addBtn = page.locator('[data-testid="open-locale-editor-new"]').first();
    let clicked = false;
    if (await addBtn.count()) {
      try {
        await addBtn.scrollIntoViewIfNeeded({ timeout: 2000 });
        await addBtn.click({ timeout: 2500 });
        clicked = true;
      } catch {}
    } else {
      // Fallback by text
      const fallback = page.locator('button:visible', { hasText: /Add\s*\/\s*edit\s*translation/i }).first();
      if (await fallback.count()) {
        try {
          await fallback.scrollIntoViewIfNeeded({ timeout: 2000 });
          await fallback.click({ timeout: 2500 });
          clicked = true;
        } catch {}
      }
    }
    await page.waitForTimeout(1500);
    await shot(page, 'doc-templates-locale-add');
    const modalOpen = await page.locator('[role="dialog"]:visible, .modal:visible').count();
    logResult(
      'doc-templates-locale-add',
      clicked && modalOpen > 0 ? 'PASS' : (clicked ? 'PARTIAL' : 'FAIL'),
      `clicked=${clicked}, modal=${modalOpen}`,
    );
  } catch (e) {
    logResult('doc-templates-locale-add', 'FAIL', `exception: ${e.message}`);
    try { await shot(page, 'doc-templates-locale-add'); } catch {}
  }

  fs.writeFileSync(
    path.join(OUT_DIR, 'results.json'),
    JSON.stringify(
      { results, consoleErrorCount: consoleErrors.length, consoleErrorsSample: consoleErrors.slice(0, 30) },
      null,
      2,
    ),
  );
  await browser.close();
  console.log('\n=== DONE ===');
  for (const r of results) console.log(`${r.status}\t${r.slug}\t${r.note}`);
})();
