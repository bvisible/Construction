# Partner Packs — Onboarding & Reference Guide

**Status:** stable since v5.6.0 (2026-05-28)
**Audience:** integration partners, white-label resellers, regional consultancies
**Source code:** `backend/app/core/partner_pack/`
**Reference packs:** `packs/<slug>/`

---

## 1. What a partner pack is

A **partner pack** is a pip-installable Python wheel that pre-configures a
vanilla OpenConstructionERP install for a specific region, industry vertical,
or partner brand. It is the smallest possible unit of customisation: one
manifest plus a handful of static assets (logo, locale JSON, onboarding
script, validation rule-pack JSON files).

Conceptually, a pack answers seven questions at boot:

1. **Who am I?** (`partner_name`, `partner_url`, `slug`)
2. **What does the workspace look like?** (`branding.primary_color`,
   `branding.accent_color`, `branding.logo_path`, `branding.favicon_path`)
3. **What language and money?** (`default_locale`, `additional_locales`,
   `default_currency`, `default_tax_template`)
4. **Which cost catalogues should load first?** (`cwicr_regions`)
5. **Which validation rules apply by default?** (`validation_rule_packs`)
6. **Which modules should the sidebar emphasise / hide?** (`default_modules`,
   `hidden_modules`)
7. **How does a brand-new user get oriented?** (`onboarding_script_path`)

That's it. Packs are **declarative presets**, not plugins. Everything they
configure already exists in the core — they just flip switches and supply
brand assets.

### Why packs are not modules

| Concern | Modules (`backend/app/modules/<name>/`) | Partner packs (`packs/<slug>/`) |
|---|---|---|
| What they add | New tables, routes, frontend pages, business logic | Configuration of existing features |
| Installation | Drop folder into `backend/app/modules/`, restart | `pip install <pack>`, restart |
| Discovery | File-system scan by `core/module_loader.py` | Python entry-points group `openconstructionerp.partner_packs` |
| Database | Owns Alembic migrations | None — packs MUST NOT touch the schema |
| Frontend | Owns React routes under `features/<name>/` | None — packs MUST NOT add routes |
| Activation | All enabled modules load simultaneously | **Exactly one pack is active per install** |
| Versioning | SemVer, independent per module | SemVer, independent per pack |

If you need a brand-new database table or a brand-new sidebar route, write a
module. If you need to ship "the German BIM consultancy edition" — colours,
locale, DIN rules pre-enabled — ship a pack.

---

## 2. Hard constraints (what packs CANNOT do)

These are enforced by the architecture, not by code review. Violating them
will not work — the loader has no path to register them.

- **No new Python modules.** A pack's wheel is not scanned by
  `module_loader.py`. There is no entry-point group for modules.
- **No new frontend routes.** The React bundle is compiled at the core's
  build time (`frontend/dist/`). Packs cannot inject routes, components, or
  JS chunks at runtime.
- **No new database tables.** Packs ship no Alembic migrations and no
  SQLAlchemy models.
- **No new REST endpoints.** All HTTP surface lives in core modules; packs
  only configure existing endpoints.
- **No new validation rule classes.** Packs reference rule-pack **slugs** that
  already exist in `backend/app/core/validation/rules/`. The JSON files
  shipped under `rule_packs/` are reference data and documentation for the
  partner; they are not loaded as executable rules by the core.
- **No code execution at boot beyond manifest construction.** The pack's
  `__init__.py` should expose `MANIFEST` and nothing else. Side-effects
  there break test isolation and the discovery cache.
- **No multi-tenant support in v5.6.x.** Exactly one pack is active per
  install (selected by `OE_PARTNER_PACK` env var, or first alphabetically).
  Hosted multi-tenant pack selection is reserved for a future major.

If a partner requires any of the above, the answer is "ship a module under
`backend/app/modules/`, not a pack." See `docs/module-development/quickstart.md`.

---

## 3. File layout of a pack

Every reference pack under `packs/` follows the same shape:

