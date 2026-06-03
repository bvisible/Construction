# Deep improvement program, June 2026

Two multi-agent discovery passes ran over the whole codebase. Raw structured
output is archived next to this file:

- `01_sections_competitive_top30.json` - per-section logic and inter-module
  coordination analysis for the nine sidebar sections, a hacks/stubs hunt, a
  competitive gap analysis against ten market products, and a ranked top-30 of
  missing features.
- `02_per_module_audit.json` - per-module correctness, data-flow, event-wiring
  and transaction-integrity audit across all backend modules. 96 findings.

## Highest-value coordination fixes (verified in code)

- Clash and validation results publish no events, and notifications subscribe
  to none of clash, document or validation. A high-severity clash is silent
  until someone opens the page. The event bus and subscriber pattern already
  exist.
- `safety/service.py` hardcodes LTIFR and TRIR to `None` and never computes
  them, although the schema and man-hours convention are in place.
- The schedule stores activity dependencies twice (Activity.dependencies JSON
  and the ScheduleRelationship table); PATCH writes one, the relationship
  endpoint the other, and CPM dedups both, so a deleted edge can still block.
- `oe_tendering` and `oe_bid_management` both publish package.awarded and both
  trigger procurement auto-PO, so a project using both can double-create
  contracts and POs.
- `collaboration_locks.sweep_expired` builds its stale set from a query whose
  filter is mutually exclusive with the keep condition, so it is always empty
  and COLLAB_LOCK_EXPIRED never fires.
- `file_references` and `file_search` have no subscriber for
  `documents.document.deleted`, so both leave orphaned rows after a delete.

## High-severity correctness and security (verified)

- `enterprise_workflows` router has no permission gates and no project access
  check on any state-changing endpoint.
- `file_comments` PATCH verifies project access after mutating; DELETE has no
  check at all.
- `correspondence` GET list and detail have no `correspondence.read` gate.
- `full_evm` returns 403 instead of 404 on cross-project access, leaking
  project existence (R7 standard is 404).
- `backup` restore in replace mode can persist a partial, corrupt database on a
  per-table flush failure.
- `costmodel` dashboard and `integrations` webhook paths have money-currency
  and commit-boundary defects.

## Live install bugs found during walkthrough (2026-06-02)

These are being tracked and fixed alongside the audit:

- `/takeoff` PDF worker chunk 404 on the built app (`pdf.worker.min-*.mjs`
  fails to load from `/assets`).
- `/bim` seeded showcase models are marked ready but their geometry files are
  not on disk, so the viewer shows a 404.
- BIM converters panel: the close (X) button does not dismiss it, and an
  in-progress converter update shows no progress bar.
- README and marketing screenshots were captured with the product-tour dimming
  overlay visible.

## Delivery

Work is being implemented in module-partitioned waves so no two changes touch
the same file at once. Backend correctness and coordination fixes run as
isolated per-module changes; frontend fixes are scoped to one feature folder
each; every change is verified before it lands.
