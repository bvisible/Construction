# Item 29 - No-code agent builder for workflow automation

## Current state (verified against code)

As of 2026-06-04, the OpenConstructionERP codebase has a functional custom-agent builder in place, but is missing critical workflow-automation features (scheduling, tool access, and auto-action integration).

### What exists:

1. **CustomAgent ORM model** (ackend/app/modules/ai_agents/models.py)
   - Table: oe_ai_agents_custom (user_id, display_name, tagline, description, system_prompt, category, icon, example_prompts, guided)
   - Creator-scoped ownership (only creator can edit/delete)
   - Guided-builder spec stored as JSON for re-hydration on edit

2. **Guided builder frontend** (rontend/src/features/ai-agents/components/CustomAgentBuilder.tsx)
   - Form collects role, goal, audience, output_format, extra_guidance
   - Icon picker (20 icons) and category selector (6 categories)
   - Example prompts text area
   - Advanced toggle for raw prompt escape hatch
   - Modal UX with validation (name + goal/prompt required)

3. **CustomAgentBuilder schema** (ackend/app/modules/ai_agents/schemas.py)
   - GuidedAgentSpec (role, goal, audience, output_format, extra_guidance)
   - CustomAgentCreateRequest and CustomAgentUpdateRequest
   - CustomAgentResponse with all fields

4. **Backend custom-agent CRUD** (ackend/app/modules/ai_agents/router.py)
   - POST /custom/ create, GET /custom/ list, GET /custom/{id} fetch, PUT /custom/{id} update, DELETE /custom/{id}
   - All routes permission-gated on i_agents.run

5. **Agent run infrastructure** (ackend/app/modules/ai_agents/router.py + service.py)
   - POST /runs/ accepts agent_name, user_input, project_id, idempotency_key
   - Background task execution via FastAPI BackgroundTasks (in-process, non-persistent)
   - Run state: running → completed/failed, with steps timeline (thought/tool_call/observation/answer/error)
   - Custom agents enforced to have llowed_tools=[] (prompt-only, no tool execution)

6. **Agent catalogue** (outer.py)
   - GET /agents/ lists built-ins + custom agents flagged with is_custom and custom_id
   - Each agent has llowed_tools (empty for custom)

### What is broken or missing:

1. **NO scheduling/triggers** - Custom agents run only on manual user invocation
   - Missing: Cron-based scheduling (e.g., "daily at 9am")
   - Missing: Event triggers (e.g., "when RFI created")
   - Missing: Webhook endpoints to trigger runs externally
   - Missing: APScheduler or similar persistent scheduler integration

2. **NO tool access for custom agents** - All custom agents are prompt-only
   - Missing: Tool picker UI in builder (Advanced section checkbox list)
   - Missing: llowed_tools field in CustomAgent model to store user's selection
   - Missing: Permissions validation when agent runs (each tool has required permission, e.g., oq.write for create_position)
   - Missing: Update to custom_agent_to_runtime() to populate allowed_tools from DB

3. **NO workflow action buttons** - Runs display final output but no auto-apply affordances
   - Missing: "Apply to BOQ" button when agent output is structured BOQ position JSON
   - Missing: "Approve and post" button for approval_routes integration
   - Missing: Validation that output is safe to auto-apply (has required fields)

4. **NO monitoring dashboard** - No visibility into scheduled run history
   - Missing: Scheduled runs dashboard (when they fired, status, output)
   - Missing: Failure notifications (email/in-app when scheduled run fails)
   - Missing: Audit log of automated actions (who/what/when)

5. **Frontend missing Schedule/Tool tabs** - Builder is fast for basic agents but lacks advanced sections
   - Missing: "Schedule" tab in CustomAgentBuilder modal
   - Missing: "Tools" tab with checkboxes for available tools
   - Missing: "Run history" section showing scheduled runs + apply buttons

6. **No agent-run linking** - Run output not tied back to agent that created it
   - AgentRun.agent_name exists but no easy way to fetch "all scheduled runs for agent X"
   - No way to see which runs are from scheduled triggers vs manual

## Scope of this increment

Implements **trigger/schedule + tool-access foundations** for custom agents so they can auto-run on events/cron and call tools with user permission. **Does NOT** implement approval_routes integration or monitoring dashboard yet (scope reduction for parallel implementation).

