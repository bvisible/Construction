# 08 - Offline Field PWA (daily diary, photos, punchlist, inspections)

Status: design
Owner: DataDrivenConstruction (info@datadrivenconstruction.io)
Module key: `field_diary` (extends the existing field module; no new top-level module)
Depends on: none (all substrate already exists in main)

## 1. Goal and what already exists

The feature is a mobile, offline-first field surface that lets a site worker
capture daily diary entries, photos, punchlist items and inspections on a phone
or tablet, keep working when the signal drops, and have everything sync when the
device is back online. The whole point of the feature is connective tissue: a
single capture flow on `/field` that writes into four existing modules and back
into the desktop product, not a fifth parallel data store.

A large part of this is already built. The honest inventory below is what we
verified in the code, and it changes the shape of the work from "build a field
app" to "complete and connect the field app that is half-shipped".

### 1.1 Backend that exists today

| Piece | File | State |
|-------|------|-------|
| Field module + PIN-gated magic-link auth | `backend/app/modules/field_diary/` | Working. `request-magic-link` -> `consume` -> session-bearer, all tokens stored as `sha256` hex. |
| `FieldSession`, `FieldMagicLink`, `FieldModuleGrant` tables | `backend/app/modules/field_diary/models.py` | Working. Migration `backend/alembic/versions/v3133_field_diary_init.py`. |
| `RequirePinPlusMagicLink` + `_require_field_module_grant` deps | `backend/app/modules/field_diary/router.py:78,120` | Working. Session is pinned to one `(user, project, module_key)`; `project_id` is read from the session, not the URL, so there is no IDOR window. |
| Diary FSM (draft -> submitted -> approved) | `backend/app/modules/field_diary/service.py:219` | Working. `module_key` column on the grant table is deliberately free-form so new field modules reuse the same grant table with no schema change (`models.py:254`). |
| New field roles | `backend/app/core/permissions.py:41` | `FIELD_WORKER` (-2), `SITE_FOREMAN` (-1), `SITE_INSPECTOR` (0) already in the `Role` enum and `ROLE_HIERARCHY`. |
| Daily Diary module | `backend/app/modules/daily_diary/` | Full diary, photos, weather, sign/archive, PDF, cross-module events (`events.py`). |
| Punchlist module | `backend/app/modules/punchlist/` | CRUD, status FSM, photo upload with magic-byte gate and Documents cross-link (`router.py:346`), geo pin columns `geo_lat`/`geo_lon` (`models.py:75`). |
| Inspections module | `backend/app/modules/inspections/` | CRUD, complete, and two cross-module bridges already exist: `create-defect` (inspection -> punchlist, `router.py:213`) and `create-ncr` (inspection -> NCR, `router.py:324`). |

### 1.2 Frontend that exists today

| Piece | File | State |
|-------|------|-------|
| `/field` route, lazy-loaded chunk | `frontend/src/app/App.tsx:224,702` | Routed. |
| `FieldShellPage` bottom-nav shell | `frontend/src/features/field/FieldShellPage.tsx` | Skeleton. Four tabs render placeholder text. No auth, no data, no capture. |
| IndexedDB offline store (cache + mutation queue) | `frontend/src/shared/lib/offlineStore.ts` | Working primitives: `cacheResponse`, `getCachedResponse`, `queueMutation`, `getQueuedMutations`, `removeMutation`. DB `oe_offline`, version 1, two stores `apiCache` + `mutationQueue`. |
| API client offline behaviour | `frontend/src/shared/lib/api.ts:397` | When `navigator.onLine === false`, GET falls back to `getCachedResponse`, and POST/PUT/PATCH/DELETE are queued via `queueMutation` and a "Saved offline" toast is shown. |
| Mutation replay on reconnect | `frontend/src/shared/hooks/useOnlineStatus.ts:44` | `replayMutations` drains the queue FIFO; treats `res.ok || 409` as success. |
| Offline banner + offline fallback | `frontend/src/shared/ui/OfflineBanner.tsx`, `OfflineFallback.tsx` | Working. `markLastSync()` helper. |
| PWA (workbox) | `frontend/vite.config.ts:123` | Installable, app-shell precache, three runtime cache lanes (`oce-static-assets`, `oce-i18n-locales`, `oce-api` NetworkFirst 30s, GET-only). |

### 1.3 The two findings that shape the design

There are two facts in the current code that are easy to miss and that the
design has to address head-on.

First, the offline mutation replay is wired into the desktop shell only.
`useOfflineSync()` is called from `frontend/src/app/layout/AppLayout.tsx:63`.
`FieldShellPage` deliberately does not mount `AppLayout` (it renders its own
bottom-nav shell with no sidebar). So today, a field worker who queues a write
offline has nothing on `/field` that drains the queue when they reconnect. This
is the single most important gap to close.

Second, the production service worker at `frontend/public/sw.js` is a
deliberate self-destruct stub, not the workbox SW. It was shipped on
2026-05-25 to evict a stale workbox bundle from user browsers; it deletes every
cache and unregisters itself. The workbox config in `vite.config.ts` is real and
emits a SW at build time, but the file checked into `public/` shadows it for the
"unregister everything" purpose. The design must verify which SW actually serves
on `:8000` and not assume the workbox runtime caches are live. The field flow is
built so that it does not depend on the workbox `oce-api` cache lane: correctness
comes from the IndexedDB queue in `offlineStore.ts`, which is independent of the
service worker. The SW, when active, is an accelerator for the app shell, not the
source of truth for field data.