```
packs/<slug>/
├── pyproject.toml                              # build + entry-point registration
├── README.md                                   # (optional) partner-facing readme
└── src/
    └── openconstructionerp_<slug_underscored>/
        ├── __init__.py                         # exposes `MANIFEST`
        ├── manifest.py                         # PartnerPackManifest(...) builder
        ├── logo.svg                            # required — partner logo
        ├── favicon.ico                         # optional — browser favicon
        ├── onboarding.yaml                     # optional — first-login script
        ├── locales/
        │   ├── en.json                         # optional — extra locale strings
        │   └── de.json
        └── rule_packs/
            ├── <slug>.json                     # reference data for the partner
            └── ...
```

### Naming rules

- **Distribution name** in `pyproject.toml`: `openconstructionerp-<slug>` —
  hyphens, lowercase, kebab-case. Example: `openconstructionerp-batimatech-ca`.
- **Python package** under `src/`: `openconstructionerp_<slug_underscored>` —
  underscores, lowercase. Example: `openconstructionerp_batimatech_ca`.
- **Manifest slug** (`PartnerPackManifest.slug`): same as the distribution
  suffix, kebab-case. Example: `batimatech-ca`. Must match the regex
  `^[a-z][a-z0-9\-]{2,40}$`.
- **Entry-point key**: matches the slug exactly.

The three names are deliberately redundant so the loader can cross-check
them and fail fast if a pack is mis-wired.

---

## 4. The 10 reference packs

All ten live under `packs/` in the monorepo. They install as separate
wheels and are independent of the core release cycle.

| Slug | Region | Currency | Locale(s) | Rule packs | Notes |
|---|---|---|---|---|---|
| `batimatech-ca` | Canada | CAD | fr-CA, en-CA | NBC 2020, CCDC 2, CSA A23 | Full reference — favicon + bilingual locales + onboarding |
| `bimhessen-de` | Germany (Hessen) | EUR | de | DIN 276, GAEB X83/X86, VOB 2023, ISO 19650 CDE, BKI | German BIM consultancy preset |
| `doker-formwork` | Germany | EUR | de | DIN 18218, formwork-cycle rules | Formwork-supplier vertical |
| `uk-jct` | United Kingdom | GBP | en-GB | NRM 1 + NRM 2, JCT clauses, BCIS | UK GC preset |
| `us-rsmeans` | United States | USD | en-US | MasterFormat 2018, AIA A201-2017, RSMeans CCI | US GC preset |
| `aus-nzs` | Australia / NZ | AUD | en-AU | AS 1684, NZS 3604, Rawlinsons, AS 4000 | AU/NZ residential + commercial |
| `brazil-sinapi` | Brazil | BRL | pt-BR | NBR 12721, RPS PDF, SINAPI | Latam tier-1 |
| `india-cpwd` | India | INR | en-IN, hi | CPWD, IS standards, DSR | Indian public-works |
| `saudi-vision2030` | Saudi Arabia | SAR | ar, en | SBC, MoMRAH, Aramco standards | KSA mega-projects |
| `renewables-epc` | Cross-region | EUR | en | IEC 61400 wind, IEC 61730 PV, MV cables, LCOE, grid compliance | Renewables EPC vertical |

> The `v5_6_0_release.md` memory mentions 5 packs (the first wave). Five more
> were added in the same wave as additional reference implementations. Total
> shipped in v5.6.0 = **10 packs**.

### Quick install — single pack

```bash
pip install openconstructionerp openconstructionerp-batimatech-ca
# optional: explicitly pin which pack is active
export OE_PARTNER_PACK=batimatech-ca   # PowerShell: $env:OE_PARTNER_PACK="batimatech-ca"
openconstructionerp serve
# log line: "Active partner pack (auto-selected): batimatech-ca"
```

### Install commands for every reference pack

> The reference packs are not (yet) on PyPI as separate distributions —
> they live in the monorepo and are installed editable from a clone. To
> publish a pack to PyPI, follow the same workflow as the core
> (`pyproject.toml` → `python -m build` → trusted publishing).

