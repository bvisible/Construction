# Item 16 - Semantic AI assistant over project documents

## Current state (verified against code)

**What is shipped:**
- Vector index infrastructure (backend/app/core/vector_index.py, vector.py, vector_routes.py) with support for 9 collections: BOQ positions, documents, tasks, risks, BIM elements, validation, chat, requirements, and cost items
- Vector adapters for 9 modules (boq, documents, tasks, risks, bim_hub, validation, erp_chat, requirements, costs) implementing the EmbeddingAdapter protocol
- Unified search service (backend/app/modules/search/service.py) with Reciprocal Rank Fusion over all collections + SQL fallback (ILIKE substring matching)
- Global search modal frontend (frontend/src/features/search/GlobalSearchModal.tsx) with Cmd+K keyboard shortcut, faceted hits by collection type, and deep-link navigation
- ERP Chat module with 13+ tool handlers (handle_search_boq_positions, handle_search_documents, handle_search_tasks, handle_search_risks, handle_search_bim_elements, handle_search_anything, etc.)
- Chat vector adapter (erp_chat/vector_adapter.py) that indexes user/assistant messages into oe_chat collection
- Three project-document modules fully built and operational:
  - RFI (Request for Information): models.py has subject, question, official_response, linked_drawing_ids; router.py has CRUD endpoints
  - Submittals: models.py has title, spec_section, submittal_type, status, linked_boq_item_ids; router.py has CRUD endpoints
  - Correspondence: models.py has subject, direction, correspondence_type, linked_document_ids; router.py has CRUD endpoints
- Search API layer (frontend/src/features/search/api.ts) with unifiedSearch(), fetchSearchStatus(), hitToHref() for routing hits to native pages
- Event bus infrastructure (backend/app/core/events.py) for publishing and subscribing to module events

**What is missing (gaps in item 16 digest):**
1. Vector adapters for RFI, submittals, and correspondence modules DO NOT EXIST
2. Collection constants (COLLECTION_RFI, COLLECTION_SUBMITTALS, COLLECTION_CORRESPONDENCE) NOT defined in vector_index.py
3. RFI, submittals, correspondence NOT registered in ALL_COLLECTIONS tuple in vector_index.py
4. Event handlers in rfi/events.py, submittals/events.py, correspondence/events.py to index on create/update/delete DO NOT EXIST
5. Search tool handlers (handle_search_rfis, handle_search_submittals, handle_search_correspondence) NOT in erp_chat/tools.py
6. Frontend search modal does NOT render RFI, Submittal, Correspondence facet pills or hit types
7. Frontend api.ts hitToHref() has no cases for oe_rfi, oe_submittals, oe_correspondence collections
8. Frontend api.ts collectionLabel() has no cases for the three new collections

**Code locations (verified):**
- Modules: backend/app/modules/rfi/, submittals/, correspondence/ with complete models + routers
- Vector infrastructure: backend/app/core/vector_index.py (constants + registry), vector.py (embedding engine), vector_routes.py (admin endpoints)
- Search: backend/app/modules/search/service.py (unified search + SQL fallback), frontend/src/features/search/
- Chat tools: backend/app/modules/erp_chat/tools.py (13 handler functions), erp_chat/vector_adapter.py, erp_chat/prompts.py
- Event bus: backend/app/core/events.py (EventBus class and publish/subscribe primitives)

## Scope of this increment (demonstrable + testable)

**Bounded slice: enable semantic search + chat tools for RFI, submittals, correspondence**

This increment plugs the three existing project-document modules into the semantic search + chat tool pipeline. No migrations, no new tables, no UI redesigns — only vector adapters, event wiring, and backend tools.

**Demonstrable outcomes:**
1. User types "tell me about structural RFI issues" in floating chat → tool calls search_rfis() → returns RFI hits with semantic matching
2. User opens Cmd+K global search modal → searches "waterproofing concerns" → results show RFI + Submittal + Correspondence hits
3. User clicks an RFI hit → deep-links to /projects/{id}/rfi/{rfiId} detail page
4. Backend publishes rfi.created, rfi.updated, rfi.deleted events → adapters auto-index/reindex/delete vectors
5. Frontend Cmd+K modal renders new facet pills for RFI, Submittals, Correspondence with colors

**Out of scope:**
- PDF content extraction, cross-project search, advanced grouping by discipline
- RFI history timeline, AI insights (later waves)

## Backend changes (files, functions, endpoints, models/DDL)

### New files

**backend/app/modules/rfi/vector_adapter.py**
Adapts RFI rows to embeddings. Concatenates subject + question + response.

**backend/app/modules/submittals/vector_adapter.py**
Adapts Submittal rows. Embeds title + spec section.

**backend/app/modules/correspondence/vector_adapter.py**
Adapts Correspondence rows. Embeds subject + direction + type + notes.

### Modified files

**backend/app/core/vector_index.py**
- Add COLLECTION_RFI = "oe_rfi_rfis"
- Add COLLECTION_SUBMITTALS = "oe_submittals_submittals"
- Add COLLECTION_CORRESPONDENCE = "oe_correspondence_correspondence"
- Extend ALL_COLLECTIONS tuple
- Extend COLLECTION_LABELS dict

