# Marketing-site i18n

# Marketing-site internationalization - how-to dossier

This covers the public website (`marketing-site/`) translation system only. It is fully independent of the platform's in-app i18n (`frontend/src/app/locales/*.ts`); strings are duplicated on purpose so the website ships without compiling the platform. The marketing surface is vanilla HTML/CSS/JS with no build step. Save a file, reload, done.

Important path correction: the repo's `marketing-site/CLAUDE.md` still says the shared runtime is at `assets/i18n.js`. That is stale. The real file is `marketing-site/i18n/i18n.js`, served at `/i18n/i18n.js`, and every sub-page references it as `<script src="/i18n/i18n.js" defer></script>`. If you fix the docs, fix this line.

## 1. The two runtimes

There are two near-identical i18n runtimes. They share the same locale JSON files, the same `LOCALE_VERSION`, the same `oce-lang` storage, and the same 20 locales, but they live in different places and target different DOM hooks.

A. The landing page (`index.html`) has its own INLINE runtime, an IIFE `(function i18n(){...})()` at `marketing-site/index.html` lines 20406-20607. It targets nav nodes `.lang-code`, `#lang-flag`, and the menu `.lang-menu [data-set-lang]` that the page itself defines. `LOCALE_VERSION = '20260605a'` is hardcoded at line 20468 inside `fetchLocale`. This runtime does NOT auto-inject a toggle button; it expects the landing page's own `#lang-toggle` to exist in the nav.

B. The shared runtime `marketing-site/i18n/i18n.js` (238 lines) is used by all 11 sub-pages. `LOCALE_VERSION = '20260605a'` at line 19. It is self-contained: it injects its own CSS (`injectStyles`, an `#oi18n-style` block, lines 134-156) and its own toggle button + dropdown (`buildToggle`, lines 158-216). The toggle prefers an existing nav container (`.nav-right, .nav-links, .nav-actions, .nav-cta`, line 170); if none exists it floats a button top-right (`.oi18n-float`). So a sub-page needs no nav surgery, just the one `<script>` tag and `data-i18n*` attributes.

Both runtimes MUST keep `LOCALE_VERSION` in sync. The comment at index.html line 18-19 and i18n.js line 17-18 both say so. When you change any copy, bump BOTH (currently `20260605a`; the convention is YYYYMMDD + a single trailing letter for same-day re-bumps).

## 2. Supported locales (20)

Defined identically in both runtimes (i18n.js line 21, index.html line 20408):

`en, de, fr, es, it, pt, nl, pl, cs, ru, bg, tr, sv, no, fi, da, ar, zh, ja, ko`

`en` is the source of truth; the other 19 are translations. Display names are in `LANG_NAMES`; flag country codes in `LANG_FLAGS` (note the mappings that differ from the lang code: `en->gb`, `cs->cz`, `sv->se`, `da->dk`, `ar->sa`, `zh->cn`, `ja->jp`, `ko->kr`). Flags are loaded from `https://flagcdn.com/<code>.svg`.

There is one physical JSON per locale under `marketing-site/locales/`: `en.json de.json fr.json es.json it.json pt.json nl.json pl.json cs.json ru.json bg.json tr.json sv.json no.json fi.json da.json ar.json zh.json ja.json ko.json`.

## 3. The attribute contract

Mark any translatable node with one of these attributes. The key is a dotted path into the locale JSON (resolved by `get(obj, path)` which splits on `.` and walks the object; returns `null` on a missing segment so untranslated keys keep their hardcoded English fallback in the HTML).

- `data-i18n="dotted.key"` - sets `el.textContent` (plain text). Most common.
- `data-i18n-html="dotted.key"` - sets `el.innerHTML`. Use ONLY when the translated value legitimately contains inline markup (`<em>`, `<br>`, `<span class>`, `<strong>`, `<a href>`). The merge tooling validates the HTML tag multiset, so the translation must keep the same tags.
- `data-i18n-attr="attr:dotted.key"` - sets an arbitrary attribute. Format is `attr:key`; comma-separate several pairs in one attribute (e.g. `title:foo.bar,placeholder:foo.baz`). Parsed at i18n.js lines 58-66. Only the shared runtime supports this; the index.html inline runtime does NOT implement `data-i18n-attr` (it only handles `data-i18n`, `data-i18n-html`, and `data-i18n-aria-label`).
- `data-i18n-aria-label="dotted.key"` - sets the `aria-label` attribute (a11y). Both runtimes support it (index.html applies it via the same `apply` flow; shared runtime at lines 67-70).