From a fresh clone of the monorepo:

```bash
# Core (PyPI)
pip install openconstructionerp

# Packs (editable, from the clone)
pip install -e packs/aus-nzs
pip install -e packs/batimatech-ca
pip install -e packs/bimhessen-de
pip install -e packs/brazil-sinapi
pip install -e packs/doker-formwork
pip install -e packs/india-cpwd
pip install -e packs/renewables-epc
pip install -e packs/saudi-vision2030
pip install -e packs/uk-jct
pip install -e packs/us-rsmeans
```

After `pip install -e packs/<slug>` you can `pip uninstall
openconstructionerp-<slug>` to remove it.

### Install many — pick one as active

Multiple packs can be installed simultaneously. Only one is active at a
time. Precedence:

1. `OE_PARTNER_PACK=<slug>` env var (exact match against `manifest.slug`).
2. First pack alphabetically by slug (`aus-nzs` wins over `batimatech-ca`).
3. None — runs in vanilla OCERP mode.

To switch between installed packs without reinstalling, restart with a
different `OE_PARTNER_PACK` value.

---

## 5. The manifest in 60 seconds

Every pack's `manifest.py` builds one `PartnerPackManifest` instance and
assigns it to a module-level name (conventionally `MANIFEST`). The
`__init__.py` re-exports it.

```python
# src/openconstructionerp_acme/manifest.py
from __future__ import annotations
from app.core.partner_pack.manifest import PartnerBranding, PartnerPackManifest

MANIFEST = PartnerPackManifest(
    slug="acme",
    partner_name="Acme Construction",
    partner_url="https://acme.example",
    pack_version="0.1.0",
    description="Acme’s preset — French + EUR + DIN 276.",
    default_locale="fr",
    additional_locales={"fr": "locales/fr.json"},
    cwicr_regions=["cwicr-fr-paris"],
    default_currency="EUR",
    validation_rule_packs=["din_276"],
    branding=PartnerBranding(
        primary_color="#003366",
        accent_color="#FF6600",
        logo_path="logo.svg",
        favicon_path="favicon.ico",
    ),
    onboarding_script_path="onboarding.yaml",
    metadata={"country": "FR", "support_email": "support@acme.example"},
)
```

```python
# src/openconstructionerp_acme/__init__.py
from openconstructionerp_acme.manifest import MANIFEST

__all__ = ["MANIFEST"]
```

```toml
# pyproject.toml
[project.entry-points."openconstructionerp.partner_packs"]
acme = "openconstructionerp_acme:MANIFEST"

[tool.setuptools.package-data]
openconstructionerp_acme = [
    "logo.svg",
    "favicon.ico",
    "onboarding.yaml",
    "locales/*.json",
    "rule_packs/*.json",
]
```

For the full field list, types, defaults, and examples, see
[`MANIFEST_REFERENCE.md`](MANIFEST_REFERENCE.md).

---

## 6. The four runtime surfaces a pack exposes

A pack does not register routes. Instead, the **core** mounts five
read-only endpoints under `/api/v1/partner-pack/` that read from the
active pack:

| Endpoint | Purpose | Source attribute |
|---|---|---|
| `GET /api/v1/partner-pack/current` | Active manifest (public dict) | `PartnerPackManifest.to_public_dict()` |
| `GET /api/v1/partner-pack/installed` | All discovered packs + which one is active | `discover_packs()` + `get_active_pack()` |
| `GET /api/v1/partner-pack/logo` | Stream the partner logo | `branding.logo_path` |
| `GET /api/v1/partner-pack/favicon` | Stream the favicon (404 if not shipped) | `branding.favicon_path` |
| `GET /api/v1/partner-pack/onboarding-script` | Stream the onboarding YAML/JSON | `onboarding_script_path` |
| `GET /api/v1/partner-pack/locale/{code}` | Stream a pack-shipped locale JSON | `additional_locales[code]` |
| `GET /api/v1/partner-pack/by-slug/{slug}` | Public manifest of any installed pack | `get_pack_by_slug()` |