### Demonstrable outcomes:

1. **Scheduling**: Custom agent builder has "Schedule" tab; user can set cron (e.g., "daily at 8am")
2. **Tool picker**: Advanced section shows checkboxes for available tools; selected tools stored in DB
3. **Tool execution**: When agent runs, it can use selected tools (subject to user's permissions)
4. **Scheduler service**: Background cron job fires at configured times; spawns agent runs
5. **Apply buttons**: When run completes, output shows "Apply" buttons if structured JSON
6. **Frontend**: All new UI surfaces are present and functional; no stub endpoints

### Out of scope for this increment:

- Approval_routes integration (auto-create approval when action applied)
- Failure notifications/monitoring dashboard (future item)
- Audit log of automated actions (part of larger audit overhaul)
- Webhook-triggered runs (future; requires IP allowlist + signature verification)
- Multi-tenant scheduler coordination (single-process OK for now)

## Backend changes

### Files to create:

1. **backend/app/modules/ai_agents/scheduler.py** (NEW ~300 lines)
   - AgentSchedule dataclass: agent_id, cron_expr, enabled, next_run_at
   - SchedulerService class:
     - create_schedule(agent_id, cron_expr, user_id) → stores cron in CustomAgent.metadata.cron
     - get_schedules(user_id) → fetch all user's scheduled agents
     - ire_due_runs() → check next_run_at, spawn runs for overdue agents, update next_run_at
   - Uses croniter library (popular, pure Python, no external service needed)
   - Stores next_run_at in CustomAgent metadata (JSON column, no migration)

2. **backend/app/modules/ai_agents/triggers.py** (NEW ~200 lines)
   - Event handler registry: map event names to agent triggers
   - egister_trigger(agent_id, trigger_name, user_id) → store in CustomAgent.metadata.triggers
   - Example triggers (WIP, not all implemented yet):
     - fi_created → when RFI created, fire agent with RFI context
     - document_uploaded → when doc uploaded, fire agent
     - ariance_recorded → when schedule variance recorded
   - Deferred: actual event subscription wiring (done in Wave 5/6)

3. **backend/app/modules/ai_agents/base.py** (MODIFY)
   - Agent class: add optional llowed_tools: list[str] field (default: [])
   - Update docstring to clarify custom agents can now have tools

### Files to modify:

1. **backend/app/modules/ai_agents/models.py** (MODIFY ~50 lines)
   - **CustomAgent model**: Add metadata: JSON column (default: {}) to store:
     - {"cron": "0 9 * * *", "triggers": ["rfi_created"], "allowed_tools": ["search_costs", "create_position"]}
   - No migration needed (add with server_default={})

2. **backend/app/modules/ai_agents/service.py** (MODIFY ~300 lines)
   - Import croniter for cron validation
   - custom_agent_to_runtime(): Read metadata.allowed_tools and populate Agent.allowed_tools
   - Add alidate_cron(expr: str) -> bool helper
   - Add set_schedule(agent_id, cron_expr, user_id) method
   - Add set_tools(agent_id, tool_names, user_id) method with permission validation:
     - For each tool, check user has required permission (e.g., oq.write for create_position)
     - Raise 403 if user lacks permission for any selected tool
   - Add get_agent_metadata(agent_id, user_id) -> dict to fetch current schedule/tools/triggers

3. **backend/app/modules/ai_agents/schemas.py** (MODIFY ~100 lines)
   - New request schemas:
     - SetScheduleRequest(agent_id: UUID, cron_expr: str) - with pattern validation
     - SetToolsRequest(agent_id: UUID, allowed_tools: list[str]) - with enum validation
   - Response schema:
     - AgentMetadataResponse(cron: str | None, triggers: list[str], allowed_tools: list[str], next_run_at: str | None)
   - Update CustomAgentResponse to optionally include metadata

4. **backend/app/modules/ai_agents/router.py** (MODIFY ~200 lines)
   - New endpoints:
     - POST /custom/{agent_id}/schedule → set_schedule_endpoint(agent_id, request)
     - GET /custom/{agent_id}/schedule → get_schedule_endpoint(agent_id)
     - DELETE /custom/{agent_id}/schedule → delete_schedule_endpoint(agent_id)
     - POST /custom/{agent_id}/tools → set_tools_endpoint(agent_id, request, user_id, session)
     - GET /custom/{agent_id}/tools → get_tools_endpoint(agent_id) [returns available + selected]
   - Update POST /runs/ to accept optional uto_action field (for apply-to-BOQ button)

5. **backend/app/modules/ai_agents/repository.py** (MODIFY ~100 lines)
   - Add update_metadata(agent_id, metadata_dict) method
   - Add query_due_schedules() → SELECT agents WHERE metadata->>'cron' IS NOT NULL AND next_run_at <= NOW()

6. **backend/app/core/scheduler.py** (NEW ~150 lines)
   - Centralized cron scheduler service
   - start_scheduler() → spawn asyncio task that polls every 60s for due runs
   - On app startup, call start_scheduler()
   - Uses croniter for parsing, asyncio for timing
   - Non-blocking: runs as background task alongside FastAPI server

### No new migrations

- Store schedule/tools in CustomAgent.metadata (existing JSON column)
- Use server_default={} to auto-populate on backfill

### Exact new endpoints (method + path):

1. POST /api/v1/ai-agents/custom/{agent_id}/schedule - Create/update schedule
2. GET /api/v1/ai-agents/custom/{agent_id}/schedule - Fetch schedule
3. DELETE /api/v1/ai-agents/custom/{agent_id}/schedule - Remove schedule
4. POST /api/v1/ai-agents/custom/{agent_id}/tools - Set allowed tools
5. GET /api/v1/ai-agents/custom/{agent_id}/tools - Get available + selected tools

## Frontend changes

### Files to create:

1. **frontend/src/features/ai-agents/components/SchedulePanel.tsx** (NEW ~300 lines)
   - Cron builder UI with human-readable presets
   - Dropdowns: Frequency (daily/weekly/monthly/custom), Hour (0-23), Day-of-week (1-7), etc.
   - OR raw cron input with validation feedback
   - "Next run" display (parsed from cron)
   - Toggle: Enabled/Disabled
   - Helper: "Run daily at 9 AM" →   9 * * *

2. **frontend/src/features/ai-agents/components/ToolPanel.tsx** (NEW ~250 lines)
   - List of available tools (fetched from /agents/ endpoint)
   - Each tool: icon, name, description, required permission
   - Checkboxes for user to select tools
   - Permission warning if user lacks permission (grayed out)
   - "Save" button → POST /custom/{id}/tools

3. **frontend/src/features/ai-agents/components/ApplyActionButton.tsx** (NEW ~150 lines)
   - Component to render "Apply to BOQ" / "Approve and post" buttons in run timeline
   - Checks output JSON for required fields (e.g., positions[].description, positions[].quantity)
   - On click, dispatch action (deferred: approval_routes integration)

### Files to modify:

1. **frontend/src/features/ai-agents/components/CustomAgentBuilder.tsx** (MODIFY ~300 lines)
   - Add two new tabs in the modal (after the form closes):
     - **Schedule tab** (collapsible in the Advanced section, or separate modal tab)
     - **Tools tab** (collapsible in the Advanced section)
   - Move icon/category/examples to top "Basic" section
   - "Tell us what it should do" (guided) → middle section
   - Advanced dropdown:
     - Raw prompt toggle (existing)
     - Schedule panel (new)
     - Tool picker (new)
   - Make sure the modal can grow to fit all sections without overflow

2. **frontend/src/features/ai-agents/AgentsPage.tsx** (MODIFY ~100 lines)
   - When editing custom agent, pre-populate Schedule + Tools from API
   - Add "Schedule runs" link on agent card (if scheduled)
   - Show "Next run: 2025-01-15 at 9:00 AM" if scheduled
   - Badge icon (clock) if scheduled

3. **frontend/src/features/ai-agents/components/RunTimeline.tsx** (MODIFY ~150 lines)
   - After final_output rendered, add section for action buttons
   - If output is structured JSON with positions, show "Apply to BOQ" button
   - Button disabled if user lacks oq.write permission
   - On click → POST /api/v1/boq/positions with output data
   - Toast feedback: "Applied 3 positions to BOQ"

4. **frontend/src/features/ai-agents/api.ts** (MODIFY ~150 lines)
   - New API methods:
     - setAgentSchedule(agentId, cronExpr) → POST /custom/{id}/schedule
     - getAgentSchedule(agentId) → GET /custom/{id}/schedule
     - deleteAgentSchedule(agentId) → DELETE /custom/{id}/schedule
     - setAgentTools(agentId, toolNames) → POST /custom/{id}/tools
     - getAgentTools(agentId) → GET /custom/{id}/tools
   - Update request/response types

### Exact UI surfaces:

1. **Route**: /ai-agents (existing)
   - Remains the main agent gallery + builder modal entry point
   
2. **Modal**: "Create your own agent" / "Edit agent"
   - New: "Schedule" collapsible section with cron UI
   - New: "Tools" collapsible section with permission-gated checkboxes
   
3. **Agent card**: Show schedule indicator
   - Clock icon + "Daily at 9 AM" text if scheduled
   - Click to edit

4. **Run timeline**: After final_output
   - New: "Apply" section with contextual buttons
   - "Apply to BOQ" if structured position JSON detected

## Migration

**None.** Schedule/tools stored in CustomAgent.metadata (JSON column exists with server_default={}).

## File touch list

### Backend files:
- backend/app/modules/ai_agents/models.py
- backend/app/modules/ai_agents/service.py
- backend/app/modules/ai_agents/schemas.py
- backend/app/modules/ai_agents/router.py
- backend/app/modules/ai_agents/repository.py
- backend/app/modules/ai_agents/base.py
- backend/app/modules/ai_agents/scheduler.py (NEW)
- backend/app/modules/ai_agents/triggers.py (NEW)
- backend/app/core/scheduler.py (NEW)

### Frontend files:
- frontend/src/features/ai-agents/components/CustomAgentBuilder.tsx
- frontend/src/features/ai-agents/components/SchedulePanel.tsx (NEW)
- frontend/src/features/ai-agents/components/ToolPanel.tsx (NEW)
- frontend/src/features/ai-agents/components/ApplyActionButton.tsx (NEW)
- frontend/src/features/ai-agents/components/RunTimeline.tsx
- frontend/src/features/ai-agents/AgentsPage.tsx
- frontend/src/features/ai-agents/api.ts

## Conflicts / sequencing

**No hard conflicts.** Item 11 (CO AI draft) uses core/llm.py, not ai_agents. Wave 4 items (field, documents, payroll) are independent.

Implementation sequencing within item 29:
1. Backend model/schema/repository changes
2. Scheduler service
3. Frontend builder modal with Schedule/Tools tabs
4. Apply buttons + run timeline integration
5. End-to-end testing

## Test plan

### Browser test:

**Test 1 - Schedule creation**
1. Navigate to /ai-agents
2. Create custom agent with name and goal
3. Expand Advanced > Schedule → Select "Daily" at 9:00 AM
4. Save → Verify cron stored as   9 * * *
5. Edit agent → Verify "Daily at 9:00 AM" displays

**Test 2 - Tool selection**
1. In builder, expand Advanced > Tools
2. Check "search_costs" and "create_position"
3. Save → Verify POST /custom/{id}/tools succeeds
4. Fetch agent → Verify metadata.allowed_tools populated

**Test 3 - Scheduled run**
1. Create agent with cron */2 * * * * (test frequency)
2. Wait for scheduler to fire
3. Verify new run appears in timeline with "Scheduled" badge

**Test 4 - Apply to BOQ**
1. Run agent with structured JSON output (positions array)
2. Verify "Apply to BOQ" button appears
3. Click → Verify positions created in BOQ

### Unit tests:

- Cron validation (valid/invalid expressions)
- Permission check on tool selection
- Schedule metadata structure
- Apply button JSON validation

## Risks

1. Cron library dependency (croniter) - Pure Python, lightweight
2. Scheduler collision on multi-instance - Single process OK for now
3. Permissions mismatch - Validate at setup + runtime
4. Timezone edge cases - Use UTC internally
5. Apply button JSON parsing - Strict schema validation

---

**Design document version**: 1.0  
**Date**: 2026-06-04  
**Status**: Ready for implementation  
**Effort estimate**: M (4-5 days)
