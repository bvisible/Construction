# Submittals and RFI through Approval Routes plus CDE linkage

Status: design, ready to build
Author: DataDrivenConstruction
Scope: backend (FastAPI) plus frontend (React/TS)

## 1. Summary and the core insight

This feature wires three modules that already exist and ship today but never talk to each other:

- `backend/app/modules/submittals` (model `Submittal`, table `oe_submittals_submittal`, already carries `linked_boq_item_ids`).
- `backend/app/modules/rfi` (model `RFI`, table `oe_rfi_rfi`, already carries `linked_drawing_ids` and `change_order_id`).
- `backend/app/modules/approval_routes` (the generic multi-step approval engine: `Route`, `Step`, `Instance`, `StepState`).
- `backend/app/modules/cde` (ISO 19650 `DocumentContainer`, `DocumentRevision`).
- `backend/app/modules/notifications` (already subscribes to `submittal.status_changed` and `rfi.assigned`).

The single most important verification result drives the whole plan: the approval-routes engine is fully built and is consumed by nobody. A repository-wide search for `approval_routes` returns only the seven files inside the module itself (`models.py`, `service.py`, `router.py`, `repository.py`, `permissions.py`, `manifest.py`, `__init__.py`). The model already declares `submittal` and `rfi` in `TARGET_KINDS` (`backend/app/modules/approval_routes/models.py` lines 50 to 59), the service already validates those kinds, already serialises decisions through `Instance` and `StepState`, already publishes lifecycle events (`approval_routes.instance.started`, `.advanced`, `.completed`, `.rejected`, `.cancelled`), and the frontend already has a complete client and component set at `frontend/src/features/approval-routes/` (`api.ts`, `types.ts`, `RouteEditor.tsx`, `ApprovalInstanceCard.tsx`, `ApprovalInstancesList.tsx`).

So this is largely activation, not greenfield. The connective tissue is what we add. We do not rebuild the engine, the submittal FSM, the RFI FSM, or the CDE container model. We add a thin linkage layer: a polymorphic link table so submittals and RFIs can attach to CDE containers and BOQ positions, two small router surfaces on the submittals and rfi modules to start and read approval workflows against themselves, a set of event subscribers that keep the submittal and RFI status in step with the approval instance outcome, and the UI panels that surface the approval ladder and the CDE/BOQ links inside the submittal and RFI detail screens.

## 2. What was verified in the code

| Claim | Evidence |
|-------|----------|
| Approval engine is generic and unused | `grep approval_routes` over `backend/app/modules` returns only the module's own 7 files. |
| Engine supports submittal and rfi targets already | `TARGET_KINDS` in `approval_routes/models.py` lines 50 to 59 includes both. |
| Engine has start, decide, cancel, list, with race guards | `ApprovalRouteService.start_instance`, `submit_decision`, `cancel_instance` in `approval_routes/service.py`; `with_for_update` lock plus `UniqueConstraint(instance_id, step_id, approver_user_id)`. |
| Engine publishes lifecycle events | `_safe_publish` calls in `approval_routes/service.py`: `approval_routes.instance.started`, `.advanced`, `.completed`, `.rejected`, `.cancelled`. |
| Engine router is project-scoped and RBAC-gated | `approval_routes/router.py` uses `verify_project_access` and `RequirePermission("approval_routes.read|write|decide|manage")`. |
| Submittal carries BOQ links today | `Submittal.linked_boq_item_ids` JSON column, `submittals/models.py` lines 53 to 58. |
| Submittal has a real FSM and review/approve endpoints | `_SUBMITTAL_STATUS_TRANSITIONS` plus `submit_submittal`, `review_submittal`, `approve_submittal` in `submittals/service.py`. |
| RFI carries drawing links and a CO cross-link today | `RFI.linked_drawing_ids`, `RFI.change_order_id`, `rfi/models.py` lines 59 to 77. |
| RFI already has a cross-module mint pattern to copy | `POST /{rfi_id}/create-variation/` in `rfi/router.py` lines 508 to 608 mints a ChangeOrder via `ChangeOrderService`. |
| CDE container and revision exist | `DocumentContainer`, `DocumentRevision` in `cde/models.py`; revision already cross-links to a Documents hub row via `document_id`. |
| Notifications already listens for our domain events | `event_handlers.py` line 1728 subscribes `submittal.status_changed`; line 1724 `rfi.assigned`; wave-5 cross-module subscriber pattern at `notifications/_wave5_cross_module_subscribers.py`. |
| Money is string/Decimal, dates are String ISO, ids are UUID | `RFI.cost_impact_value` String plus Decimal round-trip in `rfi/schemas.py`; `Submittal.date_*` String(20); `GUID()` primary keys everywhere. |
| Tests use per-module temp sqlite set before import | `backend/tests/conftest.py` lines 38 to 42 set `DATABASE_URL` to a temp sqlite before any `app.` import; engine tests build `sqlite+aiosqlite:///:memory:` per test. |
| Routers auto-mount on a kebab prefix | `module_loader.py` lines 199 to 210: `oe_submittals` -> `/api/v1/submittals`, `oe_rfi` -> `/api/v1/rfi`, `oe_approval_routes` -> `/api/v1/approval-routes`. |

