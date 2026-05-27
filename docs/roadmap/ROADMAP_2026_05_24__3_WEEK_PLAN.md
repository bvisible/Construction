# 3-week roadmap — 2026-05-24 → 2026-06-14

Living document. Updated as waves land. Source of truth for scope, cadence, QA gates.

## North star

OCERP becomes globally usable (no jurisdiction lock-in), beautifully consistent (oe-blue / Tailwind, tighter), field-ready (workers on tablets with restricted scope), and proven (every wave verified via Playwright clicks + screenshots in its worktree).

## Operating principles (settled 2026-05-24)

| Question | Decision |
|---|---|
| **Release cadence** | Every 2–3 days a `v4.x.0` to VPS — 7–10 deploys over 3 weeks |
| **Browser verification** | Every code-agent runs Playwright headless in its worktree, captures ~5 screenshots of the touched surface, attaches paths to its report |
| **Design language** | Current oe-blue / Tailwind, but tightened: Apple-tight radii (sm 6 / md 8 / lg 10 / xl 12 — already in `design_system_2026-05-11`), denser spacing, refined typography hierarchy. **No new component libraries.** |
| **Autonomy** | Full proactive — make best-guess calls, ship; for any ambiguity worth >2 hours of rework, spawn a deep-research sub-agent first |
| **Constraints** | NO IfcOpenShell · NO Claude/AI/Anthropic in commits · contact `info@datadrivenconstruction.io` · NO `--no-verify` · NO force-push to main · money = Decimal-as-string · IDOR → 404 |

## Epics

### A. Worldwide parameterization (Day 1–3)
- **A1** Document templates combobox sweep — *#109 in flight* (`agent ae1b...`)
- **A2** Currency pickers everywhere → full ISO 4217 (~180), free-text fallback
- **A3** Country pickers → ISO 3166-1 (195 entries) with regional grouping
- **A4** Date/time/number formats driven by user pref store, never hardcoded
- **A5** Unit-system toggle (metric / imperial / mixed) — wired into MoneyDisplay sister `<MeasureDisplay>`

### B. /geo deep features (Day 1–4)
- **B1** Backend `POST /geo-hub/auto-anchor-all` + frontend auto-trigger on first /geo load with unanchored-with-address projects — *#110 in flight* (coordinate with Wave 18)
- **B2** Cesium ion popup suppression + OSM attribution overlay — **DONE 2026-05-24**
- **B3** Geo viewport flush to bottom (dvh fix) — **DONE 2026-05-24**
- **B4** GeoHubPage IA + filters (country / status / value range)
- **B5** Anchor manual fine-tune drag, lat/lon precision input
- **B6** Tileset thumbnail strip in TilesetSidebar

### C. /property-dev IA + 8690-line split (Day 3–6)
- **C1** Wave 21 monolith split by tab — *in flight*
- **C2** Top nav blocks with named sections ("Sales pipeline" / "Inventory" / "Operations" / "Settings")
- **C3** Mobile drawer pattern <md
- **C4** PropDev tour rebuild for new IA
- **C5** Sub-entity tabs polish

### D. /accommodation overhaul (Day 2–5)
- **D1** Visual + IA pass — *in flight* (`agent ae4b...`)
- **D2** Calendar mobile carousel < sm
- **D3** Field-worker quick check-in surface
- **D4** Empty/loading/error consistency sweep

### E. Formwork module (Day 7–17) — research DONE
- **E0** Design doc landed — `docs/modules/FORMWORK_MODULE_DESIGN.md` (893 lines, 12 entity tables, ~50 endpoints, ASCII wireframes, RBAC matrix, MVP/Full split) — *agent `a3eb...`*
- **E1** Backend models + alembic migration (12 tables) — MVP slice
- **E2** Backend services + REST routes (catalogue + commercial)
- **E3** Backend services + REST routes (operational + movements + field)
- **E4** Frontend `/formwork` shell + inventory grid + planning calendar
- **E5** Frontend mobile field-worker scan + post-scan action sheet
- **E6** Integration touchpoints (BIM canonical zones, costs daily-rental, procurement, hse-incident link)
- **E7** Tests (pytest unit/integration + Playwright e2e + axe a11y) + i18n keys
- **E8** Vendor-comparison docs (MyDoka / PeriCloud / Ulma) — appendix already in design doc