**backend/app/modules/rfi/events.py**
Event handlers on_rfi_created, on_rfi_updated, on_rfi_deleted
Register handlers in module init

**backend/app/modules/submittals/events.py**
Same pattern for submittals

**backend/app/modules/correspondence/events.py**
Same pattern for correspondence

**backend/app/modules/rfi/router.py**
Emit rfi.created/updated/deleted events in CRUD handlers

**backend/app/modules/submittals/router.py**
Emit submittal.created/updated/deleted events

**backend/app/modules/correspondence/router.py**
Emit correspondence.created/updated/deleted events

**backend/app/modules/erp_chat/tools.py**
- Add handle_search_rfis(session, args, user_id)
- Add handle_search_submittals(session, args, user_id)
- Add handle_search_correspondence(session, args, user_id)
- Register in TOOLS registry

**backend/app/modules/search/service.py**
Add short-name aliases in _SHORT_NAME_ALIASES dict

### Endpoints

No new REST endpoints. Tools invoked via existing POST /v1/erp-chat/sessions/{id}/messages/ 

### Models / DDL

**None.** Tables exist. Vector indexes stored in LanceDB (external).

## Frontend changes (route, components, UX)

### Modified files

**frontend/src/features/search/api.ts**
- Add hitToHref() cases for oe_rfi_rfis, oe_submittals_submittals, oe_correspondence_correspondence
- Add collectionLabel() cases

**frontend/src/features/search/GlobalSearchModal.tsx**
- Add FACET_COLOR entries for cyan, indigo, teal

## Migration

**None.** Tables exist, vector indexes external to PostgreSQL.

## File touch list

**Backend (12 files):**
1. backend/app/core/vector_index.py
2. backend/app/modules/rfi/vector_adapter.py (new)
3. backend/app/modules/rfi/events.py (new)
4. backend/app/modules/rfi/router.py
5. backend/app/modules/submittals/vector_adapter.py (new)
6. backend/app/modules/submittals/events.py (new)
7. backend/app/modules/submittals/router.py
8. backend/app/modules/correspondence/vector_adapter.py (new)
9. backend/app/modules/correspondence/events.py (new)
10. backend/app/modules/correspondence/router.py
11. backend/app/modules/erp_chat/tools.py
12. backend/app/modules/search/service.py

**Frontend (2 files):**
1. frontend/src/features/search/api.ts
2. frontend/src/features/search/GlobalSearchModal.tsx

## Conflicts / sequencing

No conflicts. Purely additive to stable infrastructure. Depends on W1 (event bus) + W2 (vector index).

## Test plan (browser + unit)

**Unit tests:**
- Test adapter to_text/to_payload for each module
- Test event handlers publish and index vectors
- Test chat tools with access control
- Test reindex on update, delete on remove

**Browser tests:**
1. Cmd+K search "structural" → RFI hits appear with RFI facet pill
2. Click RFI hit → navigate to /projects/{id}/rfi/{rfiId} detail page
3. Chat: "show me structural RFIs" → tool invoked, hits displayed
4. Create submittal, search "concrete" → submittal hit appears
5. Delete RFI, search again → hit gone (allow 2s for async)
6. Mobile 375px → facet pills wrap naturally

**Screenshots show:**
- Cmd+K with RFI + Submittals + Correspondence facet pills
- Search results grouped by collection
- Click flow to detail pages (no 404)
- Chat with tool results
- Zero console errors

## Risks

**Technical:** vector store unavailable (SQL fallback works), stale vectors on update (event handlers retry), event registration timing (ensure at startup)

**Product:** users don't know RFI searchable (tooltip), facet clutter (CSS wrapping), tool discovery (update chat prompt)

**Operational:** bulk indexing (lazy on first search), search latency (10-20ms per collection, stay < 200ms total)

## Implementation checklist

- [ ] backend/app/modules/rfi/vector_adapter.py (new)
- [ ] backend/app/modules/submittals/vector_adapter.py (new)
- [ ] backend/app/modules/correspondence/vector_adapter.py (new)
- [ ] backend/app/core/vector_index.py (3 constants + ALL_COLLECTIONS + COLLECTION_LABELS)
- [ ] backend/app/modules/rfi/events.py (event handlers + register)
- [ ] backend/app/modules/submittals/events.py
- [ ] backend/app/modules/correspondence/events.py
- [ ] backend/app/modules/rfi/router.py (emit events)
- [ ] backend/app/modules/submittals/router.py (emit events)
- [ ] backend/app/modules/correspondence/router.py (emit events)
- [ ] backend/app/modules/erp_chat/tools.py (3 search handlers + register)
- [ ] backend/app/modules/search/service.py (short-name aliases)
- [ ] frontend/src/features/search/api.ts (hitToHref + collectionLabel)
- [ ] frontend/src/features/search/GlobalSearchModal.tsx (FACET_COLOR)
- [ ] Unit tests for adapters, events, tools
- [ ] Browser tests: Cmd+K, chat, detail page navigation
- [ ] Mobile viewport testing (375px)
- [ ] i18n keys in en.ts