Constraint compliance: nothing in this design touches IfcOpenShell or native IFC parsing. CDE linkage is metadata only (container id, revision id, suitability code). BCF is not needed here and is not used.

## 3. Data model

### 3.1 Reuse, do not recreate

No changes to `Submittal`, `RFI`, `Route`, `Step`, `Instance`, `StepState`, `DocumentContainer`, `DocumentRevision`. The submittal already has `linked_boq_item_ids`. The approval engine already has every table needed for the workflow itself, and the engine stores the link from a workflow to its target inside `Instance.target_kind` plus `Instance.target_id`. We add no columns to any of those tables.

### 3.2 New table: a polymorphic CDE and document link

The only structural gap is a durable, queryable link from a submittal or an RFI to CDE containers, CDE revisions, and arbitrary document references. Today an RFI stores raw drawing UUIDs in a JSON array (`linked_drawing_ids`) with no integrity and no back-reference, and a submittal has no document link table at all (attachments live inside the metadata JSON blob, see `submittals/router.py`). A JSON blob cannot answer "which submittals reference container X" without a full table scan and a Python loop. We add one polymorphic link table that both modules share, mirroring the polymorphic style the approval engine itself uses (`target_kind` plus `target_id`, no hard FK into a specific module table).

New module `backend/app/modules/doc_links` (follows the module conventions: `manifest.py`, `models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`, `permissions.py`, `__init__.py`, `tests/`). One table.

Table `oe_doc_links_link`:

| Column | Type | Notes |
|--------|------|-------|
| `id` | `GUID()` PK | base mixin |
| `created_at`, `updated_at` | `DateTime(timezone=True)` | base mixin, server default now |
| `project_id` | `GUID()` FK `oe_projects_project.id` ondelete CASCADE, indexed | scoping, required |
| `source_kind` | `String(64)` | whitelist `submittal`, `rfi` (open-ended in DB, validated tuple in code) |
| `source_id` | `GUID()` | the submittal id or RFI id |
| `link_kind` | `String(32)` | whitelist `cde_container`, `cde_revision`, `document`, `boq_position` |
| `target_ref` | `String(36)` | the linked container id, revision id, document id, or BOQ position id |
| `label` | `String(255)` nullable | optional human label, sanitised |
| `created_by` | `String(36)` nullable | actor |
| `metadata_` | `JSON` mapped to column `metadata`, default `{}` | extensibility, mirrors every other module |

Constraints and indexes:

- `UniqueConstraint(source_kind, source_id, link_kind, target_ref, name="uq_doc_links_source_target")` so the same link is not stored twice (idempotent linking, matches the dedup logic already in the submittal attachment endpoint).
- `Index("ix_doc_links_source", "source_kind", "source_id")` for "list links for this submittal" and "for this RFI".
- `Index("ix_doc_links_target", "link_kind", "target_ref")` for "which sources reference this container".