The frontend hook `usePartnerPack` calls `/current` on app boot. If a pack
is active, the hook returns the manifest and the `PartnerLogoBadge`
component renders the co-brand chip in the header and the dashboard banner.

---

## 7. Validation rule packs — what those JSON files actually are

Each pack ships zero or more JSON files under `rule_packs/`. **These are
not loaded as executable validation rules.** The core ships all rule
*classes*; the pack's JSON files are:

- **Documentation for the partner** — they describe which clauses the rule
  references, the source standard, the regulatory citation.
- **Reference data** the partner can quote in audits.
- **Future-compatible scaffold** — when v7.0 introduces declarative rule
  packs (Shape B), these JSON files can become runtime-loadable without
  changing the manifest schema.

The actual list of *rules enabled by default* is what you put in
`validation_rule_packs=[...]` on the manifest. Each entry there must match
a rule-pack slug that the core already implements. The current core ships
the following rule-pack slugs (from `backend/app/core/validation/rules/`):

- `boq_quality` — universal
- `din_276`, `gaeb_x83_x86`, `vob_2023`, `iso_19650_cde`, `bki_benchmarks` — DACH
- `nrm_1_cost_planning`, `nrm_2_detailed_measurement`, `jct_contract_clauses`, `bcis_benchmarks` — UK
- `masterformat_2018`, `aia_a201_2017`, `rsmeans_city_index` — US
- `cpwd`, `is_standards`, `dsr` — IN
- `nbr_12721`, `rps_pdf`, `sinapi` — BR
- `as_1684`, `nzs_3604`, `rawlinsons`, `as_4000` — AU/NZ
- `sbc`, `momrah`, `aramco_standards` — SA
- `nbc_2020`, `ccdc_2`, `csa_a23` — CA
- `iec_61400_wind`, `iec_61730_pv`, `mv_cable_specs`, `lcoe_templates`,
  `renewables_grid_compliance` — renewables
- `din_18218`, `formwork_cycle` — formwork

If a partner needs a rule that isn't in this list, file an issue against
the core. Packs cannot ship new rule classes.

---

## 8. Branding and AGPL co-brand obligation

OpenConstructionERP is AGPL-3.0. Section 5(d) of AGPL requires that
"appropriate legal notices" remain on each "interactive user interface."
For partner packs, this is satisfied by the **co-brand string**:

```
Powered by OpenConstructionERP · In partnership with <partner_name>
```

The string is computed by `PartnerPackManifest.effective_powered_by` and
displayed:

- In the header chip (xl+ viewport, centered, max-w-14rem).
- On the dashboard landing page banner.
- In the "About" modal.

A pack MAY override the wording via `branding.powered_by_text`, but the
override MUST still credit OpenConstructionERP somewhere in the string.
Removing the credit is an AGPL violation. The default value is the safe
choice and is recommended for all packs.

**Logo handling**

- The pack's `logo.svg` (or `.png`, `.webp`, `.jpg`) is streamed via
  `/api/v1/partner-pack/logo`. The frontend renders it in the co-brand
  chip alongside the OpenConstructionERP wordmark.
- The OpenConstructionERP wordmark MUST remain visible. Partners may not
  use CSS to hide it.

**Favicon**

- A pack may ship a `favicon.ico` (or any browser-supported favicon
  format). When present, the frontend swaps it on boot via the
  `<link rel="icon">` tag.

---

## 9. Onboarding script

A pack may ship a single `onboarding.yaml` (or `onboarding.json`) at the
path declared in `onboarding_script_path`. When set, the
`OnboardingWizard` component fetches it from
`/api/v1/partner-pack/onboarding-script` on first login and renders the
partner-specific steps instead of the default wizard.

