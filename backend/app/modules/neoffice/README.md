<!-- NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OpenConstructionERP. -->

# Neoffice Extensions module (`oe_neoffice`)

Neoservice cross-cutting extensions that extend the Neoffice backend without
belonging to a regional pack.

## Scope

| Feature | Phase | Endpoint |
|---|---|---|
| **RoomPlan import** (Apple LiDAR → BIMModel) | MVP | `POST /api/v1/neoffice/bim/import-roomplan/` |
| RoomPlan export → DXF (2D floor plan) | Phase 2 | `POST /api/v1/neoffice/bim/export-dxf/` |
| RoomPlan export → IFC (IFC4 model) | Phase 2 | `POST /api/v1/neoffice/bim/export-ifc/` |
| Future mobile-only endpoints | TBD | `/api/v1/neoffice/mobile/...` |

**Not in scope** (kept elsewhere):
- Regional standards (CFC, eBKP, NPK, TVA) → `swiss_pack/`
- Generic BIM CRUD (upload IFC/DWG, list/delete models) → `bim_hub/` (upstream)
- Core auth, projects, BoQ — handled by upstream modules

## Why a dedicated Neoservice module instead of patching upstream

1. **Zero merge conflicts**: 100% new code under `app/modules/neoffice/`, never
   touched by upstream rebases.
2. **Brand alignment**: hosts everything we sell as "Neoffice" (RoomPlan bridge,
   mobile APIs, NORA glue) under one namespace, separate from regional packs.
3. **Reusable**: a French/German deployment can disable `swiss_pack` while
   keeping `neoffice` enabled — no coupling.

## URL convention

Module loader mounts on the kebab-case `dir_name`:

- Backend direct: `POST /api/v1/neoffice/bim/import-roomplan/`
- Via Neoconstruction Frappe proxy: `POST /neoconstruction/api/v1/neoffice/bim/import-roomplan/`

The proxy injects the OCE JWT server-side using the Frappe session cookie or
`Authorization: token <api_key>:<api_secret>` — mobile clients only need the
Frappe credentials.

## Files

```
neoffice/
├── __init__.py              ← package marker + NEOFFICE FILE header
├── manifest.py              ← ModuleManifest(name="oe_neoffice")
├── router.py                ← APIRouter, includes RequirePermission deps
├── schemas.py               ← Pydantic — RoomPlanImportRequest, etc.
├── roomplan_importer.py     ← (TODO) parses CapturedRoom JSON → BIMElement[]
└── README.md                ← this file
```

## Reference docs

- Architecture + RoomPlan mapping: `Neoffice/Neoconstruction/34-Module-Neoffice-Backend.md`
  in the Obsidian vault.
- RoomPlan format reference:
  <https://developer.apple.com/documentation/roomplan/capturedroom>
- BIMElement schema (upstream): `backend/app/modules/bim_hub/models.py:80-164`
- Module loader convention: `backend/app/core/module_loader.py:170-225`