The feature therefore reuses the `field_diary` module as its backend home (the
`module_key` column was built generic precisely for this), extends it with photo,
punchlist and inspection capture endpoints, adds one connective sync endpoint,
and replaces the `FieldShellPage` skeleton with a working offline capture UI that
mounts its own sync loop.

## 2. Data model

The design adds exactly one new table and reuses everything else. The
`field_diary` module already owns the auth and grant tables and a diary entry
table; the capture surface routes photos, punchlist and inspections into the
already-existing tables in those three modules, so no new diary, photo,
punchlist or inspection tables are created.

Convention reminders verified in `backend/app/database.py:139`: `Base` provides
`id` (UUID PK via `GUID`), `created_at`, `updated_at`. Dates and times that are
business dates are `String` ISO columns (see `daily_diary` `diary_date`,
`field_diary` `entry_date`). Money is `String`/`Decimal` (see punchlist
`rework_cost` at `models.py:66`). Internal precise timestamps use
`AwareDateTime()` or `DateTime(timezone=True)`.

### 2.1 New table: `oe_field_sync_op`

This is the server-side idempotency and audit ledger for offline writes. The
frontend assigns every queued mutation a client-generated UUID (`client_op_id`)
before it goes into IndexedDB. On replay, the field sync endpoint records the op
keyed by `(session_id, client_op_id)`. A duplicate replay (the classic
"reconnect fired twice, two POSTs for one tap" case) is detected here and the
original result is returned instead of creating a second row downstream. This is
what makes the queue safe to drain more than once.

| Column | Type | Notes |
|--------|------|-------|
| `id` | `GUID` PK | from `Base` |
| `session_id` | `GUID`, FK `oe_field_diary_session.id` ON DELETE CASCADE, indexed | scopes the op to one field session, so signing out and clearing the queue cascades cleanly |
| `client_op_id` | `String(64)`, not null | client-generated UUID; the dedup key |
| `project_id` | `GUID`, FK `oe_projects_project.id` ON DELETE CASCADE, indexed | denormalised for fast project-scoped audit |
| `target_module` | `String(32)`, not null | one of `field_diary`, `daily_diary`, `punchlist`, `inspections` |
| `target_kind` | `String(40)`, not null | e.g. `diary_entry`, `diary_photo`, `punch_item`, `punch_photo`, `inspection`, `inspection_complete` |
| `verb` | `String(8)`, not null | `create`, `update`, `transition`, `complete` |
| `status` | `String(16)`, not null, default `applied` | `applied`, `conflict`, `rejected` |
| `result_id` | `GUID`, nullable | the id of the row created/updated downstream, so a replay returns the same id |
| `http_status` | `Integer`, not null, default 0 | the status the op resolved to, surfaced to the client |
| `captured_at` | `String(40)`, nullable | client device capture time, ISO string, mirrors the diary `entry_date` convention to avoid a UTC midnight trap |
| `error_detail` | `Text`, nullable | non-null only when `status` is `conflict`/`rejected`, drives the client "tap to review" toast |
| `metadata_` | `JSON`, not null, default `{}` | column name `metadata`, carries the `field_capture` payload (lat/lon/accuracy/device_hint) |

Unique constraint: `uq_oe_field_sync_op_session_client` on `(session_id,
client_op_id)`. Index: `ix_oe_field_sync_op_project_module` on `(project_id,
target_module)` for audit reads.

This table lives in the `field_diary` module
(`backend/app/modules/field_diary/models.py`) next to the existing field tables,
because it is part of the field session lifecycle, not a property of the four
target modules.

### 2.2 Columns added to existing tables (additive, nullable)

To make the cross-module capture honest rather than dumping everything in
`metadata`, the design promotes the geo capture and the source link to first
class on the two record types that do not already carry them. The design doc at
`docs/architecture/FIELD_WORKER_MOBILE_DESIGN.md` section 2.5 explicitly deferred
this; this is the deferred promotion.

Punchlist already has `geo_lat`/`geo_lon` (`models.py:75`), so it needs no geo
columns. Daily Diary `DiaryPhoto` already has `lat`/`lng` (`models.py:230`). The
remaining gaps:

| Table | New column | Type | Why |
|-------|-----------|------|-----|
| `oe_inspections_inspection` | `geo_lat` | `Float`, nullable | capture-time GPS so an inspection raised in the field renders on the Geo Hub map, mirrors punchlist `geo_lat` exactly |
| `oe_inspections_inspection` | `geo_lon` | `Float`, nullable | same |
| `oe_field_diary_entry` | `field_source` | `String(16)`, nullable | `pwa` when the entry originated from the offline field shell, null for desktop; lets reporting distinguish field-captured vs office-entered without parsing `metadata` |

Everything else the field flow needs already has a home: the `field_capture`
payload (`lat`, `lon`, `accuracy_m`, `device_hint`, `captured_at`) lands in the
existing `metadata_` JSON column on whichever record is created, exactly as the
existing design doc specified, and additionally in `oe_field_sync_op.metadata_`
for the ledger. Punchlist already cross-links its photos into the Documents hub
(`punchlist/router.py:412`); the field photo path reuses that code unchanged.

### 2.3 Alembic migration outline

One migration, chained onto the current head. The current head at design time is
`v41_smart_views_share` (`down_revision = v41_clash_ai_triage`); the field tables
came in at `v3133_field_diary_init`. The new migration sets `down_revision` to
the live head at implementation time (verify with `alembic heads` first; the repo
has a known gotcha that the VPS resolves a different relative DB, see
`MEMORY.md`).

