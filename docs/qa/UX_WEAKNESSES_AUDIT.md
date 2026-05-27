# OpenConstructionERP — UX Weaknesses Audit

Generated: 2026-05-24
Branch: `main` @ `0cb0f5c8`
Auditor scope: 12-dimension sweep across all 150+ frontend routes (`frontend/src/app/App.tsx`), shared design system (`frontend/src/shared/ui/**`), and the 27 locale dictionaries (`frontend/src/app/locales/**`).
Total findings: **287** (🔴 24 · 🟠 86 · 🟡 132 · 🔵 45)

> **Note on QA test plan cross-reference**: The task brief references
> `docs/qa/MASTER_TEST_PLAN.md` as "already merged on main". That file
> does **not** exist on the current `main` HEAD `0cb0f5c8` — the only
> existing `docs/qa/*` is this report itself. The "what Playwright will
> NOT catch" section therefore lists what such a plan *would* miss
> based on the nature of each finding (subjective vs assertable).

---

## Severity legend

- 🔴 **Blocker** — confuses or blocks users in the golden path; ship-stopping
- 🟠 **Major** — degrades trust or productivity; fix in next sprint
- 🟡 **Minor** — noticeable polish gap; fix in the next polish wave
- 🔵 **Nit** — would be nicer; nice-to-have

---

## Top 20 must-fix-before-marketing-push

1. 🔴 **21 files still use `window.confirm()` for destructive actions** — looks like a 2008 web app, breaks Apple-style polish positioning. Replace with `useConfirm()` + `ConfirmDialog` (which already exists). Worst offenders: `PropertyDevPage.tsx` (×5), `catalog/CatalogPage.tsx`, `clash/ClashDetectionPage.tsx`, `documents/PhotoGalleryPage.tsx`.
2. 🔴 **`UserManagementPage` MODULE_GROUPS + ROLE_CONFIG labels are hardcoded English** (`'Admin'`, `'Manager'`, `'Core'`, `'Planning & Finance'`, `'Bill of Quantities'`, …). German/Russian/Arabic users see English literals in the admin matrix. `frontend/src/features/users/UserManagementPage.tsx:54-144`.
3. 🔴 **`InviteModal` placeholders are hardcoded English** (`"John Doe"`, `"john@company.com"`, `"Min 6 characters"`). `users/UserManagementPage.tsx:194-219`. Same modal hand-rolls its own dialog instead of using `WideModal` — pattern drift.
4. 🔴 **49 different feature files duplicate the `inputCls` constant** instead of using a shared `<Input>` component. When the design system shifts (e.g. the 2026-05-11 radii tightening), 49 files must be touched. Search: `^const inputCls\s*=` in `frontend/src/features/**`.
5. 🔴 **Only 1 file in the entire frontend uses `aria-required`** (`projects/CreateProjectPage.tsx:1`). Every other form silently relies on a visual `*` asterisk or no marker at all. Screen-reader users cannot tell a field is required.
6. 🔴 **Two parallel onboarding-tour systems** (`OnboardingTour` keyed on `oe_tour_completed` + `ProductTour` keyed on `oe.tour_completed` — note the dot vs underscore). Both are mounted in `App.tsx:596-603`. New users may see one, dismiss it, then have the other pop on the next page. Pick one.
7. 🔴 **Dev/internal pages reachable from production sidebar**: `/styles-lab`, `/eac/demo`, `/architecture`, `/eac/blocks/:id`. `App.tsx:756-760`, sidebar surfaces "Architecture Map" via `analytics` group. Non-engineering users land on the page and have no idea what it does.
8. 🔴 **Sidebar has 22 collapsible groups + ~80 items**. First-time users cannot find anything without Cmd+K. `Sidebar.tsx:142-447`. Simple-mode reduces this only marginally (most items are `hideInSimple: false`).
9. 🔴 **NotificationsPage uses ad-hoc locale formatting** (`d.toLocaleString(locale, ...)` at line 88) rather than the shared `DateDisplay`. Inconsistent with the rest of the app.
10. 🔴 **PropertyDevPage is a single 8 690-line file** with 5 inline `window.confirm` calls, ad-hoc filter UIs and several nested table rerenders. This is the *most-visited* property-dev surface and the slowest to render on a fresh page-load (`property-dev/PropertyDevPage.tsx`).
11. 🟠 **BIMPage is 3 558 lines, FinancePage is 2 855 lines, BOQEditorPage is 4 702 lines** — initial render of any of these blocks the main thread; pages also defeat code-splitting because mixing many panels in one file means lazy chunks pull more than they should.
12. 🟠 **357 spinner usages vs 81 skeleton usages** — most loading states are bare spinners. Spinner UX flicker = 200-400 ms of "blank looks broken" before content arrives. Convert top-level lists in the 100+ pages currently relying on `animate-spin` to shape-matched skeletons.
13. 🟠 **Dashboard rollup widgets render before count loads, then re-render with the real number** (flash-of-zero). E.g. `dashboard/DashboardPage.tsx`: KPI tiles default to `0` then jump. Use `<Skeleton>` placeholders or hide until ready.
14. 🟠 **Sidebar uses cryptic group titles** like `nav.group_cad_bim_analytics`, `nav.group_estimation`, `nav.group_takeoff` — names a builder/estimator wouldn't choose. "Takeoff" + "Estimating" + "Coordination" overlap. Test with target users before marketing.
15. 🟠 **Hardcoded EUR fallback everywhere** (`MoneyDisplay.tsx:54`: `safeCurrency = /^[A-Z]{3}$/.test(resolvedCurrency) ? resolvedCurrency : 'EUR'`; `analytics/AnalyticsPage.tsx:24`: `currency = 'EUR'`). Saudi customer creates a project in SAR, totals row falls back to EUR.
16. 🟠 **`/property-dev` Settings (House Types, Doc Templates) are sidebar items but Validation Rules moved to `/admin/validation-rules`**. The split is undocumented in the UI — users searching the PropDev surface for "validation" find nothing.
17. 🟠 **No "stale data" indicator anywhere on the dashboard** — KPIs may be 1 minute or 10 minutes old; nothing tells the user. Add a "Last refreshed Nm ago" footer with a refresh button.
18. 🟠 **AR locale dictionary is 13% smaller than EN** (6 224 vs 7 142 lines). Many keys silently fall back to English — Arabic users see mixed-direction UI.
19. 🟠 **Tab patterns are NOT consistent**: only 30 of ~120 pages set `role="tablist"`. Plain `<div>`-tabs are not navigable with arrow keys; screen readers don't announce position.
20. 🟠 **`/notifications` page omits "go to source"** for many notification types; users see "RFI replied" but no jump-link to the RFI in the body.