This table is region neutral. It holds no AIA, DIN, or JCT semantics. The `boq_position` link kind generalises the submittal's existing `linked_boq_item_ids` so RFIs can link BOQ positions too, and gives both a single back-reference query path. We keep `Submittal.linked_boq_item_ids` in place for backward compatibility and dual-write to the link table inside the service so existing readers and the new query path stay consistent (see service logic). We do not migrate `RFI.linked_drawing_ids` away either; the new `cde_container` and `document` link kinds are additive.

### 3.3 Alembic migration outline

One migration file `backend/alembic/versions/v3151_doc_links_init.py`, `down_revision = "v3150_file_favorites"` (the current head per the versions directory). Follow the exact idempotent pattern of `v3147_approval_routes.py`:

- `def _table_exists` and `_index_exists` helpers using `sa.inspect(bind)`.
- `upgrade()`: guard `if not _table_exists(bind, "oe_doc_links_link")` then `op.create_table` with `id`/`created_at`/`updated_at` as `String(36)` and `DateTime(timezone=True)` server-default `sa.func.now()` exactly as the engine tables do, the columns above, the unique constraint inline, then two guarded `op.create_index` calls.
- `downgrade()`: `if _table_exists` then `op.drop_table`.

The migration must be idempotent because a fresh install boots the app first and `Base.metadata.create_all` already creates the table from the ORM model (the same reason the v3147 docstring gives). Register the new model in `backend/tests/conftest.py` import block and in any eager-import list `main.py` uses for fresh-DB `create_all`, the same way `submittals` and `rfi` models are registered, so SQLite dev and the test suite both see the table.

No column type surprises: ids are `String(36)` on disk via `GUID()`, there are no datetime business columns (we keep dates as String ISO where the domain needs them, and link rows only carry the framework `created_at`).

## 4. API

All paths below are under `/api/v1`. The approval-routes endpoints already exist and are reused verbatim by the frontend; we add convenience surfaces on the submittals and rfi modules plus the doc-links surface. Project scoping uses the existing `verify_project_access(project_id, user_id, session)` helper (`backend/app/dependencies.py` line 411), which returns 404 on both missing and forbidden to avoid IDOR leakage.

### 4.1 Reused as-is (no change)

| Method and path | Purpose |
|-----------------|---------|
| `GET /approval-routes/meta` | target kinds, modes, statuses whitelist |
| `GET /approval-routes/routes?project_id=&target_kind=submittal\|rfi&include_inactive=false` | list templates for the picker |
| `POST /approval-routes/routes` | create a route template with steps |
| `PATCH /approval-routes/routes/{id}`, `DELETE /approval-routes/routes/{id}` | edit, archive |
| `POST /approval-routes/instances` | start a workflow, body `{route_id, target_kind, target_id}` |
| `GET /approval-routes/instances?target_kind=&target_id=` | the active and historical workflows on one submittal or RFI |
| `POST /approval-routes/instances/{id}/decide` | approve or reject the current step |
| `POST /approval-routes/instances/{id}/cancel` | cancel a pending workflow |

### 4.2 New: submittal approval convenience surface

Mounted by `submittals/router.py` (prefix `/api/v1/submittals`). These are thin wrappers that resolve project scope from the submittal, then delegate to `ApprovalRouteService`, so the caller never has to know the submittal's project id or juggle two modules. RBAC reuses the submittal permissions plus the engine permissions.

| Method and path | Body | RBAC | Response |
|-----------------|------|------|----------|
| `POST /submittals/{submittal_id}/route` | `{route_id}` | `submittals.update` plus `approval_routes.write` | `InstanceResponse` (201) |
| `GET /submittals/{submittal_id}/route` | none | `submittals.read` | `InstanceResponse | null` (the latest instance, with `step_states`) |

The decide and cancel actions continue to use the generic `POST /approval-routes/instances/{id}/decide` and `/cancel` because the frontend already calls them and they carry the engine's race guard. We do not duplicate them on the submittal surface.

### 4.3 New: RFI approval convenience surface

Mounted by `rfi/router.py` (prefix `/api/v1/rfi`). Identical shape.