```
revision = "v42_field_pwa_sync"
down_revision = "<live head at build time>"   # verify, do not hardcode v41

def upgrade():
    # 1. New ledger table
    op.create_table(
        "oe_field_sync_op",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("session_id", GUID(),
                  sa.ForeignKey("oe_field_diary_session.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("client_op_id", sa.String(64), nullable=False),
        sa.Column("project_id", GUID(),
                  sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("target_module", sa.String(32), nullable=False),
        sa.Column("target_kind", sa.String(40), nullable=False),
        sa.Column("verb", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="applied"),
        sa.Column("result_id", GUID(), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("captured_at", sa.String(40), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", AwareDateTime(), nullable=False),
        sa.Column("updated_at", AwareDateTime(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_oe_field_sync_op_session_client",
        "oe_field_sync_op", ["session_id", "client_op_id"])
    op.create_index(
        "ix_oe_field_sync_op_project_module",
        "oe_field_sync_op", ["project_id", "target_module"])

    # 2. Additive nullable columns on existing tables (no backfill needed)
    op.add_column("oe_inspections_inspection", sa.Column("geo_lat", sa.Float(), nullable=True))
    op.add_column("oe_inspections_inspection", sa.Column("geo_lon", sa.Float(), nullable=True))
    op.add_column("oe_field_diary_entry", sa.Column("field_source", sa.String(16), nullable=True))

def downgrade():
    op.drop_column("oe_field_diary_entry", "field_source")
    op.drop_column("oe_inspections_inspection", "geo_lon")
    op.drop_column("oe_inspections_inspection", "geo_lat")
    op.drop_index("ix_oe_field_sync_op_project_module", "oe_field_sync_op")
    op.drop_constraint("uq_oe_field_sync_op_session_client", "oe_field_sync_op", type_="unique")
    op.drop_table("oe_field_sync_op")
```

Use `app.database.GUID` and `app.core.db_types.AwareDateTime` in the migration,
matching `v3133_field_diary_init`. New model tables that the fresh-install SQLite
`create_all` path must see also need a pre-`create_all` import in
`backend/app/main.py` (this codebase's recurring gotcha, recorded in
`MEMORY.md` under the match-pipeline note); add `oe_field_sync_op` to that import
list.

## 3. API

All endpoints extend the existing field router mounted at `/api/v1/field-diary`
(`backend/app/core/module_loader.py:207` derives the kebab prefix from the
manifest name `oe_field_diary`). Every capture endpoint is gated by the existing
`_require_field_module_grant` dependency, which already enforces PIN plus
magic-link session plus the per-project module grant, and which reads
`project_id` from the session rather than the URL. The capture endpoints add
nothing to that security model; they extend the surface it protects.

Admin grant management endpoints (`POST /grants/`, `DELETE /grants/{id}/`)
already exist and stay gated by `RequireRole("admin")` plus the standard
internal RBAC. Foremen provision and revoke field workers through these.

### 3.1 New capture endpoints (field session auth)

All requests carry `Authorization: Bearer <session-token>` and `X-Field-PIN`.
All bodies carry the field capture envelope and the `client_op_id` for
idempotency.

| Method | Path | Request | Response | Notes |
|--------|------|---------|----------|-------|
| GET | `/api/v1/field-diary/today/` | none | `FieldTodayResponse` | single round-trip for the Today screen: today's diary header for the session project, open punchlist count + top items, open inspection count, latest weather. Project is the session project. Cached client-side as the offline seed. |
| POST | `/api/v1/field-diary/capture/photo/` | multipart `file` + form fields `target` (`diary`/`punch`), `note`, `lat`, `lon`, `accuracy_m`, `captured_at`, `client_op_id`, optional `punch_item_id` | `FieldCaptureResponse` | magic-byte gated via `app.core.file_signature.require` against `ALLOWED_PHOTO_TYPES`, exactly as punchlist and the diary EXIF endpoint do today |
| POST | `/api/v1/field-diary/capture/punch/` | `FieldPunchCreate` (title, description, priority, trade, lat, lon, captured_at, client_op_id) | `FieldCaptureResponse` | creates an `oe_punchlist_item` row scoped to the session project, status `open` |
| POST | `/api/v1/field-diary/capture/inspection/` | `FieldInspectionCreate` (inspection_type, title, location, checklist_data, lat, lon, captured_at, client_op_id) | `FieldCaptureResponse` | creates an `oe_inspections_inspection` row scoped to the session project, status `scheduled` |
| POST | `/api/v1/field-diary/sync/batch/` | `FieldSyncBatch` (list of `FieldSyncOp`) | `FieldSyncResult` (per-op outcome) | optional bulk drain: the client may replay one op at a time against the endpoints above, or batch up to 50 ops here; either path goes through the same idempotency ledger |
| GET | `/api/v1/field-diary/sync/ops/` | query `since` (ISO) | `list[FieldSyncOpResponse]` | the worker's own op history for "what synced, what conflicted"; scoped to the session |

The existing diary endpoints (`/entries/`, `/entries/{id}/`,
`/entries/{id}/submit/`, `/entries/{id}/activities/`,
`/entries/{id}/attachments/`) are unchanged and are part of the same offline
flow. The field shell already has everything it needs to write a diary entry; the
capture endpoints add photos-to-diary, punch and inspection.

