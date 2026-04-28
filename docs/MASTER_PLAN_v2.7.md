# OpenConstructionERP — Master Plan v2.7+

**Дата сборки:** 2026-04-27
**Источник:** консолидация трёх документов
- `NextTasks 26042026.txt` (видение 2.x / 4.x)
- `OCE_EAC_Implementation_Spec_v2_International.md` (sections 1–10)
- `OCE_TECH_SPEC_GLOBAL.md` (modules 1–6)
плюс live-аудит репозитория и текущего бэклога задач (#135 – #264).

**Базовая ветка:** `main` @ `287d85a2` (v2.6.9 shipped).

---

## 1. Где мы сейчас (snapshot текущего релиза)

### 1.1. Что уже в продакшне на 2.6.9
- **CDE / Module 1 (TECH_SPEC)** — частично: проекты, документы, BOQ, RBAC, JWT-hardening, IDOR-фиксы (slice A), tenant isolation
- **BIM Diff Engine / Module 2** — done (#223)
- **Validation Engine / Module 3** — done в core: rule registry, IDS importer/SARIF exporter (#224), 13 встроенных rule sets, T08 DSL (#191), T13 NL Rule Builder (#196)
- **Classification / Module 4** — DIN 276 + NRM + MasterFormat + ÖNORM + DPGF + CPWD + 13 локальных стандартов: rules, не ML
- **QTO / Module 5** — BOQ редактор, multi-currency + VAT + compound positions (#249), CWICR matcher (#195), GAEB X83 import/export
- **AI Copilot / Module 6** — `ai_client.py` (httpx → vendor REST), embedded Qdrant fallback, semantic match endpoints
- **EAC v2 §1.1, §1.2, §1.3, §1.4, §1.5, §1.7, §3.x** — done (#199, #207, #221, #222)
- **EAC §2 Parameter Aliases** — done (#206)
- **Dashboards T00–T13** — все 14 фич done (#183–#196)
- **Takeoff** — Tier 1 + Tier 2 + значительная часть Tier 3 (PDF: page-jump, annotation persistence, color picker, "0 m²" suppression) live в v2.6.6→v2.6.9

### 1.2. Backlog status (текущие задачи)
| ID | Subject | Status |
|---|---|---|
| #178 | v2.4.0 slice B — Pagination + event emission (schedule, bim_hub) | **pending** (patch saved) |
| #220 | EAC §1.6 — Executor (rule-running engine) | **in_progress** (918 lines + tests, не зарелизено) |
| #260 | Takeoff Tier 3 deferred items | **in_progress** (5 шт. ниже) |

---

## 2. ⚠️ Горячие баги: чинить в v2.7.0

### 2.1. Backend test errors (обнаружено 2026-04-27)
Запуск `pytest tests/unit` показал **4 failed + 9 errors** на 2300 тестах:

1. **`tests/unit/eac/test_validator_aliases.py`** — 9 ERROR: `oe_schedule_schedule.project_id` FK references missing `oe_projects_project` table
   - **Причина:** `Base.metadata.create_all()` пытается создать `oe_schedule_schedule` (таблица из schedule-модуля) но `app.modules.projects.models` не импортирован в тесте
   - **Фикс:** добавить `import app.modules.projects.models  # noqa: F401` в conftest или test
2. **`tests/unit/test_demo_credentials.py`** — 4 FAILED:
   - `test_resolve_generates_when_unset`
   - `test_resolve_generates_unique_each_call`
   - `test_resolve_treats_empty_string_as_unset`
   - `test_main_module_has_no_hardcoded_demo_password`
   - **Причина:** требует диагностики — вероятно env-vars от conftest перетирают тестовый кейс

**Action:** одна задача "Backend test fixture cleanup", scope ≤ 1 час, ship в v2.7.0.

### 2.2. Pre-existing Alembic migration warning
`v260c_project_fx_rates_vat.py` raise на VPS: `RuntimeError: oe_projects_project not found` — задокументировано в `vps_deploy.md`. Сервис стартует через ORM `create_all()`, но миграция не идемпотентна. **Action:** идемпотентная замена (`op.create_table(..., if_not_exists=True)`).

### 2.3. Dependabot
5 moderate/low (vite/esbuild/uuid/glib/rand transitive) — отложены до v2.7.0 frontend dep refresh.

---

## 3. EAC v2 — что осталось из спеки `OCE_EAC_Implementation_Spec_v2`

| Раздел | Статус | Что осталось |
|---|---|---|
| §1 Унифицированный EAC-движок | 95% | §1.6 Executor (#220) — релиз. **Action:** ревью кода, smoke-tests, ship в v2.7.1 |
| §2 Глобальные алиасы | done (#206) | — |
| §3 Visual block editor | 80% | §3.4–§3.5 завершить UX flows, §3.6 edge cases |
| §4 **Импорт правил из Excel** | **0% — не начат** | Полная фича: парсер `.xlsx` → EAC rule JSON, mapping wizard, validation, XLS round-trip |
| §5 **Композиция классификаторов** | **0% — не начат** | Multi-system rule chains, partial DIN+NRM mapping, conflict resolution |
| §6 **4D-модуль на EAC-связках** | **0% — не начат** | Schedule-to-BIM linking, takt-zone, progress tracking, animation export |
| §7 Acceptance / testing / benchmarks | 70% | Performance budgets, accessibility (WCAG AA), полный i18n EN/DE/RU coverage |
| §8 Migration plan | done | — |
| §9 Implementation order | done | — |
| §10 Definition of Done | living doc | — |

---

## 4. TECH_SPEC_GLOBAL — что осталось из 6 модулей

| Module | Где недопокрыто |
|---|---|
| **1. CDE (ISO 19650)** | Naming convention validator (§1.6), full state machine (§1.4), suitability codes, BCF round-trip on documents |
| **2. BIM Diff** | Geometry signature compare (Шаг 4), Requirements impact analysis (Шаг 5), BCF export with viewpoints (§2.6) |
| **3. Model Validation** | Computed constraints — safe formula evaluator расширить, full IDS round-trip (export — есть, import — есть, но v1.0 strictness не доопределён) |
| **4. Classification** | **ML-based auto-classification (§4.7) — 0%**: embedding pipeline + Qdrant search + LLM resolver + confidence gate. Сейчас только rules |
| **5. QTO** | Locale-specific format adapters: AIA G702 (US), DQE/CCTP (FR), локальная смета (RU/СНГ). Progress billing flow (§5.9). Update propagation от BIM diff (§5.10) |
| **6. AI Copilot** | Document ingestion pipeline (§6.4) — extractors, chunking, embeddings; Hybrid retrieval (§6.6) — semantic + lexical; Auto-tasks (§6.8): issue auto-classification, thread summarization, requirements extraction, norms-based checklist |

---

## 5. NextTasks — стратегические "глубокие фишки"

### 5.1. Большие модули (sections 2.x)

| # | Идея | Зависимости | Статус |
|---|---|---|---|
| 2.2 | **EAC Triplet Framework** — sparse EAV + constraint registry, validation as SQL-join, real-time на triggers | EAC §1 base (есть) | Архитектурно готово, но `ifc/derived/manual/llm/cwicr` source-tag и revision-versioning ещё нет |
| 2.3 | **Geometric Quantity Engine** — B-Rep + OCC + 7 калькуляторов (Volume, Surface Area, Dimensions/OBB, Linear, Profile, Topology, Shadow) | DDC cad2data (есть), ADR-002 (OCC blocked → расширяем DDC) | **0% — критический gap.** Сейчас quantities берутся из source-properties, не пересчитываются |
| 2.4 | **Semantic Classification Engine** — rules + value partitioning + LLM fallback с confidence gate | Module 4, Qdrant | Rules — есть. LLM third-tier fallback — 0% |
| 2.5 | **Quality Gate Validation** — 4 уровня (Completeness/Consistency/Coverage/Compliance), batch+incremental+real-time, IDS bridge, BCF export | Module 3, IDS importer (есть) | 60% — IDS round-trip есть, BCF export issues — нет, real-time gate — нет |
| 2.6 | **Spatial Boundary Resolution** — second-level space boundaries, opening quantities, virtual IfcCovering | OCC | **0% — не начат** |
| 2.7 | **Visual Data Layer** — categorical/numeric/boolean palettes + viewport overlay + IFC bake | BIM viewer (есть) | Частично: theming — есть, palettes per attribute — нет, IFC bake — нет |
| 2.8 | **Cost Intelligence** — element descriptor → vector search → LLM resolver → confidence gate → quantity mapper → resource explosion → pricing engine → BoQ assembler | Modules 4+5+6, CWICR (есть) | 50% — pipeline есть, training feedback loop нет, explainability metadata нет |
| 2.9 | **Composable Workflow Automation** — Step ABC + YAML pipelines + n8n adapter + preset library | Celery (есть, #200) | 30% — async runner есть, YAML pipeline executor — нет, preset library — 1 шт |

### 5.2. Differentiators (sections 4.x — конкурентные преимущества)

| # | Идея | Усилие | Приоритет |
|---|---|---|---|
| 4.1 | Multi-Modal Element Matching (text+render+photo) | M-L | High |
| 4.2 | Federated Learning Loop (Flower + LoRA + Qwen3-4B) | XL | Medium-Long-term |
| 4.3 | Generative Specs (PDF → EAC triplets) | L | High — высокий ROI на тендерах |
| 4.4 | Reproducible Audit Trail (manifest.json + sigstore) | M | High — юридическая защита |
| 4.5 | Carbon-Aware Estimation (CWICR + GWP, Ökobaudat) | M | Medium — EU CSRD-ready |
| 4.6 | Real-Time Collaborative Wrangling (Yjs CRDT) | M | Yjs уже в deps, нужно доинтегрировать |
| 4.8 | Time-Aware Versioning (Git for BIM) | XL | Long-term |
| 4.9 | Plugin Marketplace (oce-plugin.toml + sigstore + git-backed registry) | L | После 2.x база стабилизируется |
| 4.13 | Ambient Validation (linter-style real-time) | M | High — UX рывок |
| 4.14 | Reasoning Receipts (extended thinking captured) | S | High — explainability |

---

## 6. Takeoff Tier 3 — оставшиеся пункты (#260)

| Item | Статус | Заметка |
|---|---|---|
| Annotation editing dialog (полное окно) | partially | Inline editing уже есть в Notes panel; полное dialog — нет |
| Side-panel placement of Link-to-BOQ | **done** | Picker уже встроен в side panel |
| PDF page thumbnails (full visual) | **substituted** | v2.6.8 — page-jump popover с measurement counts |
| Calibrate wizard mini-modal | **done** | v2.6.5 badge + v2.6.6 hint banner покрывают |
| Scale info in element popup | n/a | Нет element popup на canvas |
| Documents&AI tab walkthrough | not started | Нужен onboarding контент |
| `m` vs `M` consistency audit | not started | Стилистическая мелочь |

---

## 7. Версионная дорожная карта

### v2.7.0 — Stability & Test Fixtures (1–2 дня)
- Fix EAC validator test fixture (FK import order)
- Fix demo_credentials test failures
- Fix v260c migration idempotence
- Frontend dep refresh: vite/esbuild/uuid/glib/rand
- Documents&AI tab walkthrough copy
- Annotation editing dialog (full text edit)

### v2.7.1 — EAC §1.6 Executor release (1 день)
- Code review #220 (918 LOC)
- Smoke-tests against EAC golden fixtures
- Ship + docs

### v2.8.0 — EAC §4 Excel Rule Import (1 неделя)
- xlsx parser → EAC rule JSON
- Mapping wizard UI
- XLS round-trip (export rules to xlsx)
- 30+ tests

### v2.9.0 — Module 4 ML auto-classification (2 недели)
- Embedding pipeline (multilingual-e5-small уже в составе)
- Qdrant top-K → LLM resolver (Anthropic + OpenAI fallback)
- Confidence gate (auto / review / reject @ 0.85)
- Manual review queue UI
- Training example logging для federated learning loop

### v2.10.0 — Geometric Quantity Engine v1 (3 недели)
- DDC cad2data extensions: B-Rep export, OBB calculator, 7 калькуляторов
- Unit normalization contract (mm/m/inch enforcement)
- Per-calculator unit tests
- Replace source-property quantities в QTO с computed quantities

### v2.11.0 — Spatial Boundary Resolution (3 недели)
- Second-level space boundaries algorithm
- Opening quantities (host/opening/reveal)
- Virtual IfcCovering generation
- UI: per-room finish breakdown

### v3.0.0 — EAC §6 4D Module + Cost Intelligence training loop (4 недели)
- Schedule ↔ BIM linking via EAC
- Takt zones, progress tracking
- Cost training feedback loop (manual override → training example → reranker fine-tune)
- Reasoning receipts везде где AI-call

### v3.1.0+ — Differentiators wave
- Carbon-Aware Estimation (4.5)
- Reproducible Audit Trail (4.4)
- Generative Specs PDF→EAC (4.3)
- Real-Time Collab Yjs full (4.6)
- Plugin Marketplace (4.9)
- Multi-modal matching (4.1)

---

## 8. Принципы (cross-cutting, из NextTasks Часть 7)

Каждый PR проверяется по списку:

1. EAC — единственный путь к данным. Любой shortcut — баг.
2. Юнит-тесты на каждый калькулятор, на каждое правило.
3. Идемпотентность шагов pipeline (включая Alembic миграции — см. §2.2 выше).
4. Метрики единиц обязательны — каждое числовое значение несёт unit.
5. Reasoning > confidence. AI без объяснения — не результат.
6. Reproducibility > convenience.
7. Documentation as a deliverable.
8. Performance budgets — hard constraints.
9. AGPL compliance everywhere.

---

## 9. Что НЕ в этом плане (out of scope)

- Mobile native apps (PWA — да, native — нет)
- On-prem enterprise SSO (есть SAML/OIDC roadmap позже)
- Microsoft Project / Primavera P6 native parsers (через MPP/XER — есть в schedule module)
- Specific country plugins beyond what CWICR + 13 standards cover (через marketplace)
- Replacement of DDC cad2data with native IFC parsing — запрещено CLAUDE.md (используем DDC всегда)