| Method and path | Body | RBAC | Response |
|-----------------|------|------|----------|
| `POST /rfi/{rfi_id}/route` | `{route_id}` | `rfi.update` plus `approval_routes.write` | `InstanceResponse` (201) |
| `GET /rfi/{rfi_id}/route` | none | `rfi.read` | `InstanceResponse | null` |

The double-permission dependency mirrors the pattern already in `rfi/router.py` `create_variation_from_rfi`, which requires both `rfi.update` and `changeorders.create` so RBAC stays consistent across the two modules.

### 4.4 New: doc-links surface

Mounted by the new `doc_links` module (prefix `/api/v1/doc-links`). Generic, used by both the submittal and RFI detail screens.

| Method and path | Body or query | RBAC | Response |
|-----------------|---------------|------|----------|
| `GET /doc-links?source_kind=&source_id=` | query | `doc_links.read` (VIEWER) | `list[DocLinkResponse]` |
| `POST /doc-links` | `{project_id, source_kind, source_id, link_kind, target_ref, label?}` | `doc_links.write` (EDITOR) | `DocLinkResponse` (201) |
| `DELETE /doc-links/{link_id}` | none | `doc_links.write` (EDITOR) | 204 |
| `GET /doc-links/back-references?link_kind=cde_container&target_ref={container_id}` | query | `doc_links.read` | `list[DocLinkResponse]` (which submittals and RFIs reference this container) |

Every endpoint resolves `project_id` (from body on create, from the row on read or delete) and calls `verify_project_access`. On create the service also validates that `target_ref` actually resolves: for `cde_container` it loads via `ContainerRepository.get_by_id` and checks the container's `project_id` equals the link's `project_id`; for `cde_revision` it loads via `RevisionRepository.get_by_id` then the parent container; for `boq_position` it loads via the BOQ position repository and walks position to BOQ to project; for `document` it loads via `DocumentRepository.get_by_id`. A cross-project `target_ref` is rejected with 422 so a link can never straddle tenants. `label` is run through `app.core.sanitize.strip_dangerous_html` exactly as RFI text is.

### 4.5 Request and response shapes

`DocLinkResponse` (Pydantic, `from_attributes=True`, `metadata` aliased from `metadata_` like every other module response):

```
id: UUID
project_id: UUID
source_kind: Literal["submittal", "rfi"]
source_id: UUID
link_kind: Literal["cde_container", "cde_revision", "document", "boq_position"]
target_ref: str
label: str | None
created_by: str | None
metadata: dict
created_at: datetime
updated_at: datetime
```

The approval convenience endpoints return the engine's existing `InstanceResponse` (from `approval_routes/schemas.py`), so the frontend reuses its existing `ApprovalInstance` type with zero new wire contract.

## 5. Service logic, the connective tissue

This is the point of the feature. The flow ties submittals and RFIs to the approval engine, to CDE, to BOQ, and to notifications.

### 5.1 Starting an approval on a submittal or RFI

`SubmittalService.start_approval(submittal_id, route_id, started_by)`:

1. Load the submittal (`get_submittal`, 404 if missing). Read `submittal.project_id`.
2. Build `InstanceCreate(route_id=route_id, target_kind="submittal", target_id=submittal_id)` and call `ApprovalRouteService(self.session).start_instance(...)`. The engine validates that the route is active, that the route's `target_kind` is `submittal`, that the route has steps, and that no workflow is already pending on this target (409). We get those guards for free.
3. On success, transition the submittal into review. We reuse the existing FSM: if the submittal is `draft` we call the existing `submit_submittal` path first so the state machine stays honest (`draft -> submitted`), then leave it `submitted` while the workflow runs. We do not invent a parallel status; the approval `Instance.status` is the source of truth for the routed decision, and the submittal `status` reflects the FSM. The instance id is recorded in `submittal.metadata_["approval_instance_id"]` so the detail screen can deep-link without a second query.
4. The engine already logs to `audit_log` and publishes `approval_routes.instance.started`.

`RFIService.start_approval(rfi_id, route_id, started_by)` is the mirror image with `target_kind="rfi"`. For an RFI the natural pre-state is `open` (the question is live and now needs a routed sign-off on the answer); if the RFI is `draft` we move it `draft -> open` through the existing `update_rfi` FSM gate before starting the workflow.