The HTML must always carry a sensible English fallback as its literal content/attribute, because if the locale fetch fails or the key is missing, nothing is overwritten and the literal stays. `_i18n_build_en.py` later reads those literals straight back out as the en.json source values.

## 4. Language detection order

`detectSync()` (i18n.js 106-116, index.html 20495-20505) resolves synchronously in this priority:
1. URL `?lang=xx` if `xx` is in SUPPORTED. Marked `fromUrl: true`, which freezes the choice (no geo upgrade).
2. `localStorage['oce-lang']` (constant `STORAGE_LANG = 'oce-lang'`).
3. `navigator.language` first two chars, lowercased, if supported.
4. Fallback `en`.

Then, only if the language was NOT chosen by URL and `localStorage['oce-lang-manual']` is unset, an async GeoIP upgrade runs: `detectGeo()` fetches `https://ipwho.is/?fields=country_code` (3s AbortController timeout), maps the country via `COUNTRY_TO_LANG`, and switches if it differs. `COUNTRY_TO_LANG` (i18n.js 26-39) maps ~80 countries, e.g. `AT/CH/LI->de`, `BR->pt`, `MX/AR/CL...->es`, the full Arabic-world set `->ar`, `TW/HK/SG->zh`. Picking a language from the dropdown sets `oce-lang-manual=1`, which permanently disables geo override for that browser.

`setLang(lang, manual)` writes `document.documentElement.lang`, sets `dir` (RTL handling below), persists to localStorage, and rewrites the URL `?lang=` via `history.replaceState` (drops the param entirely for `en`).

## 5. RTL handling

`RTL` is `{ ar: true }` (i18n.js 25) / `new Set(['ar'])` (index.html 20414). On every `setLang`, `document.documentElement.dir = RTL[lang] ? 'rtl' : 'ltr'`. Arabic is the only RTL locale. There is no per-component RTL CSS beyond what the global `dir` attribute drives, so if you add RTL-sensitive layout, test `?lang=ar`.

## 6. The auto-injected toggle (shared runtime only)

`buildToggle()` creates `#oi18n-toggle` (flag + 2-letter code) and a `#oi18n-menu` dropdown listing all 20 languages with flag, code, and native name. It appends into the first matching nav container or floats top-right. Click handling, Escape-to-close, and resize-close are wired at lines 199-215. The current flag/code update and `is-current` highlighting happen in `apply()` (lines 71-77) via `.oi18n-code`, `#oi18n-flag`, `#oi18n-menu [data-set-lang]`. The landing page's inline runtime uses the page's own classes instead (`.lang-code`, `#lang-flag`, `.lang-menu`) and does not inject styles.

Both expose `window.__oceI18n = { setLang, SUPPORTED }` for console debugging.

## 7. Locale file layout and the `page` namespace

`en.json` has 2843 leaf keys across 28 top-level groups. Homepage keys are the flat groups: `nav, hero, final_cta, sections, demo, community, numbers, tour, compare, video_intro, modular_universe, module_lab, developers, voices, pricing, license, faq, install_cta, footer, newsletter, popup, custom, cookie, workshops, trust, ddc, modgrid`. These power `index.html`.

The 11 sub-pages live entirely under one namespace: `page.<slug>.<key>`. The slugs and their en key counts are:
- `page.download` (69) -> download.html
- `page.partners` (325) -> partners.html
- `page.services` (304) -> services.html (Practices)
- `page.standards` (240) -> standards.html
- `page.industries` (189) -> industries.html
- `page.news` (80) -> news.html
- `page.docs` (814) -> docs.html
- `page.contact` (36) -> contact.html
- `page.license` (58) -> license-request.html (note slug is `license`, not `license-request`)
- `page.demo` (53) -> demo-register.html (note slug is `demo`)
- `page.imprint` (27) -> imprint.html

