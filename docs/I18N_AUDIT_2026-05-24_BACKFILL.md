# i18n Backfill Audit — Wave 2026-05-24

**Date:** 2026-05-24 (continued into 25)
**Branch:** `i18n/wave-2026-05-24-backfill-all-locales`
**Base:** `v4.8.0` (`c734064e`). Originally cut from `v4.7.2` (`8623a274`); the upstream branch ref advanced to `v4.8.0` mid-session, so the final wave folds in the additional v4.8.0 keys as well.
**Scope:** Translations for every i18n key added during the previous two days (since 2026-05-22 morning, parent of `0f82fe3e`).

---

## Summary

Two consecutive sub-waves applied to a single branch:

- **Sub-wave 1 (97-key burst added before v4.7.2)** — 797 EN keys: PropDev plot form + inventory map, What's New v4.5, product tour, header subscribe, accommodation calendar, chat AI banner + contextual chips, geo overlays, country picker, sidebar editor.
- **Sub-wave 2 (181 keys added in v4.8.0)** — pricing engine UI (95 keys), accommodation UX overhaul (41 keys), geo_hub autocomplete + cache admin + drift indicator (39 keys), multi-currency rollup (4 keys), one common + one projects key.

All 978 keys land in six priority locales.

| Locale | Missing before | Missing after | Net new keys translated |
|--------|---------------:|--------------:|------------------------:|
| **DE** (German)  | 289 | 0 | **289** |
| **RU** (Russian) | 289 | 0 | **289** |
| **FR** (French)  | 456 | 0 | **456** |
| **ES** (Spanish) | 456 | 0 | **456** |
| **IT** (Italian) | 456 | 0 | **456** |
| **AR** (Arabic)  | 456 | 0 | **456** |
| **Total**        | **2,402** | **0** | **2,402** |

Baseline coverage of these 978 keys:
- DE/RU: 70% (Waves 11–12 had already covered 689 keys via inline edits)
- FR/ES/IT/AR: 53% (522 keys covered, mostly module nav + UserManagement from earlier waves)

After this wave: 100% coverage across all six priority locales for everything added in the previous two days.

---

## How keys were identified

```
git diff <first-2-day-commit-parent>..HEAD -- frontend/src/app/locales/en.ts \
  | grep -E '^\+\s+"[^"]+":' \
  | sed -E 's/^\+\s+"([^"]+)":.*/\1/'
```

Yielded 978 new keys. The first commit inside the 2-day window touching the EN locale file is `0f82fe3e` (2026-05-23 08:40 +0200, `feat(property-dev): deep PropDev pass`); the diff base is its parent `6ff6e767`.

Coverage per locale was then computed by checking literal `"<key>":` presence in each locale `.ts` file (case-sensitive, exact match).

---

## Key groups (by frequency, both sub-waves)

| Prefix | Keys | Notes |
|--------|-----:|-------|
| `propdev.*`         | 220 | Plot form, inventory map, dashboards hub, pricing engine (lists / rules / simulator / quote history), buyers pipeline |
| `accommodation.*`   |  65 | Calendar (rooms × dates), summary cards, bookings list, charges UX, settings hint |
| `geo_hub.*`         |  39 | Address autocomplete, coords format picker, Nominatim cache admin, drift indicator |
| `whatsnew.*`        |  37 | v4.5.0 release-notes carousel + chips + 6 highlight cards (b1/b2/b3) |
| `chat.*`            |  23 | No-AI-key banner, contextual page chips, RBAC manager-required error |
| `tour.*`            |  22 | 8-step product tour copy |
| `nav.*`             |  15 | New nav targets (Architecture Map, Snapshots, EIR Matrix, etc.) + Pinned/Recent ergonomics |
| `header.subscribe.*`|  14 | Subscribe-to-news widget |
| `sidebar.*`         |   9 | Editor for hiding nav items |
| `country_combobox.*`|   6 | New country picker (with custom-region + keyboard hints) |
| `contacts.*`        |   5 | PropDev/broker/vendor/subcontractor tags |
| `multiCurrency.*`   |   4 | Cross-currency total chip strip |
| `bim.*`             |   4 | Outdated-converter overlay UX |
| `geo.overlays.*`    |   3 | Empty-state CTA + show/hide a11y labels |
| `common.*`          |   1 | Reusable "Clear filters" |
| `projects.*`        |   1 | "Search address" projects-form label |

---

## Translation principles applied

Per project policy (the architecture guide, German construction vocab, RU industry terms, etc.):