Both services run inside the request session, so the FSM transition and the instance insert commit together.

### 5.2 Reacting to the approval outcome, the key wiring

The engine fires `approval_routes.instance.completed` (approved) and `approval_routes.instance.rejected` with a payload that already carries `target_kind` and `target_id` (see `submit_decision` in `approval_routes/service.py`, the `base_event` dict). We add a new cross-module subscriber file `backend/app/modules/submittals/approval_subscribers.py` and `backend/app/modules/rfi/approval_subscribers.py`, registered from each module's `on_startup` (next to `register_submittals_permissions`), following the exact wave-5 subscriber pattern (`async_session_factory`, best-effort, swallow exceptions, gate cross-session writes appropriately):

Submittal subscriber `_on_approval_completed`:

- Filter on `event.data["target_kind"] == "submittal"`. Parse `target_id`.
- Open an isolated session via `async_session_factory`. Load the submittal.
- If the submittal is in a reviewable state (`submitted` or `under_review`), call `SubmittalService.approve_submittal(submittal_id, approver_id=<the deciding approver from the event>)`. That method is idempotent and already does the compare-and-swap, the audit-log write, and publishes `submittal.approved`. The routed decision now drives the FSM rather than a human clicking the legacy `/approve/` button.

Submittal subscriber `_on_approval_rejected`:

- Same filter. Call `SubmittalService.review_submittal(submittal_id, new_status="rejected", reviewer_id=<approver>, notes=<step comment>)`. That sets ball-in-court back to the submitter, persists the comment into metadata, and publishes `submittal.rejected`, which notifications already consumes.

RFI subscribers are the analogues: on `completed` for an RFI we close the loop by setting the RFI to `answered` if it has an `official_response`, or we leave the answer flow to the human and only record the routed approval in the audit trail when no response exists yet; on `rejected` we reopen via the manager-gated `answered -> open` path with the step comment as the reason. The exact RFI mapping is intentionally conservative because the RFI FSM and the approval FSM are orthogonal (an RFI answer can be approved or sent back); the subscriber only ever drives transitions the existing FSM already allows, so it can never corrupt state.

Because the engine publishes through `publish_detached` and these subscribers open their own session, there is no deadlock on SQLite's single writer (the same reasoning the engine's `_safe_publish` docstring spells out). In the test harness `conftest.py` shims `publish_detached` to run synchronously, so a test can assert the submittal flipped to approved immediately after the decision.

### 5.3 CDE and BOQ linkage flow

`DocLinkService.create_link(payload, created_by)`:

1. `verify_project_access` at the router. Validate `source_kind` and `link_kind` against the code whitelists (422 on unknown).
2. Resolve and tenant-check `target_ref` as described in 4.4 using the existing repositories (`ContainerRepository`, `RevisionRepository`, BOQ position repository, `DocumentRepository`). This is the cross-module reach: doc_links depends on cde, boq, and documents only through their repositories, never their tables.
3. Insert the `Link` row. The unique constraint makes a duplicate a clean `IntegrityError`, caught and surfaced as 409 (idempotent linking), mirroring the submittal attachment dedup.
4. When `source_kind == "submittal"` and `link_kind == "boq_position"`, also append `target_ref` to `Submittal.linked_boq_item_ids` if absent (dual-write), so the existing BOQ-linkage readers and the new back-reference query agree. When the link is removed, remove it from both.
5. Emit `doc_link.created` with `{project_id, source_kind, source_id, link_kind, target_ref}` so future consumers (for example a CDE container that wants to show "referenced by 3 RFIs") can react. No consumer is required for the MVP.

The CDE back-reference (`GET /doc-links/back-references`) is what makes the linkage bidirectional and useful: from a CDE container the user can see every submittal and RFI that points at it, and from a submittal or RFI the user sees every container, revision, document, and BOQ position it points at. The link is metadata only and respects the no-IFC constraint.

### 5.4 End-to-end narrative