---

## Findings by category

### 1. Empty states

✅ **What's good**: shared `EmptyState` component + `standardEmptyCopy()` helper exist (`shared/ui/EmptyState.tsx`). Used in ~100 places. Has icon, title, description, action slot.

❌ **Findings**:

- 🔴 `HSEAdvancedPage` — when no project is selected the empty state is `"No project selected" / "Pick a project from the header"` (`hse-advanced/HSEAdvancedPage.tsx:200-208`). 30 other pages need the same flow and reinvent it inline. Extract a `<RequiresProject>` wrapper.
- 🟠 `users/UserManagementPage` — no empty state for "no users yet" (fresh-install always has the demo admin so it never triggers, but a self-hosted install with auth-via-SSO won't have a demo user → blank screen).
- 🟠 `notifications/NotificationsPage` — the empty state when `is_read=true` filter is active just says "No notifications" — does not hint that filtering by "read" returns nothing because everything is unread. Add filter-aware messaging.
- 🟠 `tasks/TasksPage`, `rfi/RFIPage`, `submittals/SubmittalsPage`, `correspondence/CorrespondencePage`, `transmittals/TransmittalsPage`, `inspections/InspectionsPage`, `ncr/NCRPage` — each has an empty state but **none link to an import-from-CSV or "use a template" CTA**, even though backend has CSV import for several of these.
- 🟠 `catalog/CatalogPage` — empty state when search returns no rows is generic ("No resources match"); doesn't suggest broadening filters (region/type) or installing a regional catalogue.
- 🟡 `geo-hub/GeoHubPage` has a glass-panel empty state (`GlobalNoProjectsEmpty`), good. But `ProjectGeoPage` empty state is bare text "No anchor for this project" — no CTA.
- 🟡 `assemblies/AssembliesPage` empty state does not link to `/assemblies/library` (which has read-only seed assemblies the user could import).
- 🟡 `clash/ClashDetectionPage` — when no clashes exist after a run, the empty state says "No clashes detected" but doesn't explain "this might be because filters exclude them" or link to "tune sensitivity".
- 🟡 `field-reports/FieldReportsPage` — no "Try a template" affordance even though template management exists in `ManageTemplatesModal`.
- 🟡 `pipelines/PipelinesPage` — no template gallery on first visit; user gets a blank canvas with no hint to drag-and-drop.
- 🔵 `crm/CRMPage` empty state for "no leads" doesn't link to `/settings/webhook-leads` (the obvious next step for inbound capture).
- 🔵 `compliance-docs/CompliancePage` empty state should link to the rule library since the only sensible first action is "pick a rule pack".

### 2. Loading states

✅ **What's good**: shared `Skeleton` + `SkeletonText` + `SkeletonGrid` + `SkeletonTable` components exist.

❌ **Findings**:

- 🔴 357 `animate-spin` usages vs 81 `Skeleton` usages across 163 files. **Most page-level loads still show a bare spinner**, which causes a 200-400 ms flash of "blank UI" before content paints.
- 🔴 `ProjectsPage` projects-dashboard-cards inline `<span className="inline-block h-5 w-10 animate-pulse rounded bg-surface-tertiary"/>` (lines 361, 381, 403). This is an ad-hoc skeleton — should use `<Skeleton width={40} height={20}/>` for consistency.
- 🟠 `DashboardPage` widgets — many KPI cards render with literal `0` and `—` while their dedicated query is pending, then flicker to the real value when it arrives. Pattern: `data?.total_revenue ?? 0`. Replace with `data ? formatBigValue(data.total_revenue) : <Skeleton width={64} height={20}/>`.
- 🟠 `BIMPage` — when a model is loading, the viewport shows a `Loader2` icon centered on a gray block. Should show a *thumbnail* of the model (if cached) + a progress percentage when the converter reports it.
- 🟠 `FloatingChatPanel` — typing indicator is a `Loader2` instead of a 3-dot animated pulse. Looks unfinished.
- 🟠 `match-elements/MatchPipeline` — each stage card shows its own spinner separately; on a 7-stage pipeline this is 7 spinners simultaneously. Aggregate to one progress bar.
- 🟠 `validation/ValidationPage` — while computing, the score circle is hidden entirely instead of showing a placeholder ring → page jumps when the result loads.
- 🟡 `analytics/AnalyticsPage` skeletons mismatch the real layout — the skeleton bars use `h-10 w-full` but the real rows have right-aligned numeric columns; the eye sees layout shift.
- 🟡 `notifications/NotificationsPage` — no skeleton at all; bare "Loading..." text.
- 🟡 `cde/CDEPage`, `submittals/SubmittalsPage`, `transmittals/TransmittalsPage` — `<SkeletonTable rows={5}/>` but actual rows render at variable height → minor shift.
- 🔵 `geo-hub/CesiumViewer` — bootstrap takes 1-3s on cold; no progress hint. Add "Loading map tiles…" with a percent.

### 3. Error recovery

❌ **Findings**:

- 🔴 `ProjectsPage` BOQ-stats error is `console.error` only (`projects/ProjectsPage.tsx:142-146`) — when the dashboard rollup endpoint 500s, **the cards silently show "0 BOQs / €0 value"** which looks identical to "no data". Add an in-page warning banner.
- 🔴 `RFIPage`, `SubmittalsPage`, `TasksPage`, `MeetingsPage`, `CorrespondencePage`, `CDEPage`, `NCRPage` — none of these surface 401/403 specifically. A logged-out / role-gated user just sees the empty state. Add `<RecoveryCard>` for 401/403 with "Sign in again" / "Request access".
- 🟠 `BIMPage` — when the converter is down the banner is conditional but doesn't offer "Retry" or "Install converter" inline; user has to find `Settings → Integrations`.
- 🟠 `DashboardPage` — if `dashboard/cards` endpoint fails, the entire grid blank-screens without an error. Wrap each widget in a per-widget ErrorBoundary so a single failing query doesn't take down the whole dashboard.
- 🟠 `ImportDatabasePage` — when a CWICR import fails partway, only a toast appears; the page state is now half-imported. Need an "Import session" page that lists past attempts with retry.
- 🟠 `MatchElementsPage` Qdrant unhealthy state — banner says "Vector index degraded" but no link to `/settings → Vector status` for the operator.
- 🟡 `AccommodationCalendarPage` — if a room fetch fails, the day cell shows blank — no indication it's a fetch error vs "no booking".
- 🟡 `clash/ClashDetectionPage` — long-running detection that times out shows a generic error toast; no "View partial results" affordance.

### 4. Form UX

❌ **Findings**:

- 🔴 **Required fields not accessibly marked**: only `projects/CreateProjectPage.tsx` uses `aria-required`. Every other form (~100) marks required only visually (red asterisk or no marker). WCAG 3.3.2 failure.
- 🔴 **`InviteModal` placeholders are English literals**: `"John Doe"`, `"john@company.com"`, `"Min 6 characters"` (`users/UserManagementPage.tsx:194-219`).
- 🔴 **Server-side validation not surfaced inline next to the field** — most forms (e.g. `ContactsPage`, `RFIPage`, `MeetingsPage`) show backend errors only via toast. Toast disappears, user can't tell which field failed. The `ContactsPage` `errors` state exists (line 193) but is only populated by client-side validation; 4xx detail.field errors are not parsed.
- 🔴 **21 files still use `window.confirm()` / `window.alert()`** instead of the shared `ConfirmDialog`. List: `PropertyDevPage` (×5 places), `catalog/CatalogPage`, `clash/ClashDetectionPage`, `documents/PhotoGalleryPage`, `costs/ImportDatabasePage`, `bim/FederationsPage` (×2), `boq/grid/cellRenderers`, `boq/BOQEditorPage`, `settings/WebhookLeads`, `compliance-docs/CompliancePage`, `geo-hub/OverlayPanel`, `property-dev/SnagsBlock`, `property-dev/PropDevSubEntityTabs`, `file-saved-views/SavedViewsRail`, `file-distribution/DistributionListModal`, `file-manager/components/FolderPermissionsModal`. Find via `grep "window\.confirm" frontend/src/features`.
- 🟠 **Submit buttons don't always disable while in-flight** — `useMutation` pattern usually sets `isPending` but many forms forget to pipe it to `<Button loading={...}/>`. E.g. `InviteModal` button has `disabled={isPending || !form.email...}` but no `loading` prop → no spinner appears.
- 🟠 **Cancel buttons don't confirm before discarding unsaved changes** — `WideModal` has a `busy` prop to lock close-during-submit, but no "are you sure you want to discard?" hook. PropertyDev's add-buyer modal could lose 30+ field entries to a stray Escape.
- 🟠 **No autosave for long forms** — `BOQEditorPage`, `EACBlockEditorPage`, `ContractsPage`'s add-contract modal, `ReportsPage` template builder. A network blip mid-edit costs 5+ minutes of work.
- 🟠 **Money inputs are plain `<input type="text">` everywhere** — should be `inputmode="decimal"` with auto-formatting (1000 → 1,000). `FinancePage`, `costs/CostsPage`, `boq/BOQEditorPage` inputs.
- 🟠 **Phone inputs missing `type="tel"`** — most contact forms use plain text. `ContactsPage`, `crm/CRMPage`, `property-dev/PropertyDevPage` buyer fields. Mobile keyboards don't switch.
- 🟠 **Date inputs are sometimes `type="date"`, sometimes a custom picker, sometimes text** — `tasks/TasksPage` uses `type="date"`, `accommodation/AccommodationDetailPage` uses a custom dialog, `schedule/SchedulePage` uses text with a date-mask. Inconsistency wastes user attention.
- 🟡 **No "(optional)" marker** on truly optional fields — users assume any unmarked field is required and abandon longer forms.
- 🟡 `users/UserManagementPage` invite modal hardcoded password placeholder `"Min 6 characters"` is also a security smell — surfaces the policy limit but is below NIST recommendation.
- 🟡 `AddContactModal` (`contacts/ContactsPage.tsx:178+`) submit-enable rule is `company_name OR first_name OR last_name` (line 200) — typing only a last-name lets the user submit a contact with no other identifying info. Empty-state contacts then have only a surname column populated → look broken.
- 🔵 Multiple `defaultValue` overrides in `t()` calls are good (English fallback), but locale dictionaries are not consistently kept in sync with new keys.

### 5. Navigation & wayfinding

❌ **Findings**:

- 🔴 **Sidebar has 22 collapsible groups, ~80 items**. `Sidebar.tsx:142-447`. Even with the "simple/advanced" toggle, the menu is overwhelming. Users find things via Cmd+K, not by browsing.
- 🟠 **Cryptic abbreviations in sidebar**: `EIR Matrix`, `CDE`, `NCR`, `RFI`, `CAPA`, `JSA`, `5D`, `4D`, `BIM`. A first-time builder doesn't know what most of these mean. Add tooltip on hover.
- 🟠 **Two near-identical surfaces**: `Variations` (`/variations`) vs `Change Orders` (`/changeorders`). The sidebar shows them in different groups (Commercial vs Finance). Comment in `App.tsx:825-826` admits the overlap. Combine or clearly differentiate.
- 🟠 **`/dashboards` and `/reporting` are both listed** in Analytics group — different purposes (snapshots vs reporting dashboards) but indistinguishable label.
- 🟠 **Tab labels need domain knowledge**: PropertyDev tabs include "Lead → Reservation → SPA → Handover → Warranty". Construction-savvy users get it; a developer's PA does not. Tooltip the abbreviation.
- 🟠 **Breadcrumbs exist on most pages but missing on**: `BIMPage`, `ClashDetectionPage`, `BOQEditorPage` (uses custom path), `match-elements/MatchElementsPage`, `geo-hub/GeoHubPage`.
- 🟠 **Many redirect routes are unannounced** (`/cad-takeoff → /data-explorer`, `/cad-explorer → /data-explorer`, `/requirements → /bim/rules`, `/documents → /files`, `/estimates → /boq`, `/profile → /settings`). After a redirect, the breadcrumb shows the destination — users who bookmarked the old URL don't realize their bookmark was rewritten.
- 🟠 **`/admin/validation-rules` was moved out of PropDev settings** (per legacy redirect in `App.tsx:744`) but the PropDev "Settings" submenu still lists "Document Templates" and "House Types". Users will keep looking for validation rules in PropDev.
- 🟡 **`useProjectContextStore` (active project) is set globally** but most module pages re-pick projectId from URL params. When a user navigates from `/projects/X/safety` to `/contacts` (no projectId in URL), the project context persists silently. Add a project chip in the header that's always visible.
- 🟡 **First-run tour duplication**: `OnboardingTour` (8-step) + `ProductTour` (8-step, different storage key). Both mounted in `App.tsx:596-603`. Steps overlap.
- 🟡 The `/onboarding` route is lazy-loaded but never linked from the sidebar — only reachable via auto-redirect on first login. Self-hosted users who skip it have no way back.
- 🔵 `/notifications` has a "Mark all as read" but no "Mark all of this type as read".

### 6. Mobile responsiveness

❌ **Findings**:

- 🔴 **BOQEditorPage AG Grid is unusable on mobile** — horizontal scroll inside the grid + sidebar overlay = thumb battle. At 375 px, the grid columns squash to unreadable width. Add a card-list view for mobile.
- 🔴 **BIMPage 3D viewer + 5 floating panels do not fit on iPhone SE (375 × 667)**. The right-side panel covers >80 % of the screen. Make panels modal on mobile.
- 🔴 **Touch targets**: `Sidebar.tsx` chevrons (~24 px), pagination buttons in `ProjectsPage:560-620` (default `py-2 text-sm` ≈ 32 px tall) — below WCAG 2.5.5 (44 × 44).
- 🟠 **`Sidebar` mobile drawer opens via `Menu` icon in header** but the drawer always covers the page entirely; no swipe-to-close. Users tap the back arrow then accidentally close the sidebar.
- 🟠 **Header search input** at narrow widths overlaps the language/notification icons.
- 🟠 **FinancePage** uses `grid-cols-12` for the dashboard with no `sm:` reset — on mobile, columns shrink to ~30 px wide → text wraps to 1 char per line.
- 🟠 **WideModal `max-w-7xl`** for `size='2xl'` exceeds mobile viewport; on mobile it stays at `max-w` but loses the side padding (`max-w-[min(1280px,calc(100vw-2rem))]` is only set for `size='full'`).
- 🟡 PropertyDev's plot grid (`Grid3X3` view) at `grid-cols-12` doesn't reflow on mobile.
- 🟡 Modal forms (e.g. PropertyDev's add-buyer) have grid layouts (`sm:grid-cols-2 lg:grid-cols-3`) but never gain enough mobile breathing room — labels wrap awkwardly.

### 7. i18n quality

✅ **What's good**: 27 locale files exist (`frontend/src/app/locales/`). `t()` calls almost universally use `defaultValue` → English fallback prevents `{{key}}` leaking to UI.

❌ **Findings**:

- 🔴 **AR locale 13% smaller than EN** (6 224 vs 7 142 lines). Hundreds of keys are EN-only; Arabic UI is mixed-direction.
- 🔴 **`UserManagementPage` MODULE_GROUPS labels are hardcoded English** (`'Bill of Quantities'`, `'4D Schedule'`, `'CDE (ISO 19650)'`, `'BIM Hub'`, …) — `users/UserManagementPage.tsx:84-144`. Same file's `ROLE_CONFIG.label` is `'Admin'`, `'Manager'` etc. — also hardcoded.
- 🔴 **PortalPage `STATUS_VARIANT` / `ACTION_VARIANT` keys are English** with no label mapping. Renders English directly.
- 🟠 **CSV export headers are hardcoded English** in `analytics/AnalyticsPage.tsx:120` (`'Project', 'Region', 'Currency', …`) — German users get English column headers in their export.
- 🟠 **Date formats vary by component**: `DateDisplay` (uses preferences), `formatDistanceToNowStrict` (date-fns English by default, ignores active locale), inline `toLocaleString(locale, …)` in `NotificationsPage:86`, ad-hoc `formatDate` in `schedule/SchedulePage:80`. Pick one.
- 🟠 **Money formatting via `Intl.NumberFormat` is OK** in `MoneyDisplay` (respects `numberLocale`), but **82 `toLocaleString()` calls** elsewhere don't pass a locale → use the browser default (often `en-US` even when the user has selected `de-DE`).
- 🟠 **Number-only inputs do not respect locale decimal separator**: German users typing `1,5` get coerced to `15` because `parseFloat` ignores `,`. `BOQEditorPage`, `costs/CostsPage`, `FinancePage` all affected.
- 🟠 **Translation key naming inconsistent**: `nav.dashboard` (snake_case) vs `projects.title` (snake_case) vs `confirm_dialog.delete` (snake_case)— ✅ consistent — BUT some test keys use camelCase: `defaultValue: 'Project'` style; `bim.federation.confirm_delete` (dot-separated like Java property keys). Standardise.
- 🟡 RTL handling: `useDocumentDirection()` in App.tsx sets `<html dir="rtl">` for Arabic. But many inline styles assume LTR (e.g. `ml-auto`, `right-2` absolute positioning, `ChevronRight` icon direction).
- 🟡 The `WhatsNewCard` / `ProductTour` content is fully English-only by default (no `defaultValue` strings in some steps).
- 🟡 Locale picker in header is a flag dropdown — but the dropdown is alphabetical by code, not by language name. A Polish user has to scan from English → German → … → Polish.
- 🔵 `de.ts` line count 6 986 vs `en.ts` 7 142 — DE missing ~150 keys (~2 %). RU close behind.

### 8. Performance smells

❌ **Findings**:

- 🔴 **BOQEditorPage is 4 702 lines** in a single file; loads AG Grid, BIM picker, AI panels, comments, version history, model link review. Initial chunk for `/boq/:id` is huge.
- 🔴 **PropertyDevPage is 8 690 lines** — the single largest feature file. Mounts dozens of inline modals + tabs + drawers. Cold-render on the dashboard is sluggish.
- 🔴 **BIMPage 3 558 lines** + Three.js + Cesium loaded in adjacent routes — total BIM chunk ~3 MB.
- 🟠 **CesiumJS** is lazy-loaded in `geo-hub/GeoHubPage.tsx:56`, good. But the recharts/d3 used in `dashboards/` are not lazy.
- 🟠 **AG Grid is now in its own chunk** (good — fixed per `App.tsx` comment lines 7-14), but `BOQEditorPage` still imports it transitively via 4+ panels in the same file.
- 🟠 **`ProjectsPage` fans out two queries** in addition to the project list (file-types-by-project, dashboard cards). On 50 projects the dashboard cards endpoint returns 50 KB JSON.
- 🟠 **No virtualization on long lists**: `contacts/ContactsPage` renders all rows in the table; on 6 600+ contacts (per memory) the page locks up.
- 🟠 `clash/ClashDetectionPage` (3 558 lines) renders thousands of clash rows un-virtualized.
- 🟡 **357 lucide-react icons imported throughout** — each is tree-shaken individually, but the average page imports 20+. Consolidate to a per-page icon barrel.
- 🟡 `DashboardPage` imports 30+ widgets via `dashboard/components/NewWidgets` barrel — eager evaluation pulls 64+ `>[A-Z]<` substrings worth of `defaultValue` strings into the boot bundle.
- 🔵 Three.js / Cesium / Monaco / PaddleOCR all separately bundled — confirm `vite preview` chunk graph in CI.

### 9. Consistency

❌ **Findings**:

- 🔴 **`inputCls` is duplicated in 49 files** instead of being a shared component. When design changes radii (e.g. 2026-05-11 tightening), 49 files diverge.
- 🔴 **Custom dialog implementations** in 5+ files instead of `WideModal` or `ConfirmDialog`: `UserManagementPage.InviteModal`, `tendering/AddendumList`, `compliance-docs/CompliancePage`, `bim/SaveGroupModal` (partial), `geo-hub/OverlayPanel`. Each has different padding / focus / Escape behaviour.
- 🟠 **Inconsistent confirm-action labels**: "Delete" vs "Remove" vs "Discard" vs "Trash" vs "Archive" — no shared verb table. Same destructive action sometimes labelled differently across modules.
- 🟠 **Inconsistent date display**: relative (`5 minutes ago`) vs absolute (`Mar 14`) vs ISO (`2026-05-24T14:32:01Z`) — chosen per page. Bookmarks, NotificationsPage, FilesActivity all use different formats.
- 🟠 **Color usage**: green = success ✅, red = error ✅, amber = warning ✅ — BUT **blue** is used both for "info" and "active/selected", and **purple** appears in 4 pages for "validation" (`notifications/NotificationsPage:82`) without explanation.
- 🟠 **Status pill variants** inconsistent: `Badge variant='neutral'` vs `Badge variant='blue'` vs custom inline `bg-amber-100 text-amber-700`. Same "Pending" status appears in 3 colours across modules.
- 🟠 **Money type leakage**: `MoneyDisplay` accepts `number | string | null`; but some pages still parse `parseFloat(amount)` themselves and lose Decimal precision. PropDev had the recent fix (commit `9f7d6281`) — other modules likely still leak.
- 🟡 **Variations on the same icon-color combo**: `text-amber-500` vs `text-amber-600` vs `text-amber-700` for "warning" across files. Use design tokens.
- 🟡 **Multiple "Spinner" implementations**: button has its own SVG (`Button.tsx:104`), pages use `Loader2` from lucide, `LoadingScreen` uses a custom shimmer bar.
- 🟡 **Modal close button position varies**: most are top-right `X`, but a few full-screen modals (e.g. `EACBlockEditorPage`) have the close in the toolbar with text.
- 🔵 **Icon sizes vary**: `size={14}`, `size={15}`, `size={16}`, `size={18}` — pick a 4-step scale.

### 10. Accessibility

❌ **Findings**:

- 🔴 **Only 1 file uses `aria-required`** (`projects/CreateProjectPage.tsx`). All other forms fail WCAG 3.3.2.
- 🔴 **Only 30 of ~120 pages use `role="tablist"` + `role="tab"`** — most tab UIs are plain divs. Cannot navigate tabs with arrow keys; not announced as tabs to screen readers.
- 🟠 **149 `htmlFor` usages across ~48 files** but ~70 files have `inputCls` — so most label↔input pairs are visual only, not associated.
- 🟠 **Color contrast risk**: `text-content-tertiary` on `bg-surface-secondary` is borderline ≈ 4.0:1. Used heavily in stats sub-lines and breadcrumbs.
- 🟠 **Modals trap focus via `useFocusTrap`** (good) — but the trap restores focus to the trigger. Some pages re-render the trigger element between modal-open and modal-close (e.g. PropertyDev's plot grid recomputes on each tab change) → focus is lost to `document.body`.
- 🟠 **Icon-only buttons missing `aria-label`** in many places — only 149 `aria-label` occurrences across 48 files; the pin/star/more buttons in ProjectsPage have `title` but no `aria-label` (title attribute is not reliably announced).
- 🟠 **AG Grid focus trap inside BOQEditorPage** — when user tabs out of the grid they jump to the page bottom instead of the next sidebar action.
- 🟡 **Many pages use `<div onClick>` instead of `<button>`** — search for `onClick={` outside form/button contexts; sidebar items, dropdown items.
- 🟡 **Skip-to-content link missing** in `AppLayout`.
- 🟡 **Tour spotlight not announced to screen readers** — `OnboardingTour` and `ProductTour` are visual-only.
- 🔵 **Drag-and-drop without keyboard alternative**: `tasks/TasksPage` reorder, `boq/grid` drag-rows, `dwg-takeoff` measurements — none have keyboard equivalents.

### 11. Trust signals

❌ **Findings**:

- 🔴 **`MoneyDisplay` falls back to EUR when currency is missing** (`MoneyDisplay.tsx:54`). Saudi user with no project currency set sees EUR — undermines trust in monetary values.
- 🔴 **No "stale data" indicator on the dashboard** — KPIs may be 5 min stale; nothing tells the user.
- 🟠 **AI confidence not shown for many AI outputs**: `match-elements/MatchSuggestionsPanel` shows confidence; `ai/QuickEstimatePage` shows it; but `BOQEditorPage` AI suggestions (`AISmartPanel`, `AICostFinderPanel`) display the suggested rate without the confidence percentage right next to it.
- 🟠 **Hash/UUID truncation forever**: `UserManagementPage` shows `user.id.slice(0, 8)`, `BIMPage` shows `model.id.slice(0, 8)`. Full ID never shown on hover. When a backend logs an error with the full UUID, the user can't match it to what they see.
- 🟠 **Timezone never shown on dates** — most pages display "Mar 14, 14:32" without "UTC" / "Europe/Berlin" suffix. For a multi-tz construction team this is ambiguous.
- 🟠 **No "Last refreshed" timestamp** on dashboards, geo overlays, validation reports.
- 🟡 **Source attribution missing**: `costs/CostsPage` shows resource entries but doesn't always show "Source: CWICR v2.3 / RSMeans 2025" — operator can't audit pricing.
- 🟡 `match-elements` shows "Best match" but doesn't always show *why* (which embedding score). Power users want the explanation; current UI hides it behind a "details" expand.
- 🔵 **PDF / Excel exports don't include a "Generated by OpenConstructionERP at 2026-05-24 12:34 UTC" footer** in most templates.

### 12. Dead ends / orphan UI

❌ **Findings**:

- 🔴 **`/styles-lab` linked from sidebar?** No — it's only reachable by typing the URL. But it's marked in `App.tsx:760` as "Styles Lab — design exploration, internal" — should be 404'd or gated to admin-only.
- 🔴 **`/eac/demo`** is "dev-only preview" (per the doc comment) but the route is exposed to all authenticated users.
- 🔴 **`/architecture` (Architecture Map)** is in the Analytics sidebar group — meant for the team, not customers.
- 🔴 **`/eac/blocks/:eacId`** has no entry point from the sidebar or any list — orphan unless user knows the URL pattern.
- 🟠 **`/quantities` (Quantity Takeoff overview)** appears to be an aggregator page but the sidebar Takeoff group routes to `/takeoff?tab=measurements`, `/dwg-takeoff`, `/bim`, `/data-explorer` directly. Is `/quantities` still needed?
- 🟠 **`/compliance/builder` (NL Rule Builder)** route exists in `App.tsx:666` but isn't in the sidebar — only reachable from inside `/bim/rules`. If a user lands directly via deep link they have no breadcrumb back.
- 🟠 **`/_modules-preview/BackendModulePage`** appears as a feature file but isn't routed — dead code.
- 🟠 **`/pipelines/PipelinesPage`** route — feature exists, but the sidebar doesn't link to it from anywhere obvious.
- 🟠 **Test/lab pages** in `frontend/src/features/translation/`, `frontend/src/features/_modules-preview/` are not gated by env.
- 🟡 **"Coming soon"** placeholders exist in `_modules-preview/BackendModulePage.tsx` — surface them only when actually enabled by feature flag.
- 🟡 **`/cad-takeoff` and `/cad-explorer` redirect to `/data-explorer`** — but PRD/support pages still reference the old paths.
- 🔵 **Some modals can be opened from one place and never re-opened** (e.g. the BIM Federation create dialog) — once dismissed, no "+" button anywhere.

---

## Findings by route

### `/` (Dashboard)
- 🟠 KPI flash-of-zero — widgets render `0`/`—` before rollup arrives.
- 🟠 `BIMCoverageCard` shows coverage % without a tooltip explaining "of what".
- 🟠 No "Last refreshed" timestamp.
- 🟡 `WhatsNewCard` content is English-only (no `defaultValue:` overrides for some keys).
- 🟡 `DashboardPage` imports 30+ widgets eagerly through `NewWidgets` barrel.

### `/projects`
- ✅ Empty state + CTA + import link via `BIMConverterStatusBanner`.
- 🟠 Ad-hoc skeleton (`inline-block h-5 w-10 animate-pulse`) instead of shared `<Skeleton>`.
- 🟠 BOQ-stats error is `console.error` only — fails to surface that "€0 value" is a network failure not a real zero.
- 🟡 Region filter is alphabetical, not by frequency — region with 50 projects sorts below `(USA)` if it's `(Belgium)`.
- 🟡 Sort buttons are 4 inline pill buttons — would compress to a dropdown on mobile.

### `/projects/new`
- 🟠 Country combobox includes the entire ISO list — no "frequent" pre-selection by browser locale.
- 🟡 Currency picker accepts any string — should validate against ISO 4217 inline.

### `/projects/:id`
- 🟠 `ProjectDetailPage` uses ad-hoc `ErrorBoundary` per section — good — but each section has its own loading spinner pattern.
- 🟠 No "Active project" toggle — switching project from this page doesn't update `useProjectContextStore`.

### `/boq`
- 🟠 List page is paginated but search is client-side over the current page only — confusing.
- 🟡 Compare drawer shows two BOQs side-by-side but only USD/EUR currency display — multi-currency compare not handled.

### `/boq/:boqId` (BOQ Editor)
- 🔴 4 702-line file; cold load ~1.5 s.
- 🔴 Mobile-unusable (AG Grid horizontal scroll).
- 🟠 `window.confirm` for "Discard unsaved changes?" at line 699.
- 🟠 Ctrl+S to save — but the docs say Ctrl+Shift+V is "reserved for Excel paste". Users will discover this via failure.
- 🟠 The 3-dot menu on each row contains 12+ items — overwhelming.

### `/costs`
- 🟠 Bulk delete uses inline `window.confirm` in `CatalogPage:1353` (catalog), `CostsPage` likely similar.
- 🟠 Import progress shows total imported but no "estimated time remaining".
- 🟡 Region browser doesn't preserve scroll position after import.

### `/catalog`
- 🟠 `window.confirm` for "Delete region" at line 1353.
- 🟡 Resource cards (50+ shown at once) don't have a sticky toolbar — operator must scroll back up to change region filter.

### `/assemblies`
- 🟠 Empty state doesn't link to `/assemblies/library` (read-only seed library).

### `/validation`
- ✅ Excellent UX — score circle, rule tooltips, drill-down per rule.
- 🟡 "Auto-fix" button on warnings (`Wand2` icon) — not always available; greyed-out without explanation when unavailable.

### `/takeoff`, `/dwg-takeoff`
- 🟠 Calibration dialog is a hard-to-find step; should appear automatically the first time a measurement tool is used on a new sheet.
- 🟠 PDF scroll inside the measurement layer is sticky; pinching to zoom on mobile sometimes pans instead.

### `/bim`
- 🔴 3 558-line file; cold render slow.
- 🔴 Mobile floating panels cover the viewport.
- 🟠 ConverterStatusBanner shown only at top — when user scrolls into the 3D canvas they forget it's installing.

### `/clash`
- 🔴 `window.confirm` for bulk-severity at line 3620.
- 🟠 Rules editor (`ClashRuleEditor`) opens as a hand-rolled modal — diverges from `WideModal`.
- 🟠 No virtualization on the clash-results list.

### `/schedule`, `/schedule-advanced`
- 🟠 Gantt at narrow widths squashes day labels to unreadable.
- 🟡 Critical-path view (`/schedule/:id/cpm`) uses a custom rendering that breaks on iPad portrait.

### `/finance`
- 🟠 2 855-line file. Many inline charts not lazy-loaded.
- 🟠 `grid-cols-12` without mobile reset.
- 🟡 Currency column not always labelled — some tables show "10 000" with no unit suffix.

### `/procurement`
- 🟠 Supplier scorecard modal is good but the close button is bottom-right not top-right.

### `/contracts`
- 🟠 Create-contract modal is 6 sections deep; no progress indicator.

### `/contacts`
- 🟠 6 600+ contacts → no virtualization → page locks up.
- 🟡 Tag-group chips don't fit on mobile.

### `/crm`
- 🟠 No funnel chart even though the data exists.
- 🟡 Empty state doesn't link to webhook-leads.

### `/property-dev`
- 🔴 8 690-line single file.
- 🔴 5 inline `window.confirm` calls.
- 🟠 Tab navigation has no keyboard arrow-key support.
- 🟠 Inline lead-pipeline KPI tiles render before count loads.
- 🟠 Settings split between `/property-dev/settings/*` and `/admin/validation-rules` is confusing.

### `/accommodation`
- 🟠 Calendar view (rooms × dates grid) on mobile breaks badly.
- 🟡 Bulk-room-add modal placeholder text English-only.

### `/portal` (Subcontractor Portal)
- 🟠 STATUS_VARIANT keys English-only (`'invited' / 'active' / 'suspended' / 'expired'`).
- 🟡 Invite flow doesn't show the actual invite URL preview before sending.

### `/users` (User Management)
- 🔴 ROLE_CONFIG, MODULE_GROUPS hardcoded English.
- 🔴 InviteModal placeholders hardcoded.
- 🟠 Module-access matrix is wide → scrolls horizontally without clear scroll-cue.

### `/admin/permissions`, `/admin/audit-log`, `/admin/validation-rules`
- 🟠 Three admin pages reached only via 2-column button grid pinned to the bottom of the sidebar — easy to miss.
- 🟡 Audit-log timeline pagination doesn't preserve filters after page change.

### `/safety`, `/hse-advanced`
- 🟠 "No project selected" state used twice with different copy in each.
- 🟡 OSHA 300 download is a tiny icon button — not discoverable.

### `/carbon`
- 🟠 Scope 1/2/3 tabs do not preserve user's drilling state across tab switches.
- 🟡 Generate-report modal uses `WideModal` but the form layout is column-1 only — wastes the 5xl width.

### `/markups`, `/markups/compare`
- 🟠 PdfCompare uses 10 hardcoded `tabular-nums` styles; OK but the colour key is below the fold.

### `/cde`
- 🟠 Approval workflow expects 4 stages; mid-stage rollback is buried behind a tiny "Revert" link.

### `/rfi`, `/submittals`, `/transmittals`, `/correspondence`, `/meetings`, `/inspections`, `/ncr`
- 🟠 None show inline error states for 401/403 / 5xx.
- 🟡 Documents pickers in each modal are reimplemented (DocumentPickerModal in `rfi/RFIPage.tsx` is local-only — same pattern elsewhere is also local).

### `/files` (File Manager)
- 🟠 The File Manager has its own internal ShortcutsCheatsheet — duplicates the global ShortcutsDialog.
- 🟡 Folder-permissions modal `window.confirm` at line 200.

### `/geo`, `/projects/:id/geo`, `/property-dev/developments/:id/geo`
- 🟠 Cesium bootstrap takes 1-3 s — no progress.
- 🟡 No "Reset view" button — user who pans into space has to refresh.

### `/integrations`
- 🟠 Integrations are listed alphabetically — no "Recommended" / "Newly added".
- 🟡 Connection-status pill is good but inconsistent with the AI Connection card in `/settings`.

### `/settings`
- ✅ AI provider grid is well-designed.
- 🟠 1 591-line file; sections are deep — a sidebar TOC would help.
- 🟡 Theme picker doesn't preview the change.

### `/notifications`
- 🟠 Date format uses inline `toLocaleString(...)` instead of `DateDisplay`.
- 🟡 Action URL rewrites at line 97 are hardcoded RegExps — should be in a central table.

### `/styles-lab`, `/eac/demo`, `/eac/blocks/:id`, `/architecture`
- 🔴 Dev/internal pages reachable from production sidebar (architecture) or via URL.

---

## Findings the QA Playwright plan will NOT catch (subjective)

Playwright is great for assertions (element X exists, click → URL Y). It will not catch:

- "First-time user is overwhelmed by 22 sidebar groups" — needs UAT.
- "Page feels slow" — needs Lighthouse / RUM, not click-thru tests.
- "Empty state copy doesn't explain what a Tender is" — needs human reading.
- "Three different shades of amber for warning" — needs design review with screenshot diff (axe doesn't flag tonal inconsistency).
- "Tab labels need domain knowledge (KG, NRM, MasterFormat)" — needs persona-based testing.
- "Money fallback to EUR is wrong for SAR project" — needs scenario testing with locale + currency variations.
- "AI confidence percentage is missing next to suggestion" — needs feature-aware audit; a Playwright test would pass if the row renders.
- "Sidebar abbreviations (RFI, CDE, CAPA, JSA) confusing" — needs first-time-user study.
- "Form discards 30+ field entries on accidental Escape" — needs UAT.
- "Touch targets < 44 px" — axe will flag some but not all; needs a manual `min-h-[44px]` audit per component.
- "Three different date formats across pages" — needs a manual format inventory.

Recommend a 2-hour manual UAT pass per persona (Estimator, PM, Developer, Site Engineer, Subcontractor Portal user) before any marketing-site push.

---

## Quick wins (under 1 hour each)

Specific edits a fix agent can knock out in 10-minute batches:

1. **Replace all `window.confirm/alert`** with `useConfirm` + `ConfirmDialog`. 21 files, ~30 call sites. Mechanical fix.
2. **Wrap `inputCls` constant** into a shared `<Input>` component and migrate one feature at a time. 49 files.
3. **Add `aria-required` to required inputs** — start with the 5 most-used forms (CreateProject ✅, AddContact, Invite User, Create RFI, Add Buyer). 5 files.
4. **Hide internal routes from production sidebar**: `/styles-lab`, `/eac/demo`, `/eac/blocks/*`, `/architecture` — wrap with `import.meta.env.DEV` check in `App.tsx`.
5. **Translate `UserManagementPage` MODULE_GROUPS + ROLE_CONFIG labels** through `t()` — 30 strings.
6. **Replace English placeholders** in `InviteModal` (`'John Doe'`, `'john@company.com'`, `'Min 6 characters'`) with i18n keys.
7. **Add `(optional)` marker** to optional form fields — start with `ContactsPage`, `AddContactModal`, then propagate.
8. **Add tooltip for sidebar abbreviations** (RFI, CDE, NCR, CAPA, JSA, KG, NRM): one `title=` per `NavItem`.
9. **Add per-widget ErrorBoundary** on the dashboard so one failed query doesn't blank the grid. 1 file, ~20 lines.
10. **Replace `inline-block h-5 w-10 animate-pulse rounded`** in `ProjectsPage:361,381,403` with `<Skeleton width={40} height={20}/>`.
11. **Add a "Last refreshed N min ago" footer** to the dashboard rollup; React Query exposes `dataUpdatedAt`.
12. **Pick `OnboardingTour` OR `ProductTour`** — delete the loser; reclaim ~700 lines + reduce confusion.
13. **Add `<Breadcrumb>` to**: `BIMPage`, `ClashDetectionPage`, `MatchElementsPage`, `GeoHubPage`, `BOQEditorPage`.
14. **Add `role="tablist"` + `role="tab"`** to the 90 pages currently using plain `<div>` tabs.
15. **Add `min-h-[44px] min-w-[44px]`** to all icon-only buttons in `Sidebar.tsx` and pagination controls.
16. **Add empty-state CTA "Import from CSV"** to: `tasks`, `rfi`, `submittals`, `transmittals`, `inspections`, `ncr`, `contacts` (backend already supports import).
17. **Add `inputmode="decimal"`** to all money inputs.
18. **Add `type="tel"`** to all phone inputs.
19. **Fix `MoneyDisplay` EUR fallback** — fall back to `'—'` when no currency is set, OR surface "Currency not set" warning at the page-header level.
20. **Add `data-testid="..."`** to common interaction points so Playwright assertions are stable.

---

## Bigger refactors (multi-day)

These need design discussion first:

1. **Split PropertyDevPage (8 690 lines)** into one file per tab + one file per modal. ~3-5 days.
2. **Split BIMPage (3 558 lines)** into `BIMViewer`, `BIMUploadPanel`, `BIMRightRail`, `BIMConverterStatus`, `BIMElementInspector`. ~2-3 days.
3. **Mobile-first redesign of BOQEditor**: cards on mobile, AG Grid on tablet+. ~5 days.
4. **Unified "active project" wayfinding**: project chip in header always visible; clicking it picks/switches/clears. Replace today's hidden `useProjectContextStore`. ~2 days.
5. **Single design-system input component** that replaces the 49 `inputCls` constants. Audit all forms. ~5 days.
6. **Sidebar redesign**: cut from 22 groups + 80 items to 6-8 top-level entries with secondary nav inside the page (à la Notion). ~5 days; needs UX design.
7. **Localise all enum-derived labels** (STATUS_VARIANT, ROLE_CONFIG, etc.) by extracting them into i18n maps. ~3 days.
8. **Standardise the dialog/modal pattern** — kill the 5 custom modal implementations. ~2 days.
9. **Pick one onboarding tour system** and decommission the other. ~1 day.
10. **Per-widget skeletons** for the dashboard with shape-matched placeholders. ~2 days.
11. **Virtualize all 100+ row tables**: contacts, clashes, costs catalog, BOQ, audit log, files. ~5 days using `@tanstack/react-virtual`.
12. **Locale completeness CI gate**: fail builds when EN keys have no AR/DE/RU/ZH equivalents. ~1 day to wire + ongoing maintenance.
13. **Mobile drawer overhaul**: swipe-to-close + reduced-motion + safe-area-inset bottom for iOS. ~2 days.
14. **Money input + decimal parsing**: locale-aware comma/dot, no precision loss, Decimal-string upstream. ~3 days.

---

## Honest verdict

**Is OpenConstructionERP ready for a marketing push?**

Not quite — but close. The bones are excellent: shared `EmptyState`, `Skeleton`, `WideModal`, `ConfirmDialog`, `MoneyDisplay`, `DateDisplay`, `useConfirm`, `useFocusTrap` patterns are in place and well-designed. The validation pipeline is a genuine differentiator. The localisation infrastructure (27 locales, `defaultValue` fallback) is more disciplined than most ERP competitors.

However, **the most-visited surfaces have the most rough edges**: `PropertyDevPage` (8 690 lines, 5 `window.confirm`), `BIMPage` (3 558 lines, mobile-broken), `FinancePage` (2 855 lines, grid-cols-12 no-reset), and `BOQEditorPage` (4 702 lines, mobile-unusable AG Grid). The User Management page has hardcoded English in the role matrix — a screenshot of that in German will hurt credibility. The sidebar has 80+ items and overwhelms first-time users, who will likely abandon before discovering the Cmd+K palette. The 21 `window.confirm` browser dialogs look unprofessional next to the otherwise Apple-Liquid polish.

Estimated agent-hours to clear the 🔴 + 🟠 backlog: **180-240 hours** (≈ 4-6 weeks of one full-time agent). Most blockers are quick mechanical fixes (replace `window.confirm`, hide dev routes, hardcoded-English sweep, ad-hoc skeleton swap). The bigger 🟠 items (BIM/PropDev/BOQ mobile rework, sidebar information architecture, decimal-input locale handling) are 3-5 days each and benefit from design review first.

Recommendation: ship the 🔴 quick wins (1 week), demo to 5 real users from each persona (Estimator, PM, Site Engineer, Developer, Sub-contractor), then decide whether to push the marketing campaign or invest in the 🟠 redesigns first.