- **DE**: construction/real-estate German — *Bauträger* (developer), *Leistungsverzeichnis (LV)* (BOQ), *Aufmaß* (takeoff), *Mängel* (snags), *Treuhand* (escrow), *Übergabe* (handover), *Gewährleistung* (warranty), *Nachträge* (variations/change orders), *Kollisionsprüfung* (clash detection), *Preisliste* (price list), *Geocode-Cache* (geocode cache), *Vorrang-Erklärung* (precedence explanation).
- **RU**: industry RU — *спецификация работ/BOQ*, *застройщик*, *Эскроу*, *передача*, *гарантия*, *Снимки*, *прайс-лист*, *перепривязать* (re-anchor), *маркер* / *якорь* for anchor depending on context. Loanwords preserved for product names (BIM Hub, Geo Hub, PropDev, Nominatim) per established locale-file convention.
- **FR**: *DQE* (Devis Quantitatif Estimatif) for BOQ, *promoteur immobilier* (real-estate developer), *réservation/compromis* (reservation/sales contract), *livraison* (handover), *journal de chantier* (daily diary), *réserves* (snag list), *avenants* (change orders), *clash* (loanword kept — standard in FR BIM), *liste de prix* (price list), *géocodage* (geocoding), *ancrage / ré-ancrer* (anchoring).
- **ES** (es-ES): *promotor inmobiliario*, *compraventa* (sales contract), *entrega* (handover), *repasos* (snags), *órdenes de cambio* (change orders), *diario de obra* (daily diary), *lista de precios* (price list), *anclaje / re-anclar* (anchor / re-anchor). Civil-engineering terms preferred over LatAm variants (*plaza de aparcamiento* not *estacionamiento*).
- **IT**: *Edilizia / promotore immobiliare*, *computo metrico estimativo (CME)*, *compromesso* (sales contract), *consegna* (handover), *riserve* (snag list), *varianti* (change orders), *giornale di cantiere* (daily diary), *listino prezzi* (price list), *capitolato* style preserved in form labels.
- **AR**: Modern Standard Arabic. RTL-aware (no LTR-only punctuation forced). Construction-industry vocab: *المطور العقاري* (real-estate developer), *جدول الكميات (BOQ)*, *عقد البيع* (sales contract), *التسليم* (handover), *الضمان* (warranty), *العيوب* (snags), *يوميات الموقع* (daily diary), *كشف التعارضات* (clash detection), *قائمة الأسعار* (price list), *الترميز الجغرافي* (geocoding), *مرتكز / إعادة المرتكز* (anchor / re-anchor). Direction arrows kept LTR (`→`, `↑↓`) when they form part of a Latin-origin technical glyph; mailto fallback uses `←` to follow Arabic reading flow.

Product-name brand strings (`PropDev`, `BIM Hub`, `Geo Hub`, `Cesium`, `Nominatim`, etc.) intentionally not translated — they are product identifiers across all locales.

`{{placeholder}}` interpolation tokens preserved exactly as in EN — no localised reorder where the placeholder grammar was ambiguous.

---

## Quality gates

- `npm run lint:unicode` — no zero-width Unicode characters detected outside the allowed `src/app/locales/ar.ts` (which legitimately contains Arabic). PASS.
- `npm run typecheck` — the 13 pre-existing `src/features/property-dev/*.tsx` errors flagged by the v4.8.0 release commit are **NOT** introduced by this wave (verified by re-running tsc with locale files reverted: same 13 errors). Locale files themselves contribute zero TS errors — they remain valid `{ translation: Record<string, string> }` shape.
- Manual file-end check — every locale file still ends with the canonical resource close block:
  ```ts
    // --- /i18n v4.8.0 backfill ---
    }
  } as { translation: Record<string, string> };

  export default resource;
  ```
- Marker comments — each file carries two annotated block delimiters: `// --- i18n wave 2026-05-24 backfill (N keys) ---` and `// --- i18n v4.8.0 backfill (N keys) ---`. Future audits can grep these to attribute keys to this wave.

---

## Keys intentionally NOT translated (top 5 + reasons)

All 2,402 net additions were translated in this wave. There are however a few values where the canonical form is intentionally kept English-loan or product-brand across locales:

1. **`whatsnew.v450.propdev.chip` = `"PropDev"`** — product short-name. Same in all 6 locales.
2. **`whatsnew.v450.geo.chip` = `"Geo Hub"`** — product name. Same across all locales.
3. **`tour.step.4.title` = `"BIM Hub"`** and **`tour.step.6.title` = `"Geo Hub"`** — product names; transliteration would harm searchability.
4. **`chat.panel.ctx_geo.clashes` → "clash"/"clashes" in FR/IT** kept as loanword in FR/IT (standard in industry BIM glossary; native equivalents like FR *conflit géométrique* are wordy and less recognised in tooling UIs).
5. **`header.subscribe.email_placeholder`** — placeholder kept locale-appropriate but minimal (`sie@beispiel.de`, `вы@example.com`, `vous@exemple.com`, `usted@ejemplo.com`, `tu@esempio.com`, `you@example.com`). The AR form keeps the EN form to avoid implying a real third-party email pattern.

A handful of priority-acronym strings (`Pri` short label) were rendered as transliterated 2-char abbreviations because the column width is fixed; full localisation would overflow. This is the only place this trade-off is applied.

---

## Notes for the next backfill wave

- Wider locales (`pt`, `pl`, `ja`, `ko`, `zh`, `nl`, `cs`, `bg`, `hr`, `fi`, `da`, `no`, `sv`, `ro`, `th`, `vi`, `tr`, `id`, `hi`, `mn`) are not covered by this wave. The previous full audit (`docs/I18N_AUDIT_2026-05-24.md`) shows their baseline gaps; the 978 new keys would push them deeper. Recommend a follow-up sweep that re-uses the translation tables from the two backfill scripts (DE/RU as the Cyrillic/Germanic anchor, FR as the Romance anchor) and machine-extends to the remaining 21 locales with light human review on construction vocab.
- The split-script generator (`scripts/split-i18n-fallbacks.mjs`) comment in each locale file warns "Do not edit by hand". This wave edits the locale files directly because the legacy fallback file is monolithic and the project has moved away from it; future backfills should follow the same pattern of appending a marked block before `}\n} as { translation:`.
- Two block markers (`// --- i18n wave 2026-05-24 backfill ---` and `// --- i18n v4.8.0 backfill ---`) mark the boundaries of this contribution; they should remain stable so subsequent waves can locate and append without disturbing them.

---

## Branch

`i18n/wave-2026-05-24-backfill-all-locales` — branched from `8623a274` (v4.7.2) and rebased onto `c734064e` (v4.8.0) when upstream advanced mid-session.

Single commit prefix `i18n:`. No `--no-verify`. No force-push.