A reviewer opens a submittal, links the relevant CDE container revision and the two BOQ positions the shop drawing covers (doc_links). They pick an approval route template (engine, project-scoped picker), and start the workflow (`POST /submittals/{id}/route`). The submittal moves to `submitted`. Each approver in turn calls `/approve-routes/instances/{id}/decide`. On the final approval the engine fires `instance.completed`, the submittal subscriber flips the submittal to `approved` through the existing idempotent path, which fires `submittal.approved`, which notifications already turns into a notice to the submitter and ball-in-court holders. Every hop writes an `audit_log` row. The RFI path is identical with `target_kind="rfi"`.

## 6. Frontend

Feature folders already exist: `frontend/src/features/submittals/`, `frontend/src/features/rfi/`, `frontend/src/features/approval-routes/`, `frontend/src/features/cde/`. We add to them, we do not create new top-level features.

### 6.1 Reused components and clients

- `frontend/src/features/approval-routes/api.ts` and `types.ts`: complete client for routes and instances, plus React Query keys. Reused verbatim.
- `frontend/src/features/approval-routes/ApprovalInstanceCard.tsx` and `ApprovalInstancesList.tsx` and `RouteEditor.tsx`: render the step ladder from `step_states` joined against the route's `steps`, and expose approve/reject. Reused as embedded panels.
- `frontend/src/features/submittals/api.ts` and `frontend/src/features/rfi/api.ts`: existing clients; we add the two new helper functions per module (`startSubmittalApproval`, `getSubmittalApproval`; `startRFIApproval`, `getRFIApproval`) that call the new convenience endpoints, and a small `docLinks` client (`listLinks`, `createLink`, `deleteLink`, `backReferences`) plus types.

### 6.2 New surfaces

- Submittal detail (the submittals feature currently ships `SubmittalsPage.tsx`; the detail panel gains two tabbed sections): an "Approval" section that, when no instance exists, shows the route picker (`listRoutes({ projectId, targetKind: 'submittal', includeInactive: false })`) and a Start button, and when an instance exists embeds `ApprovalInstanceCard`. A "Links" section listing CDE containers, revisions, documents, and BOQ positions with add and remove, backed by the doc_links client. State: React Query, keyed by `approvalRoutesKeys.instances('submittal', submittalId)` and a new `docLinksKeys.list('submittal', submittalId)`.
- RFI detail (`frontend/src/features/rfi/RFIDetailPage.tsx` exists): same two sections with `targetKind: 'rfi'` and `source_kind: 'rfi'`. The existing drawing-link UI stays; the new CDE container link is added alongside it.
- CDE container detail (in `frontend/src/features/cde/`): a "Referenced by" panel calling `backReferences({ link_kind: 'cde_container', target_ref: containerId })`, rendering links back to the submittal and RFI detail routes.

All labels go through the existing i18n layer (the project keeps zero hardcoded strings). The approval-routes feature already has `labels.ts`; we add submittal-approval and doc-link keys to the locale JSON and they flow to all 26 locales through the standard i18n sweep.

## 7. Reuse summary (verified in code)

- Approval engine end to end: `ApprovalRouteService` (`start_instance`, `submit_decision`, `cancel_instance`, listing), `Route`/`Step`/`Instance`/`StepState` tables, the `/api/v1/approval-routes` router, the engine's lifecycle events, and its `with_for_update` plus unique-constraint race guards.
- Submittal FSM and endpoints: `submit_submittal`, `review_submittal`, `approve_submittal` (idempotent, compare-and-swap), `_SUBMITTAL_STATUS_TRANSITIONS`, `Submittal.linked_boq_item_ids`, the attachment dedup pattern.
- RFI FSM and the cross-module mint pattern: `respond_to_rfi`, `close_rfi`, `update_rfi` role gates, and `create_variation_from_rfi` as the template for the convenience-endpoint double-permission and lazy-import style.
- CDE repositories: `ContainerRepository.get_by_id`, `RevisionRepository.get_by_id` for link validation.
- BOQ: `Position` (`oe_boq_position`) for `boq_position` link validation.
- Documents: `DocumentRepository.get_by_id` (already imported by `submittals/router.py`).
- Core infra: `verify_project_access`, `RequirePermission`, `RequireRole` (`dependencies.py`); `permission_registry.register_module_permissions` (`core/permissions.py`); `log_activity` (`core/audit_log.py`); `event_bus.subscribe` and `publish_detached` (`core/events.py`); `strip_dangerous_html` (`core/sanitize.py`); `async_session_factory` (`app/database.py`); the wave-5 cross-module subscriber pattern (`notifications/_wave5_cross_module_subscribers.py`); the idempotent alembic helpers (`v3147_approval_routes.py`).
- Frontend: the whole `approval-routes` feature (api, types, components), the submittals and rfi api clients and pages.

