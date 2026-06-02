# Drawing / Document Version Compare with Overlay

Implementation design. Region-neutral core, partner-pack extension points for AIA G702/G703, DIN, JCT and similar.

## 1. Summary

Side-by-side and overlay comparison of two versions of the same drawing or document, with a markup diff that shows which annotations were added, removed or carried over between the two revisions. The feature connects four existing modules: `file_versions` (the version chain that already tracks every re-upload), `documents` (the files and the download endpoint), `markups` (annotations that already carry `file_version_id`), and `cde` (the ISO 19650 revision register that sits on top of documents). The connective tissue is a new compare service that resolves two chain rows to their respective file bytes and to their respective markup sets, plus one schema change that makes historical bytes retrievable at all.

This is not a greenfield build. A working three-mode pixel viewer already exists at `frontend/src/features/markups/PdfCompare.tsx` (overlay onion-skin, per-pixel difference, side-by-side synced pan and zoom) and is routed at `/markups/compare`. What it lacks is any link to the version chain (it lists arbitrary project PDFs by `Document.id`), the markup diff overlay, and a backend that can serve an old version's bytes. The design keeps the existing viewer and wires it to the version chain.

## 2. What was verified in the code

| Claim | Evidence |
|-------|----------|
| Version chain exists, keyed `(project_id, file_kind, canonical_name)`, one `is_current` per chain | `backend/app/modules/file_versions/models.py` lines 47-113 |
| Chain endpoints: list, detail, create, restore | `backend/app/modules/file_versions/router.py` lines 47-138 |
| Chain row stores `file_id` (the kind's own row id), `version_number`, `checksum`, `file_size`, `superseded_*`, but NO per-version storage path | `backend/app/modules/file_versions/models.py` lines 68-107 |
| Markups already carry `file_version_id` and the viewer fades stale-version markups | `backend/app/modules/markups/models.py` lines 41-47; `MarkupsService._resolve_file_version_id` `service.py` lines 165-203 |
| Document download serves only the current `Document.file_path` | `backend/app/modules/documents/router.py` lines 1375-1463 |
| Re-upload overwrites `Document.file_path` in place; old bytes are abandoned, only the event is recorded | `backend/app/modules/documents/service.py` lines 524-558 (`upload_document_revision` updates `file_path`, then calls `register_new_version`) |
| Existing compare viewer lists arbitrary PDFs, never the chain | `frontend/src/features/markups/PdfCompare.tsx` lines 78-89, 786-802 |
| Compare route already mounted | `frontend/src/app/App.tsx` lines 103-104, 820 |
| CDE revisions cross-link to documents and store `storage_key` per revision | `backend/app/modules/cde/models.py` lines 57-92 (`DocumentRevision.storage_key`, `.document_id`) |
| Test convention: temp sqlite set in `tests/conftest.py` before any `from app...` import; per-test in-memory engine with `Base.metadata.create_all` | `backend/tests/conftest.py` lines 38-42; `backend/tests/unit/test_file_versions.py` lines 31-40 |
| Alembic head | `v3150_file_favorites` |

### The core blocker

The version chain records that a re-upload happened, but it does not keep the superseded file. `upload_document_revision` writes the new bytes to a new path and then calls `repo.update_fields(document_id, file_path=str(file_path), ...)`, so the previous revision's bytes are no longer referenced by any row. `GET /api/v1/documents/{id}/download/` resolves `Document.file_path`, which is always the latest. A true version compare needs the bytes of version N and version N-1 at the same time. Phase 1 fixes this by giving each chain row its own immutable storage pointer.

## 3. Data model

### 3.1 Change to an existing table: `oe_file_version`

Add an immutable per-version storage pointer plus a denormalised page count so the compare picker can warn about page mismatches without opening both PDFs. All columns are nullable for backward compatibility with the rows already written.

| Column | Type | Notes |
|--------|------|-------|
| `storage_key` | `String(500)` nullable | Absolute or upload-base-relative path to THIS version's bytes, snapshotted at upload time. NULL for legacy rows; the compare service falls back to the document's current `file_path` for the current row only. |
| `mime_type` | `String(100)` nullable | Snapshot of the content type at upload, so the viewer can pick a renderer (PDF vs raster) per version. |
| `page_count` | `Integer` nullable | Page count detected at upload (PDF) or 1 (raster). Used for the picker mismatch warning. Best-effort, NULL when undetected. |

We reuse the existing String-ISO and Decimal conventions: `superseded_at` is already `DateTime(timezone=True)`, `checksum` is already `String(64)`, ids are `GUID()`. No money in this feature.

The chain key, `is_current` flip, and restore semantics are untouched. The only behavioural change is that `register_new_version` now also persists `storage_key`, `mime_type`, `page_count`, and `upload_document_revision` snapshots the bytes to a per-version path rather than overwriting one shared path.

### 3.2 New table: `oe_compare_session`

A saved comparison so a reviewer can hand a teammate a link, and so an audit trail of "what was compared against what" survives. This is the table that physically connects the version chain to the markup diff. Region-neutral; partner packs read its `metadata_` for their own overlays.

```
oe_compare_session
  id                 GUID PK                                        (Base provides id/created_at/updated_at)
  project_id         GUID FK oe_projects_project ON DELETE CASCADE  not null, indexed
  file_kind          String(32)  not null        chain kind, validated against FILE_KINDS
  canonical_name     String(255) not null         chain key shared by both versions
  base_version_id    GUID FK oe_file_version ON DELETE CASCADE      not null  (the "A" / older side)
  compare_version_id GUID FK oe_file_version ON DELETE CASCADE      not null  (the "B" / newer side)
  mode               String(20)  not null default 'overlay'   one of overlay | diff | sidebyside
  title              String(255) nullable
  notes              Text        nullable
  change_summary     JSON        not null default {}     cached diff result, see 3.3
  created_by         String(36)  not null default ''
  __table_args__     Index(ix_compare_session_project, project_id, file_kind, canonical_name)
```

Both version FKs point at `oe_file_version.id`. We constrain at the service layer that both rows share the same `(project_id, file_kind, canonical_name)`. That is exactly what makes this a version compare rather than the old arbitrary-PDF compare: you can only compare two rows of one chain.

### 3.3 `change_summary` JSON shape

Cached so a re-open does not recompute. Written when a diff completes; region-neutral.

```json
{
  "markups": {
    "added":   [ { "id": "uuid", "type": "cloud", "page": 2, "label": "RFI-12" } ],
    "removed": [ { "id": "uuid", "type": "text",  "page": 1, "label": null } ],
    "carried": [ "uuid", "uuid" ],
    "counts":  { "added": 1, "removed": 1, "carried": 2 }
  },
  "pixel": { "changed_pct": 7, "page": 1, "computed_at": "2026-06-01T10:00:00Z" },
  "pages": { "base": 4, "compare": 5, "compared_up_to": 4 }
}
```

`pixel.changed_pct` is supplied by the client (the canvas diff already computes it in `PdfCompare.tsx` line 473) and posted back on save. The markup buckets are computed server-side from `file_version_id` (see 4 and 5).

### 3.4 Alembic migration outline

One revision, `down_revision = "v3150_file_favorites"`, file `backend/alembic/versions/v3151_drawing_version_compare.py`.

```
upgrade():
  # 1. widen oe_file_version with immutable per-version storage
  op.add_column("oe_file_version", sa.Column("storage_key", sa.String(500), nullable=True))
  op.add_column("oe_file_version", sa.Column("mime_type",   sa.String(100), nullable=True))
  op.add_column("oe_file_version", sa.Column("page_count",  sa.Integer(),  nullable=True))

  # 2. compare session table
  op.create_table(
    "oe_compare_session",
    sa.Column("id", GUID(), primary_key=True),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    sa.Column("project_id", GUID(), sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"), nullable=False),
    sa.Column("file_kind", sa.String(32), nullable=False),
    sa.Column("canonical_name", sa.String(255), nullable=False),
    sa.Column("base_version_id", GUID(), sa.ForeignKey("oe_file_version.id", ondelete="CASCADE"), nullable=False),
    sa.Column("compare_version_id", GUID(), sa.ForeignKey("oe_file_version.id", ondelete="CASCADE"), nullable=False),
    sa.Column("mode", sa.String(20), nullable=False, server_default="overlay"),
    sa.Column("title", sa.String(255), nullable=True),
    sa.Column("notes", sa.Text(), nullable=True),
    sa.Column("change_summary", sa.JSON(), nullable=False, server_default="{}"),
    sa.Column("created_by", sa.String(36), nullable=False, server_default=""),
  )
  op.create_index("ix_compare_session_project", "oe_compare_session",
                  ["project_id", "file_kind", "canonical_name"])

downgrade():
  op.drop_index("ix_compare_session_project", table_name="oe_compare_session")
  op.drop_table("oe_compare_session")
  op.drop_column("oe_file_version", "page_count")
  op.drop_column("oe_file_version", "mime_type")
  op.drop_column("oe_file_version", "storage_key")
```

`GUID` is imported from `app.database` exactly as every other migration does. Because dev and fresh installs build the schema through `Base.metadata.create_all` (not alembic), the new model must be importable so the loader picks it up. The compare module's `models.py` plus the three added columns on `FileVersion` satisfy that automatically since the module loader imports `<module>.models`.

## 4. API

New module `backend/app/modules/compare` following the standard conventions (`manifest.py`, `models.py`, `schemas.py`, `repository.py`, `service.py`, `router.py`, `permissions.py`). Auto-mounted at `/api/v1/compare/`. One small additive endpoint also lands on the documents router.

### 4.1 New endpoints

| Method | Path | Purpose | Permission |
|--------|------|---------|------------|
| GET | `/api/v1/compare/candidates/` | Given `file_id` + `kind`, return the version chain enriched with `download_url` and `page_count` per row, so the picker offers "compare any two versions of THIS drawing". | `compare.read` |
| POST | `/api/v1/compare/diff/` | Compute (and optionally persist) the markup diff between two version ids. Body: `{ base_version_id, compare_version_id, persist, mode, title, notes, pixel }`. Returns `CompareResultResponse` with the `change_summary` shape from 3.3. | `compare.read`, plus `compare.write` only when `persist=true` |
| GET | `/api/v1/compare/sessions/` | List saved compare sessions for `project_id` (+ optional `canonical_name`). | `compare.read` |
| GET | `/api/v1/compare/sessions/{id}/` | Single saved session, with both sides re-resolved to current `download_url`s. | `compare.read` |
| DELETE | `/api/v1/compare/sessions/{id}/` | Delete a saved session (author or project owner). | `compare.write` |
| GET | `/api/v1/documents/{document_id}/versions/{version_id}/download/` | Serve the bytes of a SPECIFIC version of a document, resolved from `oe_file_version.storage_key`. Falls back to `Document.file_path` only when the row is the current row and `storage_key` is NULL (legacy). | `documents.read` |

The last endpoint is the one that unblocks the whole feature. It is added to the existing documents router because it shares the `UPLOAD_BASE` containment logic, the demo-PDF re-anchoring, and the symlink rejection already written in `download_document` (`documents/router.py` lines 1391-1463). It reuses that helper rather than duplicating it.

### 4.2 Request and response shapes

`CompareCandidate` (one row of `GET /compare/candidates/`):

```
{
  "version_id": "uuid",
  "version_number": 3,
  "is_current": true,
  "uploaded_at": "2026-06-01T09:00:00Z",
  "notes": "Issued for construction",
  "file_id": "uuid",
  "file_kind": "document",
  "mime_type": "application/pdf",
  "page_count": 5,
  "download_url": "/api/v1/documents/<file_id>/versions/<version_id>/download/",
  "markup_count": 12
}
```

`CompareResultResponse` (from `POST /compare/diff/` and `GET /compare/sessions/{id}/`):

```
{
  "session_id": "uuid | null",       null when persist=false
  "project_id": "uuid",
  "file_kind": "document",
  "canonical_name": "Level-02-Plan.pdf",
  "base":    { ...CompareCandidate of older side... },
  "compare": { ...CompareCandidate of newer side... },
  "mode": "overlay",
  "change_summary": { ...shape from 3.3... }
}
```

### 4.3 RBAC and project scoping

New permissions registered by the module (mirrors `file_versions/permissions.py`):

```
compare.read   -> Role.VIEWER
compare.write  -> Role.EDITOR
```

Every endpoint resolves the owning `project_id` from the chain row (`FileVersion.project_id`) and calls `verify_project_access(project_id, user_id, session)` exactly as `file_versions/router.py` does (lines 76, 97, 114). A caller cannot diff two version ids from another tenant: the service loads both rows, asserts they share one `project_id`, then runs the access gate once. Cross-version-across-projects is rejected with 422 before any access check, so the error never leaks whether a foreign version id exists. The specific-version download reuses `download_document`'s own `verify_project_access` call.

## 5. Service logic - the connective tissue

This is where the four modules are joined. The flow for `POST /compare/diff/`:

1. Load both `FileVersion` rows by id from the `file_versions` repository (`FileVersionRepository.get_by_id`). 404 if either is missing.
2. Assert `base.project_id == compare.project_id`, `base.file_kind == compare.file_kind`, `base.canonical_name == compare.canonical_name`. Otherwise 422 "versions are not in the same chain". This guarantee is the whole reason the feature is a version compare and not the legacy arbitrary-PDF compare.
3. `verify_project_access(base.project_id, user_id, session)`.
4. Markup diff against the `markups` module. Both version rows have a `file_version_id` that markups point at (`Markup.file_version_id`). The compare repository runs two scoped queries against `oe_markups_markup`:
   - markups where `file_version_id == base_version_id`
   - markups where `file_version_id == compare_version_id`
   Bucketing rule, region-neutral and identity-based:
   - present on compare only -> `added`
   - present on base only -> `removed`
   - a markup is `carried` when a base-side markup has a descendant on the compare side. Carry-over is detected via `Markup.metadata_["supersedes_markup_id"]`, an optional pointer the markup module can set when a reviewer re-draws a note on the new revision. When that pointer is absent we do not guess geometry equality in the core; carried stays empty and every markup falls into added or removed. Geometry-similarity carry-over is a Phase 3 enrichment.
   - Legacy markups with `file_version_id IS NULL` are attributed to the current row (matching the viewer's existing "NULL = current" convention in `markups/models.py` lines 41-47), so they bucket as either added or carried and never vanish.
5. Pixel summary: the client posts `pixel.changed_pct` computed by the existing canvas diff. The server stores it verbatim. The server never rasterises PDFs; that stays in the browser where pdf.js already runs.
6. Page reconciliation: read `page_count` off both rows for the `pages` block.
7. If `persist=true`, write one `CompareSession` row (`compare.write` enforced) with `change_summary` populated, and emit a `documents.activity` row through the existing `record_activity` helper used across the documents module, action `compare_saved`, so the comparison shows up in the document timeline. This is the second cross-module link: a saved compare is visible from the CDE history drawer and the documents activity feed.

The flow for the specific-version download:

1. Load the `FileVersion` row, `verify_project_access` on its `project_id`.
2. If `storage_key` is set, resolve it through the same `UPLOAD_BASE` containment + symlink + existence checks as `download_document`, and stream it with the row's `mime_type`.
3. If `storage_key` is NULL and the row `is_current`, fall back to the document's current `file_path` (legacy rows uploaded before this feature). If NULL and not current, 410 Gone with a clear message "this version predates per-version storage and its file was not retained", because we cannot fabricate bytes we never kept.

The write side - making old bytes retrievable going forward:

`upload_document_revision` (`documents/service.py` lines 524-558) is amended so the per-version path it already writes (`upload_dir / storage_name`, line 513) is recorded on the new chain row instead of being lost. The shared `Document.file_path` still points at the latest for backward compatibility with everything that reads the document directly, but the chain row now also carries `storage_key=str(file_path)`, `mime_type=stored_mime`, and a detected `page_count`. We extend `FileVersionCreate` with three optional fields (`storage_key`, `mime_type`, `page_count`) and `register_new_version` persists them. No other caller of `register_new_version` is forced to supply them (they default to NULL), so the photos, BIM and sheet upload paths keep working unchanged.

For documents whose current bytes already exist but predate this change, a one-time best-effort backfill in the migration is intentionally avoided (we cannot recover bytes that were overwritten). Instead, the current row gets its `storage_key` set lazily the next time the document is read through the compare candidates endpoint, by copying `Document.file_path` and `mime_type` onto the current chain row if they are NULL. That makes the current version always comparable; only truly historical pre-feature versions are unrecoverable, which is the honest outcome.

### 5.1 CDE link

The `cde` module's `DocumentRevision` already stores `storage_key` per revision and a `document_id` cross-link (`cde/models.py` lines 75-81). When a comparison is opened from a CDE container, the candidates endpoint accepts the document `file_id` and returns the same chain; the CDE revision codes (for example `P.01`, `C.02`) are surfaced in the picker by joining `oe_cde_revision.document_id == file_id` and matching `revision_number` to `version_number` when present. This is read-only enrichment: CDE supplies human revision labels, `file_versions` supplies the bytes. No CDE write happens from compare.

## 6. Frontend

Feature folder: extend the existing `frontend/src/features/markups/` viewer and add a thin compare-domain folder `frontend/src/features/compare/` for the API client, hooks and the version picker. The heavy canvas work already lives in `PdfCompare.tsx` and is reused as-is.

### 6.1 Components and screens

| File | Role |
|------|------|
| `features/compare/api.ts` | `getCandidates(fileId, kind)`, `computeDiff(body)`, `listSessions(projectId)`, `getSession(id)`, `deleteSession(id)`. Uses `apiGet`/`apiPost` from `@/shared/lib/api`. |
| `features/compare/hooks.ts` | React Query hooks `useCompareCandidates`, `useComputeDiff`, `useCompareSessions`, mirroring `file-versions/hooks.ts`. |
| `features/compare/types.ts` | Wire types mirroring the backend schemas (CompareCandidate, CompareResultResponse, change_summary). |
| `features/compare/VersionPickerBar.tsx` | Replaces the two free-text PDF dropdowns at the top of `PdfCompare.tsx` with two version selectors driven by `useCompareCandidates`. Each option shows `V03 - Issued for construction - 2026-06-01`. Default selection: base = previous version, compare = current. |
| `features/compare/MarkupDiffOverlay.tsx` | Renders the markup diff on top of the compare canvas. Green outline = added, red dashed = removed (ghosted on the older side), grey = carried. Driven by `change_summary.markups`. Reuses the geometry-to-canvas math already used by `InlinePdfAnnotator`. |
| `features/compare/MarkupDiffList.tsx` | Right-hand drawer listing added / removed / carried markups with counts, each row click-to-locate (sets page + pans to geometry). |
| `features/markups/PdfCompare.tsx` (edited) | Keep all three render modes. Swap the document pickers for `VersionPickerBar`, swap `loadPdfFromDocId` to load from the specific-version download URL, add a "Markup diff" toggle that mounts `MarkupDiffOverlay` + `MarkupDiffList`, add a "Save comparison" action that calls `computeDiff` with `persist=true`. |

### 6.2 State

- Local component state for `mode`, `zoom`, `page`, `overlayOpacity`, pan (already present in `PdfCompare.tsx`).
- `selectedBaseVersionId` / `selectedCompareVersionId` replace `selectedDocAId` / `selectedDocBId`. Seeded from query params `?fileId=&kind=&base=&compare=` so deep links from the file manager and CDE work.
- Server state via React Query: candidates, diff result, sessions. No Zustand store needed; the active project comes from `useProjectContextStore` exactly as the current page does (`PdfCompare.tsx` line 728).

### 6.3 How it surfaces to the user

1. From the file preview pane's existing `RevisionsPanel` (`features/file-versions/RevisionsPanel.tsx`), add a "Compare" affordance next to each historical row that deep-links to `/markups/compare?fileId={id}&kind=document&base={thisVersion}&compare={current}`.
2. From the CDE history drawer (`features/cde/CDEHistoryDrawer.tsx`), a "Compare revisions" button on any container with two or more revisions opens the same route preselected to the chosen pair.
3. From the takeoff and markups viewers, a toolbar button "Compare versions" opens the current drawing's chain.
4. The route itself (`/markups/compare`) stays, now version-aware. Saved comparisons appear under the document's activity timeline and are reachable from `GET /compare/sessions/`.

All new strings go through `react-i18next` with `defaultValue`, matching the existing `pdf_compare.*` keys already in `PdfCompare.tsx`, and are picked up by the i18n sweep for the other 26 locales.

## 7. Reuse - confirmed infra to build on

| Existing asset | Reused for |
|----------------|-----------|
| `FileVersion` model + `FileVersionRepository` (`list_chain`, `get_current`, `list_for_file_id`, `get_by_id`) | Chain resolution for candidates and diff; no new chain query logic. |
| `FileVersionService.register_new_version` | Extended with three optional fields to persist per-version storage; no fork. |
| `Markup.file_version_id` + `MarkupRepository.list_for_project` | The markup diff buckets without any new column on markups. |
| `documents/router.py` `download_document` containment + symlink + demo re-anchor logic | The specific-version download reuses it instead of reimplementing path safety. |
| `record_activity` (documents) | Compare-saved entries in the document timeline. |
| `verify_project_access`, `RequirePermission`, `CurrentUserId`, `SessionDep` (`app/dependencies.py`) | Identical RBAC and scoping pattern as every module router. |
| `PdfCompare.tsx` (overlay/diff/sidebyside canvas, pan hook, pdf.js worker reuse) | The entire pixel-rendering layer. We only change its data source and add the markup overlay. |
| `RevisionsPanel`, `VersionBadge`, `VersionDropdown`, `StaleVersionPill` (`features/file-versions`) | Entry points and version labelling on the frontend. |
| `cde/models.py` `DocumentRevision.storage_key` / `.document_id` | Revision-code labels in the picker. |
| `app.database.GUID` / `Base` | Standard id and timestamp columns. |

## 8. Phasing

Region-neutral core first, then fidelity. No stubs at any phase: every endpoint and screen listed in a phase is fully working when that phase lands.

### Phase 1 - Make versions retrievable and version-aware compare (MVP, end to end)

- Migration `v3151`: add `storage_key`, `mime_type`, `page_count` to `oe_file_version`; create `oe_compare_session`.
- Extend `FileVersionCreate` and `register_new_version` to persist the three new fields (defaults NULL, no caller breakage).
- Amend `upload_document_revision` to record the per-version path it already writes onto the new chain row.
- New `documents/.../versions/{version_id}/download/` endpoint reusing existing path-safety logic, with the legacy fallback and 410 for unrecoverable historical bytes.
- New `compare` module: `candidates`, `diff` (markup buckets by `file_version_id`, identity carry-over only), `sessions` CRUD; permissions `compare.read`/`compare.write`.
- Frontend: `VersionPickerBar`, switch `PdfCompare.tsx` to load specific-version bytes, `MarkupDiffOverlay` + `MarkupDiffList`, "Save comparison". Deep links from `RevisionsPanel`.
- Lazy backfill of the current row's `storage_key` from `Document.file_path` on first candidates read.

Effort: 6 days.

### Phase 2 - CDE integration and saved-comparison surfacing

- Candidates endpoint joins `oe_cde_revision` to label rows with revision codes.
- "Compare revisions" entry in `CDEHistoryDrawer`.
- Compare-saved entries written to the documents activity timeline and surfaced in the CDE history drawer.
- Session list view in the markups feature.

Effort: 3 days.

### Phase 3 - Higher-fidelity diff

- Geometry-similarity carry-over detection in the markup diff (centroid + bbox overlap threshold) so re-drawn notes are recognised as carried without the explicit `supersedes_markup_id` pointer.
- Server-assisted page alignment hint when page counts differ (map base page to the nearest compare page by title-block OCR text already available from the takeoff sheet split, `oe_documents_sheet.sheet_number`).
- Export the comparison as a flattened PDF (base + diff overlay) using the existing report rendering path.

Effort: 5 days.

### Phase 4 - Partner-pack extension points

The core stays region-neutral. Partner packs hook in through `CompareSession.metadata_` and a small registry, mirroring how validation rule packs already register:

- US AIA G702/G703: a pack reads the markup diff and the linked BOQ positions (markups already carry `linked_boq_position_id`, `markups/models.py` line 79) to flag scope additions between revisions for a continuation-sheet delta.
- DACH DIN: a pack maps changed regions to DIN 276 cost groups via the document's classification metadata.
- UK JCT: a pack annotates the comparison with a variation reference when a saved compare is linked to a change order.

Each pack provides a read-only summariser that consumes `change_summary` and returns extra rows for the diff drawer. No core change per pack.

Effort: 3 days.

## 9. Risks and edge cases

| Risk / edge case | Handling |
|------------------|----------|
| Historical versions uploaded before this feature have no retained bytes | Specific-version download returns 410 with a clear message for non-current legacy rows; current row backfills from `file_path`. We never fabricate bytes. |
| Two versions have different page counts | `page_count` on each row drives a picker warning; the viewer already clamps navigation to the shared range and flags the mismatch (`PdfCompare.tsx` lines 758-770, 1036-1048). |
| Non-PDF documents (DWG, RVT, IFC) | Compare candidates only offer pixel/markup compare for PDF and raster `mime_type`s. CAD and BIM go through DDC cad2data canonical format and are out of scope for pixel overlay; the picker disables non-rasterisable kinds with a tooltip. No IfcOpenShell, no native IFC parsing. |
| Large PDFs rasterised in the browser | Rendering stays client-side as today; the offscreen-canvas diff is already memory-bounded per page. The server never rasterises, so backend memory is unaffected. |
| Markup `file_version_id` is NULL on legacy markups | Attributed to the current row per the existing viewer convention, so they bucket as added or carried, never lost. |
| Cross-tenant version ids in a diff request | Rejected 422 before access check when the two rows are not in one chain; single `verify_project_access` after. |
| Restore changes which row is current mid-compare | The compare operates on explicit version ids, not "current", so a concurrent restore does not change what a given saved session points at. The candidates list reflects the new current on next fetch. |
| Storage path moved between releases | The specific-version download reuses the demo re-anchor and containment logic already hardened in `download_document`; real uploads outside `UPLOAD_BASE` degrade to 404, not 403. |
| Per-version storage doubles disk use | Each revision already wrote its own file before; we now keep the old one instead of orphaning it. This is intended; file-trash and retention policies (existing `file_trash` module) govern cleanup. |

## 10. Test plan

### Backend (pytest, per-module temp sqlite)

New file `backend/tests/unit/test_compare.py` following `test_file_versions.py`: per-test in-memory engine, `Base.metadata.create_all`, seed a project and user. The session-level temp sqlite is already set in `tests/conftest.py` before app import.

- `register_new_version` persists `storage_key`, `mime_type`, `page_count` and leaves them NULL when omitted (existing photo/sheet callers unaffected).
- Compare service rejects two version ids from different chains with 422.
- Markup diff buckets correctly: seed base-version and compare-version markups via `MarkupsService`, assert added/removed/carried counts; assert NULL `file_version_id` markup is attributed to current.
- Saved session round-trips: `persist=true` writes a row with the right `change_summary`; `GET /sessions/{id}` re-resolves both sides.
- `compare.write` is required for persist and for delete; `compare.read` suffices for diff and candidates.

New file `backend/tests/integration/test_compare_download.py` following `test_markups_persistence.py` (real `create_app()` + `AsyncClient`):

- Register admin, create project, upload a document, upload a revision, then `GET /documents/{id}/versions/{base}/download/` returns the OLD bytes and `.../{current}/download/` returns the NEW bytes (the core blocker is fixed end to end).
- Cross-tenant: user B gets 404 on user A's version download.
- Legacy non-current row with NULL `storage_key` returns 410.

### Frontend (vitest)

`features/compare/__tests__/`:

- `useCompareCandidates` maps chain rows to options with download URLs.
- Markup diff buckets render the right counts and colours in `MarkupDiffList`.
- `VersionPickerBar` defaults base to previous and compare to current; swap works.
- `PdfCompare` still mounts all three modes after the data-source swap (mock pdf.js as the existing markups tests do).

### Manual browser verification on :8000

1. Start the app, open a project with a multi-revision PDF.
2. From the file preview Revisions panel, click Compare on an older revision -> lands on `/markups/compare` preselected, both versions render.
3. Overlay mode: slide B opacity, confirm onion-skin. Diff mode: confirm changed-percentage badge. Side-by-side: confirm synced pan and zoom.
4. Toggle Markup diff: confirm added markups outlined green on the new side, removed ghosted red on the old side, carried grey, list counts match.
5. Save comparison -> confirm it appears in the document activity timeline and under `GET /compare/sessions/`.
6. Open the saved session link in a fresh tab -> both sides re-resolve and render.
7. CDE: open a container with two revisions, Compare revisions, confirm revision-code labels in the picker.
8. Negative: a DWG document offers no pixel compare (disabled with tooltip); a pre-feature historical version shows the 410 message gracefully rather than a broken canvas.

## 11. File and module map

| Path | New or edited |
|------|---------------|
| `backend/alembic/versions/v3151_drawing_version_compare.py` | new |
| `backend/app/modules/compare/manifest.py` | new |
| `backend/app/modules/compare/models.py` (`CompareSession`) | new |
| `backend/app/modules/compare/schemas.py` | new |
| `backend/app/modules/compare/repository.py` | new |
| `backend/app/modules/compare/service.py` | new |
| `backend/app/modules/compare/router.py` | new |
| `backend/app/modules/compare/permissions.py` | new |
| `backend/app/modules/file_versions/models.py` | edited (3 columns) |
| `backend/app/modules/file_versions/schemas.py` | edited (3 optional fields) |
| `backend/app/modules/file_versions/service.py` | edited (persist new fields) |
| `backend/app/modules/documents/service.py` | edited (snapshot per-version path) |
| `backend/app/modules/documents/router.py` | edited (specific-version download) |
| `backend/tests/unit/test_compare.py` | new |
| `backend/tests/integration/test_compare_download.py` | new |
| `frontend/src/features/compare/{api,hooks,types}.ts` | new |
| `frontend/src/features/compare/{VersionPickerBar,MarkupDiffOverlay,MarkupDiffList}.tsx` | new |
| `frontend/src/features/markups/PdfCompare.tsx` | edited (version-aware data source + markup diff) |
| `frontend/src/features/file-versions/RevisionsPanel.tsx` | edited (Compare deep link) |
| `frontend/src/features/cde/CDEHistoryDrawer.tsx` | edited (Compare revisions entry) |
| `frontend/src/features/compare/__tests__/*` | new |