### 3.2 Request/response shapes (Pydantic, in `field_diary/schemas.py`)

```python
class FieldCapture(BaseModel):
    # The capture envelope embedded in every field write.
    client_op_id: str = Field(..., min_length=8, max_length=64)
    captured_at: str = Field(..., description="ISO 8601 device time")
    lat: float | None = None
    lon: float | None = None
    accuracy_m: float | None = Field(default=None, ge=0)
    device_hint: str | None = Field(default=None, max_length=120)

class FieldPunchCreate(FieldCapture):
    title: str = Field(..., max_length=255)
    description: str = Field(default="", max_length=10_000)
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    trade: str | None = Field(default=None, max_length=100)

class FieldInspectionCreate(FieldCapture):
    inspection_type: str = Field(..., max_length=50)
    title: str = Field(..., max_length=500)
    location: str | None = Field(default=None, max_length=500)
    checklist_data: list[dict[str, Any]] = Field(default_factory=list)

class FieldCaptureResponse(BaseModel):
    client_op_id: str
    status: Literal["applied", "conflict", "rejected"]
    target_module: str
    target_kind: str
    result_id: uuid.UUID | None = None   # downstream row id; stable on replay
    http_status: int

class FieldTodayResponse(BaseModel):
    project_id: uuid.UUID
    diary: DiaryEntryResponse | None
    weather: dict[str, Any] | None
    open_punch_count: int
    top_punch: list[dict[str, Any]]      # id, title, priority, status
    open_inspection_count: int
    server_time: str                     # ISO, so the client can reconcile clock skew
```

`FieldSyncOp` mirrors the IndexedDB `QueuedMutation` plus the `client_op_id`;
`FieldSyncBatch` is a list capped at 50; `FieldSyncResult` is a list of
`FieldCaptureResponse`.

### 3.3 RBAC and project scoping

There are two enforcement layers, and the field surface uses the dedicated one,
not the standard `RequirePermission` stack. This is by design and already true
of the diary endpoints.

1. Session + PIN: `RequirePinPlusMagicLink` validates the bearer session token
   and the `X-Field-PIN` header (`field_diary/router.py:78`).
2. Module grant: `_require_field_module_grant` confirms a live non-revoked row in
   `oe_field_module_grant` for `(session.user_id, session.project_id,
   session.module_key)` (`router.py:120`, `service.py:149`). The foreman flips
   this on or off in one operation, which is the kill switch.

Project scoping is structural, not a filter that can be forgotten: the session
is pinned to exactly one `project_id`, the capture endpoints read it from the
session, and any body that names a different `project_id` is rejected (the diary
endpoints already do this, `router.py:269`). Cross-project access is therefore
impossible to express, not merely guarded.

IDOR convention: every mismatch between a URL UUID and the session scope returns
404, not 403, matching `field_diary/router.py:289` and the buyer-portal pattern
the field module was modelled on. A `punch_item_id` in a photo capture that
belongs to another project resolves to 404.

The new field roles already exist in the registry
(`backend/app/core/permissions.py:41`). The field surface does not depend on the
JWT role at all (it runs on the field session, not a JWT), so no role-permission
registration changes are required for the capture endpoints. If a future phase
exposes field capture to internal JWT users (a PM testing on their phone), the
permission set listed in the existing design doc section 4.1 is registered then.

## 4. Service logic and module connections

The connective tissue is the entire reason the feature exists, so this section is
concrete about which existing function each capture path calls.

### 4.1 Core flow

```
Field worker on /field (PWA, possibly offline)
        |
        v
Capture (photo / punch / inspection / diary entry)
        |
   client assigns client_op_id, captures GPS + device time
        |
   online?  --yes-->  POST to the matching /field-diary/capture/* endpoint
        |                     |
        no                    v
        |              FieldSyncService.apply_op()
        v                     |
  offlineStore.queueMutation  |  idempotency check on (session_id, client_op_id)
  (IndexedDB, oe_offline)     |   - seen + applied  -> return prior result_id
        |                     |   - new             -> call the target module service
   "Saved offline" toast      |                        record oe_field_sync_op row
        |                     v
   reconnect (online event)   downstream row created in the TARGET module's table
        |                     (punchlist / inspections / daily_diary / field_diary)
        v                     |
  useFieldSync drains queue   v
  FIFO, max 5 parallel        events published (punchlist.item.created, etc.)
        |                     |
        v                     v
  same /field-diary endpoints  desktop product sees the row immediately:
  -> FieldSyncService          Punch List page, Inspections page, Daily Diary,
                               Geo Hub map (via geo_lat/geo_lon), Documents hub
                               (via the existing punch-photo cross-link)
```

### 4.2 New `FieldSyncService` (in `field_diary/service.py`)

This service is the hub. It does not own any record type; it dispatches into the
four module services and records the ledger. It is constructed with the request
session, like every other service in the codebase.

`apply_op(session, op, target_kind)`:

1. Look up `oe_field_sync_op` by `(session.id, op.client_op_id)`. If found and
   `status == applied`, return the stored `result_id` and `http_status` without
   touching anything else. This is the dedup that makes replay safe.