## 8. Phasing

### Phase 1, MVP, end to end with no stubs (effort 4 days)

Activate the approval engine for submittals and RFIs.

- Submittal convenience endpoints `POST/GET /submittals/{id}/route`, RFI convenience endpoints `POST/GET /rfi/{id}/route`, both delegating to `ApprovalRouteService` and resolving project scope from the row.
- Submittal and RFI approval subscribers wiring the engine's `instance.completed` and `instance.rejected` events back into the existing FSM (idempotent `approve_submittal` and the manager-gated reject path). Registered from each module's `on_startup`.
- Record the instance id in the row metadata for deep-linking.
- Frontend: embed `ApprovalInstanceCard` and the route picker into the submittal and RFI detail screens, with the two new api helpers and React Query keys.
- Tests as in section 10 for these paths.

This phase ships a working feature: a routed multi-step sign-off on submittals and RFIs that drives the existing status machine and existing notifications, with no new table required (it uses only the engine and metadata).

### Phase 2, CDE and BOQ linkage (effort 3 days)

- New `doc_links` module: model, schema, repository, service, router, permissions, manifest, `__init__` with `on_startup` registering permissions.
- Alembic `v3151_doc_links_init.py`, idempotent.
- Link validation against cde, boq, documents repositories with tenant checks; dual-write to `Submittal.linked_boq_item_ids`.
- Back-reference endpoint and the CDE "Referenced by" panel.
- Frontend Links sections on submittal and RFI detail.
- Tests for link creation, dedup, cross-project rejection, back-references.

### Phase 3, deeper fidelity and partner-pack extension points (effort 4 days)

- Seed region-neutral default route templates per project on creation (a two-step "Reviewer then Approver" route for `submittal` and a one-step "Responder" route for `rfi`), tenant-wide so the picker is never empty. Region-specific templates and labels are delivered as partner packs, not core:
  - US: an AIA-style multi-stage submittal route (Contractor, A/E, Owner) and the G702/G703 vocabulary surfaced as route names and step labels; no schema change, the pack ships route templates plus locale labels.
  - DACH: DIN-aligned review stages and German step labels.
  - UK: JCT-style architect-instruction sign-off chain.
  Each pack registers its templates through the existing partner-pack entry-point group and the route create API, so the core stays region neutral and the engine's `target_kind` plus role-or-user steps already express every variant.
- SLA surfacing: the engine's `Step.sla_hours` is stored but not yet surfaced; add an overdue badge on the approval card and an optional `approval.step.overdue` emission from a scheduled scan (the codebase already has a job runner).
- An aggregate "Approvals" dashboard tile counting pending instances by target kind for the project, reusing the engine list endpoint.

## 9. Risks and edge cases