Two slug names do not match their file name: `page.license` serves `license-request.html` and `page.demo` serves `demo-register.html`. Remember this when instrumenting or extracting.

Current coverage: en = 2843 leaf keys. All 19 translated locales = 2822 leaf keys each. The 21-key gap is the one real outstanding work item (see section 10). `page_present=True` in every locale.

## 8. Instrumented pages and runtime wiring (verified)

Every sub-page references the shared runtime. Confirmed by grep for `/i18n/i18n.js`:
contact.html:430, demo-register.html:742, download.html:808, docs.html:1125, imprint.html:90, industries.html:1277, news.html:1016, license-request.html:785, partners.html:3997, standards.html:1862, services.html:1729.

That is the full set of 11 sub-pages. `index.html` is NOT in that list because it uses its own inline runtime (correct by design). So all 12 user-facing HTML pages are instrumented: the 11 sub-pages via the shared script plus the landing page inline. The older `news/v*.html` release articles are frozen English snapshots and are not i18n-instrumented.

Instrumentation density (data-i18n* attribute count per file): docs 814+, partners 325+, services 304+, standards 240+, industries 189+, news 80+, download 69+, contact 36+, license 58+, demo 53+, imprint 27. download.html has ~75 data-i18n occurrences and is fully wired.

## 9. Translation tooling (repo-root scripts)

All three live at repo root, run with the system Python (they import `bs4`/`lxml` for the extractor). They operate on `marketing-site/locales/` resolved relative to the script's own directory.