2. Otherwise dispatch by `target_kind` into the existing module service,
   forcing `project_id = session.project_id`:
   - `punch_item` -> construct `PunchItem` via the punchlist module
     (`app.modules.punchlist.models.PunchItem` / `PunchListService.create_item`),
     set `geo_lat`/`geo_lon` from the capture, `created_by = session.user_id`,
     status `open`. This is the same model the inspections `create-defect` bridge
     already constructs (`inspections/router.py:274`).
   - `inspection` -> construct `QualityInspection` via
     `InspectionService.create_inspection`, set the new `geo_lat`/`geo_lon`,
     `created_by = session.user_id`, status `scheduled`.
   - `diary_photo` / `punch_photo` -> reuse the photo persistence already written
     in `punchlist/router.py:346` (magic-byte gate, server-derived filename,
     write to `uploads/.../photos`, then the Documents hub cross-link at
     `router.py:412`). For a diary photo, register an `oe_field_diary_attachment`
     row via `FieldDiaryService.register_attachment` (already exists,
     `service.py:411`), which is the diary's own attachment path.
   - `diary_entry` / `diary_activity` -> the existing
     `FieldDiaryService.create_diary_entry` / `append_activity`.
3. Record an `oe_field_sync_op` row with the downstream `result_id`, the resolved
   `http_status`, and the capture envelope in `metadata_`.
4. On a downstream `HTTPException` with 409, store `status = conflict` and the
   detail, return it to the client so the queue can surface the "tap to review"
   path rather than silently dropping. On a 4xx that is not 409 (validation),
   store `status = rejected`; the client stops retrying that op.

### 4.3 How the four named modules are linked

This is the explicit module-to-module wiring, all of it through existing service
functions and existing cross-links.

- field_diary <-> daily_diary: the field diary entry is the worker-facing,
  per-author daily record (`oe_field_diary_entry`, unique on `(project, author,
  date)`); the office Daily Diary (`oe_daily_diary_diary`, unique on `(project,
  date)`) is the consolidated, signable, legally significant record. The field
  flow writes field diary entries; a `field_diary.entry.submitted` event already
  fires (`service.py:311`). The design adds a subscriber in the daily_diary
  module that, on `field_diary.entry.submitted`, appends a `DiaryEntry` row
  (`oe_daily_diary_entry`, type `field`) to that day's office diary header,
  carrying `source_module = "field_diary"` and `source_ref = <field entry id>`
  (the office diary entry model already has exactly these columns,
  `daily_diary/models.py:174`). This is the bridge that makes a field-captured
  day show up in the office diary the foreman signs. It follows the same
  publish-detached, idempotent-subscriber pattern as the existing diary
  subscribers (`daily_diary/events.py:101`).

- field capture -> punchlist: a field punch capture creates a real
  `oe_punchlist_item`. From that moment it is a first-class punch item: it shows
  on the desktop Punch List page, runs the punchlist status FSM
  (open -> in_progress -> resolved -> verified -> closed), exports to the
  punchlist PDF/Excel, and its photo is cross-linked into the Documents hub by
  the code already at `punchlist/router.py:412`. The `geo_lat`/`geo_lon` it
  carries put it on the Geo Hub map (those columns exist for exactly this,
  `punchlist/models.py:75`).

- field capture -> inspections: a field inspection capture creates a real
  `oe_inspections_inspection`. The desktop Inspections page can then complete it,
  and the two existing bridges fire from there: `create-defect` turns a failed
  inspection into a punch item (`inspections/router.py:213`) and `create-ncr`
  raises a formal NCR (`router.py:324`). So a field-raised inspection flows
  inspection -> punchlist and inspection -> NCR through code that already exists,
  with no new bridge to write.

- inspections <-> punchlist already linked: the inspections `create-defect`
  endpoint is the canonical inspection-to-punch bridge. The field surface does
  not duplicate it; the field inspection becomes the input to it.

The net effect: the field PWA is a capture front door, and every captured item
lands in the same table the desktop product already reads, so the connection is
"same row, two surfaces", not a sync of parallel copies.

### 4.4 Offline correctness

Correctness does not depend on the service worker. It depends on three things,
two of which already exist:

1. The IndexedDB queue in `offlineStore.ts` persists writes across reloads and
   network drops (exists).
2. The `client_op_id` plus `oe_field_sync_op` unique constraint makes draining
   the queue idempotent (new). Without this, the existing `replayMutations`
   (`useOnlineStatus.ts:62`) can double-apply: it treats only `res.ok || 409` as
   success and re-fires the rest, and a successful POST whose response was lost on
   a flaky link would be re-sent and create a duplicate. The ledger closes that
   hole.
3. The field shell mounts its own sync loop (new), because `useOfflineSync` only
   runs inside `AppLayout`, which `/field` does not use.

## 5. Frontend

### 5.1 Feature folder and screens

All under `frontend/src/features/field/` (the folder and the lazy route already
exist, `App.tsx:224`). The skeleton `FieldShellPage.tsx` is replaced with a
working shell plus child screens. The shell deliberately reuses none of the
desktop heavy surfaces (AG Grid, Three.js, Cesium); the existing design doc
audited those as unusable under 768 px.