- Double source of truth between FSM and instance status. Mitigation: the approval `Instance.status` owns the routed decision, the submittal/RFI `status` owns the domain FSM, and the subscriber only ever drives transitions the existing FSM already permits. The subscriber calls the idempotent `approve_submittal`, so a duplicate event cannot double-approve.
- Engine rejects a second pending workflow on the same target (409). This is correct, but the UI must surface it as "a workflow is already running" and offer cancel-then-restart rather than a raw error. Handled in the frontend.
- Role steps degrade to any-style advance because the engine does not expand a role to its members (documented in `_maybe_advance`). For the MVP we prefer user-pinned steps in the seeded default routes so the behaviour is deterministic; role steps remain available for partner packs that accept the documented semantics.
- Cross-tenant link injection. Mitigation: `target_ref` is resolved and its project compared to the link's project at create time; a mismatch is 422. `verify_project_access` guards every read and delete.
- Orphan links when a container, revision, document, or BOQ position is deleted. The link table has no hard FK into those tables by design (polymorphic, cross-dialect safe), so a delete leaves a dangling link. Mitigation: the read path tolerates a missing target (the row still renders with a "target removed" marker) and a Phase 3 prune job can sweep orphans; this matches how the engine itself never FKs into target tables.
- SQLite single-writer deadlock if a subscriber wrote on the request session. Mitigation: subscribers open their own session via `async_session_factory` and the engine publishes detached, exactly as the wave-5 subscribers do.
- Migration re-run on a partially applied or fresh-create_all install. Mitigation: the migration is fully guarded with `_table_exists` and `_index_exists` like v3147.
- Money and dates. No new money or datetime business columns are introduced. Where a link carries context it stays in the JSON `metadata` blob, and the RFI cost-impact value continues to use the existing Decimal-string round-trip.

## 10. Test plan

### 10.1 Backend pytest

Pattern: per the repo, `backend/tests/conftest.py` sets `DATABASE_URL` to a temp sqlite before any `app.` import, and the engine suite builds a fresh `sqlite+aiosqlite:///:memory:` per test with `Base.metadata.create_all`. New tests follow the existing `tests/modules/approval_routes/test_approval_routes_engine.py` fixture style (seed a project and users, build the service directly).

New files:

- `backend/tests/modules/submittals/test_submittal_approval_link.py`:
  - Start an approval on a submittal, assert an `Instance` exists with `target_kind="submittal"` and the submittal moved out of draft.
  - Reject the second-of-two-step route, assert `instance.rejected` fired and the submittal subscriber moved the submittal to `rejected` with the step comment in metadata.
  - Approve every step, assert `instance.completed` fired and the submittal is `approved` (idempotent, no double approval on a duplicate event).
  - 409 when starting a second workflow on the same submittal while one is pending.
- `backend/tests/modules/rfi/test_rfi_approval_link.py`: the analogues for `target_kind="rfi"`, including the conservative RFI mapping (reject reopens an answered RFI through the manager-gated path, never an illegal transition).
- `backend/tests/modules/doc_links/test_doc_links.py`:
  - Create a `cde_container` link, assert dedup (second identical create is 409).
  - Cross-project `target_ref` is rejected 422.
  - `boq_position` link dual-writes into `Submittal.linked_boq_item_ids` and removing it cleans both.
  - Back-reference query returns both a submittal and an RFI that point at the same container.
- Router-level tests under `tests/modules/.../` exercising RBAC: a VIEWER cannot start an approval (`approval_routes.write` denied), a non-member is 404 on the convenience endpoints (IDOR), `doc_links.write` is EDITOR.

### 10.2 Frontend vitest

- `frontend/src/features/submittals/__tests__/`: the approval section renders the route picker when no instance exists and the `ApprovalInstanceCard` when one does; clicking Start calls `startSubmittalApproval`; a 409 surfaces the "already running" message. The Links section adds and removes a link and refetches.
- `frontend/src/features/rfi/__tests__/`: the analogues, and that the existing drawing-link UI still works alongside the new CDE link.
- Reuse the existing `approval-routes/__tests__` for the card and ladder rendering (no change needed).

### 10.3 Manual browser verification on the :8000 server

- Log in, open a project, open a submittal detail.
- Confirm the route picker lists active `submittal` routes; start a workflow; confirm the submittal status moved and the approval card shows the ladder with the first step active.
- As each approver, approve the step; confirm the card advances and on the last approval the submittal flips to `approved` and a notification lands for the submitter.
- Repeat the reject path; confirm the submittal returns to the submitter with the reviewer comment visible.
- On the same submittal, link a CDE container revision and two BOQ positions; open the CDE container and confirm the "Referenced by" panel lists the submittal; delete a link and confirm both the submittal Links list and the container back-reference update.
- Repeat the approval and linking flow on an RFI detail screen.
- Confirm `/api/health` still reports the module count incremented by one (the new `doc_links` module) with `alembic_head_matches` true after `v3151`.