`_i18n_build_en.py` - the EXTRACTOR. `python _i18n_build_en.py page1.html page2.html ...` (page paths relative to `marketing-site/` or absolute). For each page it parses the HTML with BeautifulSoup and reads the ground-truth English value straight from each instrumented node: `[data-i18n]` -> `get_text()`, `[data-i18n-html]` -> `decode_contents()` (raw inner HTML), `[data-i18n-attr]` -> the named attribute value, `[data-i18n-aria-label]` -> the `aria-label`. It `set_nested`s each dotted key into `en.json` under its existing structure and rewrites en.json. It reports total keys written, per-page counts, and any "same key, different value" conflicts. Reading values from the HTML (not from an agent's JSON report) avoids HTML-escaping artifacts and guarantees en.json matches the page's English fallback exactly.

`_i18n_pages_gen.py` - the WORKFLOW GENERATOR. Reads only the `page` namespace from en.json, flattens to dotted `page.<slug>.<key>`, chunks into 300-key batches (`CHUNK = 300`), and writes `_i18n_pages_workflow.js`. That generated workflow fans out one translation agent per (locale x chunk) for the 19 non-English locales (`LOCALES` at line 15). It prints `page gap keys / chunks / agents`. The embedded agent prompt enforces the rules that matter: preserve all HTML markup and attribute values exactly, preserve placeholders (`{name}`, `%s`, `%d`), keep a fixed GLOSSARY of brand/technical terms verbatim (OpenConstructionERP, DDC, GAEB, BOQ, DIN, NRM, MasterFormat, CWICR, IFC/DWG/RVT, PyPI, PostgreSQL, BIM/CAD, RFI/RFQ/NCR/MoC/EVM, GAEB XML/X83/X84, etc.), keep version strings / currency codes / emails unchanged, and never use the em-dash (render as hyphen or comma). Output is via StructuredOutput `{ loc, translations }`.

`_i18n_pages_merge.py` - the MERGER/VALIDATOR. `python _i18n_pages_merge.py <workflow-output.json>`. Locates the result array (handles a bare list or several wrapper-key shapes). For each `{loc, translations}` it accumulates across chunks, then for each key: skips if not present in en or not a string (`not-in-en`); un-escapes over-escaped HTML (`&lt;`->`<` etc.) when the English value contains `<` or `&`; rejects the value if the sorted HTML-tag multiset differs from English (`tag-mismatch`), if the placeholder set differs (`placeholder-mismatch`), or if blank (`empty`); otherwise `set_nested`s it. It only ever writes `page.*` keys; everything else in each locale is untouched. It preserves each file's original ASCII-ness (`ensure_ascii=ascii_orig`) and adds a trailing newline. It prints per-locale merged/skipped counts with reasons. This is the safety net that makes broken markup impossible to ship.

There is also `_i18n_merge.py` at repo root, an older sibling of the pages merger that hardcodes a task-output path (lines 14-16) and is not page-namespace-scoped. Prefer `_i18n_pages_merge.py` for sub-page work. Other helpers exist under `marketing-site/` (`_i18n_chunk.mjs`, `_i18n_dedup.mjs`, `_i18n_gap.mjs`, `_i18n_merge.mjs`) and were used for homepage/whole-locale sweeps; the canonical sub-page flow is the three Python scripts above.

## 10. Procedures

### (a) Translate a NEW page
1. Instrument the HTML: add `data-i18n*` attributes to every translatable node, each with a `page.<newslug>.<key>` dotted key and a literal English fallback. Add `<script src="/i18n/i18n.js" defer></script>` near the end of `<body>`. (Landing-style inline runtime is only for index.html; sub-pages always use the shared script.)
2. Extract English: `python _i18n_build_en.py <newpage>.html`. Verify no key conflicts in the report and that `en.json` now has your `page.<newslug>.*` keys.
3. Generate the workflow: `python _i18n_pages_gen.py` (it picks up the whole `page` namespace; new keys included). Check the printed key/chunk/agent counts.
4. Run `_i18n_pages_workflow.js` through the orchestration to produce a results JSON.
5. Merge: `python _i18n_pages_merge.py <results.json>`. Review the skipped report for tag/placeholder mismatches and fix those values manually if needed.
6. Bump `LOCALE_VERSION` in BOTH `index.html` (line ~20468) and `i18n/i18n.js` (line 19) to a new stamp.
7. Smoke test: `python -m http.server 8000` in `marketing-site/`, open `http://localhost:8000/<newpage>.html?lang=de` (and `?lang=ar` for RTL), confirm strings switch and no console errors.
8. Add the page to the global nav, `llms.txt`, and the SEO `<head>` block per the site CLAUDE.md done-criteria.

### (b) Re-translate after copy changes
1. Edit the English literals directly in the HTML (and/or add new `data-i18n*` keys).
2. Re-extract: `python _i18n_build_en.py <changed pages...>`. This overwrites the affected en.json values with the new ground truth. (Note: the extractor does NOT remove now-orphaned keys; prune dead keys by hand if a string was deleted.)
3. Regenerate + run + merge as in (a) steps 3-5. The merger only rewrites keys the agents returned, so untouched translations stay put; changed English keys get fresh translations.
4. Bump `LOCALE_VERSION` in both runtimes (this is what forces cached locale JSON to refresh for existing users via the `?v=` query string in `fetchLocale`).
5. Smoke test a couple of locales.

## 11. Known gotchas

- The CLAUDE.md `assets/i18n.js` path is wrong; the live path is `/i18n/i18n.js`. Do not create an `assets/` copy; fix references to point at `i18n/i18n.js`.
- Two runtimes, one version constant duplicated in two places. Forgetting to bump either one means stale cached copy for some users. The index.html inline runtime additionally lacks `data-i18n-attr` support, so any homepage node needing a translated attribute (other than aria-label) will not work; use `data-i18n-aria-label` or move to inner text.
- Slug-vs-filename mismatch: `license-request.html` -> `page.license`, `demo-register.html` -> `page.demo`.
- The merger silently keeps the English fallback for any value whose tags or placeholders diverge. Always read the printed skip report; a high `tag-mismatch` count means the agents mangled markup and those strings are still English on the live site.
- Locale fetch is graceful: a missing key or a failed fetch leaves the HTML literal in place. This is why every node needs a real English fallback baked into the HTML, and why partial translation coverage does not break a page.
- Byte-identical-to-English values are not automatically gaps. Many are correct brand nouns (GitHub, Demo, Cashflow). But the audit also surfaces genuine misses (e.g. `tour.info_chip2_default = 'Region'` left English in de). Judge case by case; do not blindly re-translate brand terms.
- One mojibake artifact exists in some homepage values, e.g. `community.hero_eyebrow` and `license.size_1_5 = '1 ? 5'` show a replacement char where a separator should be. This predates the page workflow and lives in the homepage namespace, not `page.*`, so the pages merger will not touch it. Fix in en.json + re-sweep the homepage if you clean it up.

## 12. Current outstanding work (the only translation gap)

21 keys exist in `en.json` but are missing from all 19 translated locales (en = 2843 leaf keys, each translated locale = 2822; exact 21-key delta). They are all on the Practices/services page module tiles, used as `data-i18n-aria-label` (verified at services.html lines 820 and 835, e.g. `page.services.mod_bimhub_title`, `page.services.mod_costs_title`). Full list:

`page.services.mod_bimhub_title, mod_cadimport_title, mod_requirements_title, mod_costs_title, mod_costmodel_title, mod_assemblies_title, mod_takeoff_title, mod_dwgtakeoff_title, mod_match_title, mod_validation_title, mod_compliance_title, mod_bimrules_title, mod_rfqbid_title, mod_procurement_title, mod_projectai_title, mod_schedule_title, mod_finance_title, mod_risk_title, mod_changeorders_title, mod_erpchat_title, mod_docscde_title`.

Why it matters: these are the aria-labels (accessibility) for the module tiles on services.html. In any non-English locale they currently fall back to English. Impact is low (screen-reader labels only, page still works), but it is the one piece that completes the translation matrix.

Fix: run procedure (b) targeting services.html (`python _i18n_build_en.py services.html` is already done since the keys are in en.json; just `python _i18n_pages_gen.py`, run the workflow, then `python _i18n_pages_merge.py <out.json>`), then bump LOCALE_VERSION in both runtimes. Acceptance criteria: all 20 locale files report 2843 leaf keys with no `page.services.mod_*_title` missing; `?lang=de` etc. on services.html shows translated tile aria-labels; merge report shows 0 tag/placeholder mismatches for these keys.

## 13. Quick reference - key file paths

- Shared runtime: `C:\Users\Artem Boiko\Desktop\CodeProjects\ERP_26030500\marketing-site\i18n\i18n.js`
- Landing inline runtime: `marketing-site\index.html` lines 20406-20607 (LOCALE_VERSION at 20468)
- Locales: `marketing-site\locales\<lang>.json` (en.json is source of truth)
- Extractor: `_i18n_build_en.py` (repo root)
- Workflow generator: `_i18n_pages_gen.py` -> writes `_i18n_pages_workflow.js`
- Merger: `_i18n_pages_merge.py`
- Local preview: `cd marketing-site && python -m http.server 8000`
</dossier>
<parameter name="open_questions">["The marketing-site/CLAUDE.md documents the shared runtime path as assets/i18n.js, but the live file is at i18n/i18n.js and all 11 sub-pages reference /i18n/i18n.js. The CLAUDE.md is stale and should be corrected, but I could not confirm whether any deploy artifact or Caddy rule still expects an assets/ path.", "The dossier brief states current published version is v6.9.0, but git log shows the latest release commit as v6.8.0 (89238c030) and the project memory's current entry is v6.8.2. I did not find a v6.9.0 tag/commit in the marketing-site i18n history, so the exact current version is ambiguous from this domain's files.", "Some homepage-namespace values contain a mojibake replacement character (e.g. license.size_1_5 = '1 ? 5', community.hero_eyebrow). This is outside the page.* namespace the page tooling manages, so I could not confirm whether a homepage-locale re-sweep is planned or whether these render acceptably in production.", "Whether the 132 byte-identical-to-English values in de.json (and similar in other locales) are all intentional brand terms or include genuine untranslated strings was not exhaustively audited per locale; only a sample was reviewed. A full pass via the /i18n-sweep skill would be needed to separate legitimate brand nouns from real gaps.", "I did not verify whether _i18n_pages_gen.py overwrites _i18n_pages_workflow.js cleanly when only a subset of pages changed, or whether stale chunks from a prior run could leak in; the script regenerates from the full page namespace each time, which appears safe, but this was not exercised end to end."]