| Component | File | Role |
|-----------|------|------|
| `FieldShellPage` | `field/FieldShellPage.tsx` | bottom-nav shell (Today / Capture / Crew / Profile), mounts `useFieldSync()`, renders `<OfflineBanner/>` inside the field shell so the worker sees offline state without `AppLayout` |
| `FieldAuthPage` | `field/FieldAuthPage.tsx` | mounted at `/field/:token`, PIN entry, calls `consume` to exchange `(token, pin)` for the session token, stores it in the field auth store |
| `FieldTodayTab` | `field/tabs/FieldTodayTab.tsx` | reads `GET /field-diary/today/`, shows weather, crew count, my-entries pending-sync badge, top open punch items |
| `FieldCaptureFlow` | `field/capture/FieldCaptureFlow.tsx` | the 3-screen capture flow from the design doc section 6.2: camera, categorise (diary note / punch / inspection / photo), details + submit |
| `FieldPunchForm`, `FieldInspectionForm`, `FieldDiaryEntryForm` | `field/capture/*` | single-column, 48px-tall inputs, voice-friendly attributes, the forms specified in design doc section 6.3 |
| `FieldProfileTab` | `field/tabs/FieldProfileTab.tsx` | switch project (re-redeem), sign out + clear queue (flushes JWT-less field session and any unsynced mutations), pending-sync list with conflict review |

### 5.2 State and the sync loop

- Field auth store (Zustand, `frontend/src/stores/useFieldSessionStore.ts`):
  holds the field session token and PIN in memory (not the desktop
  `useAuthStore`, which holds JWTs). The field session token plus PIN are sent on
  every field request as `Authorization: Bearer` and `X-Field-PIN`.
- `useFieldSync()` (`frontend/src/features/field/useFieldSync.ts`): the field
  equivalent of `useOfflineSync`, but it must run on `/field`. It subscribes to
  the `online` event, drains the `offlineStore` queue FIFO at max 5 parallel, and
  attaches the field session headers (the existing `replayMutations` attaches the
  JWT from `useAuthStore`, which the field worker does not have, so the field
  shell needs its own drain that uses the field session). Each replayed op
  carries its `client_op_id` so the server dedups.
- A small `submitFieldMutation(path, body, clientOpId)` helper: online -> POST
  directly through the field client; offline -> `queueMutation` plus an optimistic
  local placeholder, returning the `client_op_id` so the UI can show "pending
  sync". This is the helper the existing design doc and the `FieldShellPage`
  header comment both reference as the missing piece.
- Photos: resized client-side to 1600px long edge before queueing (design doc
  section 7.4), stored as a Blob in a third IndexedDB store. This needs an
  `oe_offline` version bump from 1 to 2 in `offlineStore.ts` with a new
  `fieldPhotos` object store created in `onupgradeneeded`; the existing two
  stores are preserved.

### 5.3 How it surfaces to the user

The field worker opens a bookmarked `/field/:token` link, enters a 6-digit PIN
once, and lands on the bottom-nav shell. They tap Capture, take a photo,
categorise it (punch / inspection / diary / note), add a voice note, and submit.
If they are offline, the item is queued with a "Saved offline" toast (the toast
already exists in `api.ts:412`) and a pending-sync badge appears. When signal
returns, `useFieldSync` drains the queue and the badge clears. Back in the
office, the captured punch item is on the Punch List page, the inspection is on
the Inspections page, the diary entry is folded into the day's Daily Diary that
the foreman signs, and every geotagged item is a pin on the Geo Hub map. No one
re-keys anything.

## 6. Reuse (confirmed in code)

Built on, verified by reading the source:

- `backend/app/modules/field_diary/` whole module: auth (`request-magic-link`,
  `consume`, `verify_session`), `FieldSession`/`FieldMagicLink`/`FieldModuleGrant`
  models and repositories, `RequirePinPlusMagicLink`, `_require_field_module_grant`,
  the diary FSM, and `register_attachment`. The `module_key` column was built
  free-form for exactly this extension (`models.py:254`).
- `backend/app/modules/punchlist/router.py:346` photo upload: magic-byte gate via
  `app.core.file_signature.require` + `ALLOWED_PHOTO_TYPES`, server-derived
  filename, and the Documents hub cross-link at line 412. Reused verbatim for
  field punch photos.
- `backend/app/modules/inspections/router.py:213,324` the `create-defect` and
  `create-ncr` bridges. The field inspection feeds these, so the
  inspection -> punch and inspection -> NCR flows are already written.
- `backend/app/modules/daily_diary/models.py:174` the office diary entry's
  `source_module`/`source_ref` columns, and `daily_diary/events.py:101` the
  idempotent cross-module subscriber pattern, for the field-to-office diary
  bridge.
- `backend/app/core/permissions.py:41` the `FIELD_WORKER`/`SITE_FOREMAN`/
  `SITE_INSPECTOR` roles and `ROLE_HIERARCHY` ranks (already present).
- `backend/app/core/file_signature.py`, `app.database.GUID`,
  `app.core.db_types.AwareDateTime`, `app.core.events.event_bus`,
  `app.core.audit_log.log_activity` (the diary approve path already uses it,
  `field_diary/service.py:347`).
- `frontend/src/shared/lib/offlineStore.ts` IndexedDB cache + mutation queue.
- `frontend/src/shared/lib/api.ts:397` offline GET fallback + mutation queueing +
  the "Saved offline" toast.
- `frontend/src/shared/hooks/useOnlineStatus.ts` the online store and the
  `replayMutations` reference implementation (the field drain is modelled on it
  but uses field session headers).
- `frontend/src/shared/ui/OfflineBanner.tsx`, `OfflineFallback.tsx`,
  `PWAInstallPrompt.tsx`, and the workbox config in `vite.config.ts:123`.
- `frontend/src/features/field/FieldShellPage.tsx` and the `/field` lazy route.

## 7. Phasing

The build is split so the MVP is a real end-to-end offline flow with no stubs,
then fidelity is layered on. Effort is in developer-days for one engineer
familiar with the codebase.

