# Postgres-only simplification potential

Inventory of code that exists **only** because the app must also run on SQLite.
Quantifies what becomes deletable / simpler if SQLite is dropped, and the
ongoing dual-dialect maintenance tax that disappears.

Scale reference: `backend/app/` is ~205k Python LOC. The portability tax below
is small in raw LOC but high in *cognitive/maintenance* weight (it is the source
of the recurring "works on SQLite, breaks on PG" bug class).

---

## 1. `backend/app/database.py`

| Construct | Lines | If PG-only |
|-----------|-------|------------|
| `GUID` TypeDecorator | `database.py:98-131` (34 LOC) | Replace with native `postgresql.UUID(as_uuid=True)`. The whole class + its 803 `GUID()` call sites across 102 model files become a plain type alias. The tolerant `process_result_value` fallback (`:120-131`, swallows non-UUID strings) only exists because SQLite stores UUIDs as untyped `String(36)` and some columns abuse it as free text. On native PG UUID those rows would have to be real UUIDs or move to `Text` columns — the silent-coercion hack goes away. |
| `_tolerant_json_loads` | `database.py:165-180` (16 LOC) + wired at `:191` | Pure SQLite workaround. SQLite JSON columns are untyped TEXT, so legacy seeds persisted bare scalars (`activity = construction` instead of `["construction"]`) that crashed `json.loads` at ORM-load time. On PG with real JSONB the column is validated at write time, so a bare scalar can never be stored. Deletable; revert `json_deserializer` to the SQLAlchemy default. |
| SQLite PRAGMA connect listener | `database.py:198-206` (WAL / busy_timeout / foreign_keys=ON) | Deletable. PG enforces FKs natively and has MVCC (no WAL pragma, no busy_timeout). |
| `_is_sqlite` helper + pool branch | `database.py:161-162`, `:194-208`, `:217-226` | Collapses. The `connect_args={"check_same_thread": False}` branch and the `if not _is_sqlite` guard around `pool_pre_ping` / `pool_recycle` both vanish — PG always wants pre-ping + recycle, so it becomes unconditional. |

**database.py removable/simplified: ~70-90 LOC**, plus ripple across **803 `GUID()` call sites / 102 model files** (mechanical type swap, not deletion, but removes a whole abstraction layer).

---

## 2. `backend/app/core/pg_optimizations.py` — 168 LOC

The `@compiles(JSON,'postgresql') -> 'JSONB'` trick (`:53-64`) exists **only**
because models declare the generic SQLAlchemy `JSON` type for SQLite portability.
If PG-only:

- Models can declare `JSONB` directly. The two `@compiles` hooks (`:53-64`) and the entire "rewrite DDL at compile time" comment block (`:1-27`) are deletable (~40 LOC of mechanism + docs).
- The GIN-index logic (`:127-134`) currently has to runtime-check `isinstance(col.type, JSON)` and tag `postgresql_using='gin'`; with native JSONB columns the GIN index can be declared inline on the model (`Index(..., postgresql_using='gin')`) — the inference machinery (`_desired_indexes`, `_existing_single_col_left`, `_ensure_performance_indexes`, the dialect skip at `:154`) can largely move into normal model/migration declarations.
- The whole module is a side-effect import guarded by try/except in `database.py:235-244` precisely because it is fragile dual-dialect glue.

**pg_optimizations.py: ~168 LOC of which the JSON->JSONB compile trick (~40 LOC) is purely SQLite-portability tax**; the rest could be re-expressed as ordinary declarative indexes.

---

## 3. `backend/app/core/db_types.py` — 143 LOC (MoneyType / SafeDate)

Both types are explicit dual-dialect shims: **PG -> `NUMERIC`/`DATE`, SQLite -> `VARCHAR`**
(see the module docstring `:14-19`: "the existing SQLite dev databases store money
and dates as strings ... swapping column types in place would require a destructive
migration"). The `load_dialect_impl` / `process_bind_param` branches (`:68-84`,
`:110-135`) all branch on `dialect.name == "postgresql"`.