The script schema is open. Conventionally a YAML list of step objects
with `id`, `title`, `body`, `cta`, `next` fields. See
`packs/batimatech-ca/src/openconstructionerp_batimatech_ca/onboarding.yaml`
for a worked example.

The script is rendered client-side. No business logic — only UI text and
flow.

---

## 10. Local development workflow

Develop your pack alongside the core:

```bash
# 1. Clone the monorepo
git clone https://github.com/DataDrivenConstruction/openconstructionerp
cd openconstructionerp

# 2. Editable install of the core + your pack
pip install -e .
pip install -e packs/your-pack

# 3. Activate it
export OE_PARTNER_PACK=your-pack   # PowerShell: $env:OE_PARTNER_PACK="your-pack"

# 4. Run the backend
openconstructionerp serve --reload
# Expect log line: "Active partner pack (auto-selected): your-pack v0.1.0"

# 5. Hit the API
curl http://localhost:8000/api/v1/partner-pack/current | jq
```

### Unit tests

The core ships `backend/tests/test_partner_pack_core.py` with 13 unit
tests covering manifest validation, discovery precedence, broken-pack
tolerance, and every router endpoint. Run them after every pack change:

```bash
cd backend
pytest tests/test_partner_pack_core.py -v
```

Add your own pack-specific assertions in `packs/<slug>/tests/` (mirror
the layout of `packs/batimatech-ca/tests/` once that exists).

---

## 11. Publishing a pack to PyPI

Packs are independent distributions. The core's PyPI trusted-publishing
workflow does NOT publish packs.

```bash
cd packs/your-pack
python -m build              # produces dist/openconstructionerp_your_pack-0.1.0-py3-none-any.whl
twine check dist/*
twine upload dist/*          # or set up trusted publishing per-pack
```

Use a `requires-python = ">=3.12"` pin and a `dependencies = [
"openconstructionerp>=5.6.0" ]` floor so the pack refuses to install
against a core version that predates the entry-point group.

---

## 12. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/api/v1/partner-pack/current` returns `{"active": false}` after install | Entry-point not registered | Verify `pyproject.toml` has the `[project.entry-points."openconstructionerp.partner_packs"]` table and that you reinstalled after editing it |
| Logs say `Partner pack 'X' failed to load: ...` | `MANIFEST` is malformed or `manifest.py` raises at import | Run `python -c "from openconstructionerp_x import MANIFEST; print(MANIFEST)"` to reproduce; fix the validation error |
| Wrong pack is active when multiple are installed | First-alphabetical-slug fallback | Set `OE_PARTNER_PACK=<slug>` explicitly |
| `/api/v1/partner-pack/logo` returns 404 | `logo_path` points at a missing file or the file is not in `package-data` | Ensure `pyproject.toml`'s `[tool.setuptools.package-data]` lists `"logo.svg"` (or your filename), then reinstall |
| Co-brand chip overlaps header buttons at 1366×768 | Pre-v5.6.0 layout bug | Upgrade core to ≥ v5.6.0 (header chip is `xl:flex` + `max-w-14rem`) |
| Pack works in test but not after `pip install` | Editable install picked up dev-only files | Add the missing globs to `[tool.setuptools.package-data]` and rebuild the wheel |

---

## 13. Where to look next

- **Field reference for every manifest property**:
  [`MANIFEST_REFERENCE.md`](MANIFEST_REFERENCE.md)
- **Why this design (Shape A vs Shape B, single- vs multi-tenant)**:
  [`docs/adr/2026-05-28-partner-pack-architecture.md`](../adr/2026-05-28-partner-pack-architecture.md)
- **Module SDK** (when you outgrow packs): `docs/module-development/quickstart.md`
- **Core source**: `backend/app/core/partner_pack/`
  - `manifest.py` — Pydantic schema
  - `discovery.py` — entry-point loader, env-var precedence, caching
  - `router.py` — five public endpoints
- **Reference packs**: `packs/<slug>/`

For partnership inquiries: <info@datadrivenconstruction.io>.