### Phase 1: MVP, offline diary + punch capture end to end (region-neutral)

Scope: one migration (`oe_field_sync_op` plus the three additive columns);
`FieldSyncService` with idempotent `apply_op` for `diary_entry`, `diary_photo`,
`punch_item`, `punch_photo`; the `today/`, `capture/photo/`, `capture/punch/`,
`sync/batch/`, `sync/ops/` endpoints; the field-to-office diary subscriber;
replace `FieldShellPage` skeleton with the working shell; `FieldAuthPage` PIN
entry; `FieldTodayTab`; `FieldCaptureFlow` for diary note + punch + photo;
`useFieldSync` drain loop mounted on `/field`; `submitFieldMutation`;
`offlineStore` version bump to 2 with the `fieldPhotos` store. At the end a worker
can, fully offline, capture a punch item with a photo and a diary note, reconnect,
and see both land in the desktop Punch List and Daily Diary with no duplicates.
No stubs: every path writes a real row through an existing service.

Effort: 9 days.

### Phase 2: Inspections capture + conflict review UI

Scope: `capture/inspection/` endpoint and `FieldInspectionForm`; wire the field
inspection into the existing `create-defect`/`create-ncr` bridges from the
desktop side (no new bridge code, just the capture); the conflict-review surface
in `FieldProfileTab` that reads `sync/ops/` and lets a worker keep-as-new or
discard a 409'd op (design doc section 7.3); Crew tab read-only
(`GET /field-diary/crew/`). Geo pins verified on the Geo Hub map for field punch
and inspection.

Effort: 6 days.

### Phase 3: Sync robustness + PWA hardening

Scope: exponential backoff on the drain (1s, 5s, 30s, 5m, 30m, give up) matching
the design doc; `fieldPhotos` IndexedDB cap at 200 MB with oldest-dropped toast;
captive-portal detection (a 1px image fetch against own origin to defeat
`navigator.onLine` lying behind site Wi-Fi captive portals, design doc risk 8);
resolve the service-worker question on `:8000` (decide whether to retire the
self-destruct `public/sw.js` so the workbox SW serves and pre-seeds `today/` into
`oce-api`); PWA install prompt surfaced on `/field`.

Effort: 5 days.

### Region-neutral core and partner-pack extension points

The core captures region-neutral primitives: a diary entry, a punch item, an
inspection with a free-form `checklist_data` list, a photo with GPS. None of the
capture endpoints or forms hardcode a national standard. Region-specific
behaviour attaches at four declared extension points, consistent with how the
partner-pack system already layers presets (`MEMORY.md`, the partner-pack notes):

- Inspection checklist templates: `checklist_data` is a generic list of
  `{question, response_type, response, critical}`. A partner pack supplies named
  templates (US AIA-style QA checklists, DACH DIN inspection sheets, UK JCT
  practical-completion snag templates) that the capture form offers as a starting
  checklist. No core change.
- Diary sign-off and report format: the office Daily Diary already owns sign,
  archive, SCL Protocol bundle and PDF (`daily_diary/router.py:1138,291`). Region
  packs select the diary report template (US, DIN, JCT) at that layer; the field
  flow only feeds entries in.
- Punch priority and trade vocabularies: free-form `priority`/`trade` strings; a
  pack can constrain or relabel them per region without touching the capture
  endpoint.
- Payment-application linkage (US AIA G702/G703, DACH Abschlagsrechnung): out of
  scope for the field surface itself, but the field-captured progress feeds the
  daily diary and the schedule actuals events
  (`daily_diary/events.py:37`) that those region packs consume downstream. The
  field flow stays neutral; the pack reads the events.

## 8. Risks and edge cases