If PG-only: both collapse to thin `Numeric`/`Date` wrappers (keep only the Python-side
Decimal/date normalisation, drop every SQLite string branch). Used in 6 files / 57
call sites (finance, variations, moc, changeorders, procurement) — the SQLite-string
storage path for money is **dead weight on PG** and a correctness footgun (string money
sorts/aggregates lexically on SQLite).

**db_types.py: ~50-60 LOC of dialect branching removable; semantics get strictly safer.**

---

## 4. `backend/app/core/sql_json.py` — 80 LOC — DELETABLE IN FULL

`json_path_text(col, '$.a.b')` exists solely to compile to `json_extract` on SQLite
vs `(col::jsonb #>> '{a,b}')` on PG (`:63-79`). If PG-only the call sites (20
occurrences in 5 files: bim_hub/repository, costs/router, costs/repository, main)
use the native JSONB operator directly. **Entire 80-LOC module deletable** plus its
210-LOC test (`tests/unit/test_sql_json.py`).

---

## 5. `backend/app/middleware/sqlite_retry.py` — 79 LOC — DELETABLE IN FULL

`SQLiteLockRetryMiddleware` retries on `database is locked` (`:38-78`). The docstring
itself says "Only engaged when the underlying engine dialect is sqlite — on PostgreSQL
this is a no-op (MVCC, no file lock)" (`:15-16`). On PG it does literally nothing.
**Entire module + its registration in `main.py` + 118-LOC test deletable.**

---

## 6. Migrations — the dual-dialect tax (the biggest line-count win)

Out of **198 migration files** in `backend/alembic/versions/`:

| Pattern | Files | Notes |
|---------|-------|-------|
| `batch_alter_table` | **52 files, 144 occurrences** | `batch_alter_table` is the SQLite-only "rebuild the table to ALTER it" pattern (SQLite can't `ALTER COLUMN`/`DROP COLUMN`/add constraints in place). On PG, every one of these becomes a one-line `op.alter_column` / `op.add_column` / `op.create_unique_constraint`. |
| `bind.dialect.name` branches | **54 files, 60 occurrences** | Explicit `if dialect == 'postgresql' / elif 'sqlite'` forks. |
| references `sqlite` | 127 files | |
| branch on **both** dialects | **94 files** | the migrations carrying real dual-dialect cost |
| `"0" if is_sqlite else "false"` boolean-default branches | **44 files, 72 occurrences** | SQLite has no boolean type so server_defaults must be `'0'/'1'`; PG wants `'false'/'true'`. Each becomes a single literal. |

Representative cost (`v3123_boq_fk_indexes.py:106-162`): a 57-line up/down pair that
forks into PG `CREATE INDEX CONCURRENTLY` + manual COMMIT/BEGIN vs SQLite plain
`CREATE INDEX` — on PG-only this is ~15 lines. `v3030_module4_extras.py:68-69` picks
`String(36)` vs `postgresql.UUID` per dialect; that disappears with native UUID.

**Dual-dialect migration tax: ~150 dialect/batch branch sites across 94 files.**
Going forward, *every new migration* avoids the `batch_alter_table` ceremony and the
boolean/UUID/default forks — this is the largest ongoing maintenance saving.

---

## 7. The "works on SQLite, breaks on PG" bug class — and its reverse

The bugs hunted this session all come from the lowest-common-denominator design:

- **JSONB containment vs LIKE-scan** forks in runtime code: `tasks/service.py:50-66`, `bim_hub/service.py:180-185`, `boq/events.py:87-93`, `costs/repository.py:44-48`. On SQLite these do a `col.like('%"<id>"%')` text scan; on PG a native `@>` / `#>>`. PG-only deletes the SQLite arm of each fork.
- `json_extract` (SQLite) vs `#>>` (PG) — 22 occurrences, centralised in `sql_json.py` (deletable per §4).
- `.like` vs `.ilike`: **95 `.like(` vs 47 `.ilike(`** call sites. SQLite `LIKE` is case-insensitive by default; PG `LIKE` is case-sensitive. Every `.like()` written/tested on SQLite is a latent case-sensitivity bug on PG.

**Reverse risk is real and PG-only KILLS it.** Today, any PG-only code path (the
`if dialect == 'postgresql'` arms in §6/§7, the full-text search in
`file_search/service.py:337-361` using `to_tsvector`/`plainto_tsquery`) is **never
exercised by the test suite**, which runs on in-memory SQLite (`tests/conftest.py:84-86`).
So PG-specific code ships untested. PG-only means **one code path, tested by one
backend** — both directions of the dual-dialect bug class are eliminated.

Caveat (cost side): the test suite (38 test files reference `sqlite`, conftest uses
`sqlite+aiosqlite:///:memory:`) would have to move to a real Postgres in CI
(testcontainers / service container). That is the main one-time cost of dropping SQLite.

---

## 8. Native PG features currently unused (lowest-common-denominator)

Confirmed by grep across `app/` + `alembic/`:

- **`gen_random_uuid()` / `uuid_generate_v4()`: 0 uses.** PKs are generated Python-side via `default=uuid.uuid4` (`database.py:146`) because SQLite has no UUID generator. Could move to DB-side defaults.
- **Native `UUID` columns: 0** (`postgresql.UUID(as_uuid=...)` appears in 0 model files; everything is `GUID()` -> `String(36)`).
- **`timestamptz` semantics: unused.** 241 columns declare `DateTime(timezone=True)` but on SQLite tz is a no-op (stored naive). Memory note confirms "0 aware cols" in practice. Real `timestamptz` (and tz-correct comparisons/`AT TIME ZONE`) only becomes meaningful on PG.
- **ARRAY columns: 0** — string/JSON arrays are stored as JSON text instead (the cause of the JSONB-vs-LIKE forks in §7).
- **Full-text search:** implemented PG-side (`file_search/service.py`) but only as one arm of a dialect fork; the SQLite arm is the fallback that gets tested.
- **Partial / expression indexes, GIN-on-JSONB:** GIN exists but is bolted on via the `pg_optimizations.py` runtime-inference hack (§2) rather than declared natively; partial/expression indexes are not used at all.

---

## Bottom line — quantified removal

| Bucket | Removable / simplified |
|--------|------------------------|
| Fully deletable modules | `sql_json.py` (80) + `sqlite_retry.py` (79) = **159 LOC** + their tests (210 + 118 = 328 LOC) |
| Simplified in place | `database.py` ~70-90 LOC; `db_types.py` ~50-60 LOC; `pg_optimizations.py` ~40+ LOC of JSON->JSONB trick |
| Migrations | ~150 dialect/`batch_alter_table` branch sites across 94 of 198 files (mostly converts to simpler one-liners, not all deletable) |
| Runtime dialect forks | 7 service/repo files lose their SQLite arm (`tasks`, `bim_hub`, `boq/events`, `costs` x2, `property_dev`, `file_search`) |
| Mechanical ripple | 803 `GUID()` call sites / 102 files -> native UUID; 95 `.like(` audited for case-sensitivity |
| Ongoing tax eliminated | every future migration drops batch/boolean/UUID forks; one tested code path; whole "works-on-SQLite/breaks-on-PG" (and the reverse "PG-only untested") bug class gone |

**Net deletable LOC: ~400-500 (source) + ~650 (shim tests) ≈ 1,000+ LOC**, plus a
large reduction in per-migration ceremony and the elimination of an entire recurring
bug class. The chief offsetting cost is moving the test suite from in-memory SQLite
onto a real Postgres in CI.