### F. Field-worker mobile platform (Day 4–12)
- **F0** Design doc + skeleton — *in flight* (`agent a1b4...`)
- **F1** Backend `field_worker` / `site_foreman` / `site_inspector` roles + project-scoped perm matrix
- **F2** Auth flow: PIN + magic-link (reuse buyer-portal pattern)
- **F3** Frontend `/field` shell with 4-item bottom nav (Today / Capture / Crew / Profile)
- **F4** Capture flow: photo → categorise → location auto-tag → submit
- **F5** Offline queue (IndexedDB + service-worker pre-cache app shell + today's data)
- **F6** First pilot module surface: Daily Diary entries from field
- **F7** Second surface: HSE quick incident
- **F8** Third surface: Formwork unit scan (ties into Epic E)

### G. Visual polish + density (Day 5–10)
- **G1** Apple-tight radii sweep (sm 6 / md 8 / lg 10 / xl 12) across all components
- **G2** Spacing audit — 50+ pages, target tokens: dense (gap-1.5/2/3), spacious (gap-4/6/8) — one consistent pattern per page section
- **G3** Typography scale tokens — header sizes, line-heights, text-content-* role classes
- **G4** Empty/loading/error sweep — every `useQuery` follows the `<SkeletonX> / <RecoveryCard> / <EmptyState>` triplet (extending Wave 11)
- **G5** Dark-mode contrast sweep (WCAG AA every page)

### H. QA browser-screenshot loop (continuous, Day 1–21)
- **H1** Add `frontend/qa/playwright-screenshot-helper.ts` — agents import + call `captureFeature(name)` to drop PNGs into `qa-screenshots/<wave>/<feature>/`
- **H2** Add agent-prompt template that mandates: vite preview running, headless Chromium, login as demo, navigate to touched route, ~5 screenshots, paths in report
- **H3** 1 daily QA-walkthrough agent — sweep all 112 modules, screenshot each landing page + 1 deep flow per module, diff against prior day, flag visual regressions
- **H4** Pixel-diff regression suite — PNG compare with 0.1% threshold; failures open Issue
- **H5** Sample-PR ultrareview gate: every PR with >200 LOC frontend changes triggers `/ultrareview` (manual — user-triggered)

## Release train (target)

| Day | Version | Includes |
|---|---|---|
| D2 (2026-05-26) | v4.8.0 | Epic A1+A2, Epic B1+B2+B3, /accommodation D1 |
| D4 (2026-05-28) | v4.8.1 | A3+A4, Epic C2 menu blocks, hotfixes |
| D7 (2026-05-31) | v4.9.0 | Epic C done, Epic D done, Epic G1+G2 |
| D10 (2026-06-03) | v4.9.1 | A5 units, G3 typography, hotfixes |
| D13 (2026-06-06) | v4.10.0 | Epic F MVP (Daily Diary mobile), Epic E1+E2 |
| D16 (2026-06-09) | v4.11.0 | Epic E3+E4 (Formwork inventory + planning), F6+F7 |
| D19 (2026-06-12) | v4.12.0 | Epic E5+E6+E7 (Formwork field + tests), F8, G4+G5 |
| D21 (2026-06-14) | **v5.0.0** | QA H3+H4 stable, all epics shipped + verified, full screenshot regression baseline |

## Wave throughput

Target: 4–6 code agents in flight at any time + 1 daily QA-walkthrough agent.
Total over 3 weeks: ~80–120 agent waves.

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Worktree base drift (memory: bit us 3× in R6 + 3× in v4.6.0) | Every agent first instruction is `git fetch && git checkout origin/main`, verify HEAD |
| Sandbox kills uvicorn (3× incidents) | Agents run their own `python -m uvicorn app.main:create_app --factory` via `Start-Process -WindowStyle Hidden cmd /c ...` |
| Playwright in worktree slow/flaky | Cache `~/.cache/ms-playwright` browsers; first agent installs, rest reuse |
| Merge conflicts across parallel waves on same area | Concurrent agents must touch non-overlapping files; conflict-prone areas (PropertyDevPage, GeoHubPage) get a single owner per wave |
| Cadence pressure leaves bugs | Mandatory QA-screenshot pass before every VPS deploy; revert wave if regression |

## Tracking

Each epic = 1+ tasks in TaskList. Each wave = 1 commit + 1 agent. Status visible via task list + git log.

This doc is updated at every deploy with: what shipped, what slipped, what surfaced new.