| # | Risk / edge case | Mitigation |
|---|------------------|------------|
| 1 | Queue double-drain creates duplicate rows (the existing `replayMutations` re-fires anything that is not `ok`/409, and a lost-response POST would re-send). | `client_op_id` + `oe_field_sync_op` unique constraint; `apply_op` returns the prior result on a seen op. This is the core safety property. |
| 2 | `useOfflineSync` does not run on `/field` (it is only in `AppLayout`). A worker's offline writes would never drain. | Phase 1 ships `useFieldSync` mounted in `FieldShellPage`, with field session headers rather than the JWT. |
| 3 | The production SW is a self-destruct stub (`public/sw.js`), not workbox. Field correctness must not assume the `oce-api` cache lane is live. | Correctness rests on the IndexedDB queue, independent of the SW. Phase 3 resolves which SW serves on `:8000` and only then relies on workbox pre-seeding. |
| 4 | Clock skew: a device offline for hours stamps `captured_at` from a wrong clock; UTC-midnight rollover could land an entry on the wrong day. | Business dates are ISO `String` columns stamped from the device's local capture time (matching the `field_diary` `entry_date` rationale at `models.py:70`); `FieldTodayResponse.server_time` lets the client show skew; the diary unique key is `(project, author, date)` so a late sync updates the right day. |
| 5 | Photo payload: a worker queues 50 photos offline that drain at end of day and saturate the link. | Client resize to 1600px before queueing (cuts ~10x), drain max 5 parallel, `fieldPhotos` store capped at 200 MB with oldest-dropped toast (Phase 3). |
| 6 | A queued punch references a `punch_item_id` (photo-to-punch) whose punch op has not yet drained. | The drain is FIFO and the create op for a punch precedes its photo op in the same queue; if a photo op resolves a 404 (parent not yet there), it stays queued and retries after the parent drains. |
| 7 | Stolen tablet. | Foreman revokes the `oe_field_module_grant` in one operation (`DELETE /grants/{id}/`), which `_require_field_module_grant` checks on every request; the bookmarked URL is useless without the PIN and the PIN useless without the URL (design doc section 5). Profile tab's sign-out clears the session token and the queue. |
| 8 | PIN brute force. | Already mitigated: `PIN_MAX_ATTEMPTS = 5` burns the magic link (`field_diary/service.py:531`). |
| 9 | Conflict (409) on replay, e.g. a diary entry for that author+date created on another device. | `apply_op` records `status = conflict` and the detail; the client surfaces "tap to review" and lets the worker keep-as-new or discard (Phase 2); never silently dropped. |
| 10 | Fresh-install SQLite `create_all` does not see the new table. | Add `oe_field_sync_op` to the pre-`create_all` import list in `main.py` (the codebase's recurring gotcha). |
| 11 | A field worker is a provisioned `oe_users_user` with no role and no permissions (`field_diary/router.py:181`). They must not reach any standard `RequirePermission` endpoint. | The capture endpoints use only the field session deps, never `RequirePermission`; the field session carries no JWT, so the standard stack is never satisfied. |

## 9. Test plan

### 9.1 Backend (pytest, per-module temp SQLite before app import)

Follow the exact pattern in `backend/tests/integration/test_field_diary.py:21`:
set `DATABASE_URL` / `DATABASE_SYNC_URL` to a temp SQLite file and `APP_DEBUG=true`
before importing the app, then `Base.metadata.create_all` for only the tables
under test (including `oe_field_sync_op` and the existing field, punchlist and
inspection tables).

- Idempotency: replay the same `client_op_id` twice against `capture/punch/`;
  assert exactly one `oe_punchlist_item` row and the same `result_id` both times.
- Cross-project scope: open a session pinned to project A; `capture/punch/` with a
  body naming project B is rejected; `today/` only ever returns project A; a
  `punch_item_id` from project B resolves to 404.
- Module grant kill switch: revoke the grant, assert every capture endpoint
  returns 403 (the `_require_field_module_grant` path).
- PIN required: capture without `X-Field-PIN` returns 401 (mirrors the existing
  field-diary tests).
- Photo magic-byte gate: a non-image payload to `capture/photo/` returns 415; a
  valid JPEG creates the punch photo and the Documents hub cross-link row.
- Field-to-office diary bridge: submit a field diary entry, assert a
  `daily_diary` `DiaryEntry` row appears with `source_module = field_diary` and
  the field entry id in `source_ref`; assert the subscriber is idempotent on a
  re-published event.
- Inspection capture feeds the bridge: capture an inspection, complete it as
  `fail` via the inspections endpoint, call `create-defect`, assert a punch item
  is created (re-uses existing `test_snag_punchlist_bridge.py` and
  `test_inspections_idor.py` as references).

Unit tests for `FieldSyncService.apply_op` with stubbed repositories, matching
the stub style in `backend/tests/unit/test_punchlist.py:26`.

### 9.2 Frontend (vitest)

Existing `frontend/src/shared/lib/offlineStore.test.ts` covers the queue
primitives; extend it for the `fieldPhotos` store and the version-2 upgrade.

- `submitFieldMutation`: online path POSTs through the field client; offline path
  (`navigator.onLine = false`, mocked) calls `queueMutation` with a stable
  `client_op_id` and returns the optimistic placeholder.
- `useFieldSync`: with three queued ops, firing the `online` event drains them
  FIFO, attaches the field session headers, and clears the pending badge; a 409
  moves the op to the conflict list rather than removing it.
- `FieldAuthPage`: a valid PIN consumes the link and stores the session;
  a wrong PIN surfaces the 401 message without storing a session.
- Component render tests for the capture forms asserting the touch-target and
  voice-input attributes (48px inputs, `autocapitalize="sentences"`,
  `inputmode`), consistent with the design doc section 6.3.

### 9.3 Manual browser verification on the `:8000` server

Run the backend on `:8000` (the README/dev default that `vite.config.ts:287`
proxies to) with `APP_DEBUG=true` so `request-magic-link` returns the dev token
and PIN.

1. As admin, create a project and a field module grant for a provisioned field
   user (`POST /api/v1/field-diary/grants/`).
2. `POST /api/v1/field-diary/auth/request-magic-link/`, copy the dev token + PIN,
   open `/field/<token>` in the browser, enter the PIN, confirm the bottom-nav
   shell renders and the Today tab loads.
3. Open DevTools, throttle to Offline. Capture a punch item with a photo and a
   diary note; confirm the "Saved offline" toast and the pending-sync badge.
4. Restore the network; confirm `useFieldSync` drains the queue and the badge
   clears.
5. In a normal desktop session, open the Punch List page and the Daily Diary for
   that project and date; confirm the field-captured punch item and diary entry
   are present, the photo is in the Documents hub, and the geotagged punch is a
   pin on the Geo Hub map.
6. Re-trigger the drain (toggle offline/online twice) and confirm no duplicate
   rows appear (the idempotency ledger).
7. Run the `qa-crawler` skill against `/field` for axe-core touch-target and
   console-error coverage, and `/i18n-sweep` for the new field strings.

Sequential only against a shared server: never parallelise browser probes against
the demo VPS (`MEMORY.md` feedback note).
