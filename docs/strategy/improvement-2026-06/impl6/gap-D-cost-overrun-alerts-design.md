# Gap D - Cost-overrun alerts to notifications when a budget line breaches threshold

## Current state (verified against code)

**Backend (backend/app/modules/costmodel/):**
- BudgetLine (oe_costmodel_budget_line) tracks planned, committed, actual, forecast amounts
- CostModelService.update_budget_line() publishes costmodel.budget_line.updated event
- No current overrun threshold storage or alerting logic

**Backend (backend/app/modules/notifications/):**
- NotificationService handles creation and delivery via i18n keys (title_key, body_key)
- Subscribers in events.py and _wave5_cross_module_subscribers.py follow pattern:
  - Subscribe to event, open isolated session, call NotificationService, commit
  - Catch all exceptions so notification failure never breaks upstream

**Frontend (frontend/src/features/costmodel/):**
- CostModelPage.tsx shows budget summary and lines list
- No UI for overrun thresholds or alert preferences

**Gap:** No per-budget-line overrun threshold; no alert when actual_amount exceeds planned + threshold%.

---

## Exact scope (demonstrable + testable)

**Goal:** When BudgetLine.actual_amount breaches threshold, notify project owner.

**Trigger:** costmodel.budget_line.updated event -> subscriber checks if actual >= planned * (1 + threshold_pct / 100) -> notify.

**UX:** Threshold slider on budget line detail panel. Badge "Alert @ +10%" on lines with thresholds. Notification in bell icon navigates to cost spine page.

**Idempotent:** 24h cooldown per line (overrun_alerted_at timestamp).

**Out of scope:** Cost-controller role lookup, escalation, email/webhook, compliance gate.

---

## Shared cost-spine interface (if relevant)

Gap D CONSUMES events (does not define post_actual_to_budget_line). Gap B owns that method; Gap D listens to the resulting costmodel.budget_line.updated event.

---

## Backend (files, functions, endpoints, models/DDL)

### Models (backend/app/modules/costmodel/models.py)

Add to BudgetLine:
- overrun_alert_threshold_pct: VARCHAR(10) DEFAULT '0'  (% above planned; 0=disabled)
- overrun_alerted_at: TIMESTAMP WITH TIME ZONE  (last alert time)

### Service (backend/app/modules/costmodel/service.py)

Existing update_budget_line() already publishes event. Optional helper check_budget_line_overrun() for testing.

### Router (backend/app/modules/costmodel/router.py)

New endpoint: PATCH /5d/budget-lines/{line_id}/overrun-alert-threshold?threshold=10 -> sets threshold, returns updated line.

### Schemas (backend/app/modules/costmodel/schemas.py)

Add overrun_alert_threshold_pct and overrun_alerted_at fields to BudgetLineResponse and BudgetLineUpdate.

### Event subscriber (NEW: backend/app/modules/notifications/_wave6_costmodel_subscribers.py)

Subscribe to costmodel.budget_line.updated:
1. Check if line has threshold (> 0)
2. Check if actual >= planned * (1 + threshold / 100)
3. Check cooldown (alerted_at recent?)
4. If all pass, notify project.owner_id
5. Set overrun_alerted_at timestamp
6. Catch exceptions, log at debug

Register in manifest (backend/app/modules/notifications/manifest.py).

### Locale (backend/app/modules/notifications/messages/en.json)

Add keys:
- notifications.costmodel.overrun_alert.title = "Cost Overrun Alert"
- notifications.costmodel.overrun_alert.body = "{{category}} cost exceeded {{threshold_pct}}% threshold..."

### DDL (Alembic migration)

File: backend/alembic/versions/v3XXX_costmodel_budget_line_overrun_alerts.py

ALTER TABLE oe_costmodel_budget_line ADD overrun_alert_threshold_pct VARCHAR(10) DEFAULT '0';
ALTER TABLE oe_costmodel_budget_line ADD overrun_alerted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;
CREATE INDEX ix_costmodel_budget_line_overrun_alert ON oe_costmodel_budget_line(project_id, overrun_alerted_at) WHERE overrun_alert_threshold_pct > '0';

---

## Frontend (route, components, UX)

### New component: BudgetLineThresholdEditor.tsx

Slider 0-50%, label, save button. Issues PATCH to set threshold.

### Update CostModelPage.tsx

Integrate threshold editor in budget line detail panel. Show badge on lines with thresholds.

### Notification UI

Existing NotificationBell renders notifications. Click cost_overrun_alert -> /costmodel?line={entity_id}.

---

## Migration DDL

Same as backend DDL above. Both columns nullable with safe defaults.

---

## File touch list (own vs needs-central vs overlaps-Wave5)

**Gap D owns (new):**
- backend/app/modules/notifications/_wave6_costmodel_subscribers.py
- backend/app/modules/notifications/messages/en.json (append)
- frontend/src/features/costmodel/BudgetLineThresholdEditor.tsx
- docs/strategy/improvement-2026-06/impl6/gap-D-cost-overrun-alerts-design.md

**Gap D edits (existing):**
- backend/app/modules/costmodel/models.py (2 new columns)
- backend/app/modules/costmodel/schemas.py (new fields)
- backend/app/modules/costmodel/router.py (PATCH endpoint)
- backend/app/modules/costmodel/service.py (optional helper)
- backend/app/modules/notifications/manifest.py (register subscriber)
- backend/alembic/versions/v3XXX_*.py (migration)
- frontend/src/features/costmodel/CostModelPage.tsx (integrate editor)
- frontend/src/features/costmodel/api.ts (add PATCH call)

**Needs central:** None.

**Overlaps Wave5:** Project.owner_id lookup; no file collisions.

---

## Sequencing / conflicts

No blocking dependencies. Gap B lands first (cost spine posting). Wave 5 lands. Gap D lands (columns, subscriber, UI). No conflicts.

---

## TEST MATRIX (exhaustive)

**Unit (backend/tests/test_costmodel_service.py):**
1. test_overrun_not_breached: planned=100, actual=105, threshold=10 -> is_overrun=False
2. test_overrun_breached: planned=100, actual=111, threshold=10 -> is_overrun=True
3. test_overrun_disabled: threshold=0 -> is_overrun=False
4. test_overrun_no_planned: planned=0 -> is_overrun=False

**Integration (backend/tests/test_costmodel_router.py):**
5. test_set_threshold_success: PATCH /5d/budget-lines/{id}/overrun-alert-threshold threshold=20 -> 200
6. test_set_threshold_validation: threshold=invalid -> 400
7. test_set_threshold_not_found: non-existent line -> 404
8. test_set_threshold_permission: missing permission -> 403

**Subscriber (backend/tests/test_notifications_costmodel.py):**
9. test_on_budget_line_updated_no_threshold: threshold=0 -> 0 notifications
10. test_on_budget_line_updated_overrun_crossed: threshold=10, actual>=110% -> 1 notification
11. test_on_budget_line_updated_not_crossed: threshold=10, actual=105% -> 0 notifications
12. test_on_budget_line_updated_cooldown_active: emit twice within 24h -> 1st sends, 2nd skipped
13. test_on_budget_line_updated_cooldown_expired: emit, wait 25h, emit -> both send
14. test_on_budget_line_updated_context_accuracy: verify body_context fields match
15. test_on_budget_line_updated_sets_alerted_at: notification sent -> overrun_alerted_at updated
16. test_on_budget_line_updated_exception_swallowed: exception in subscriber -> logged, no re-raise

**Browser/E2E (frontend/e2e/costmodel_overrun.spec.ts):**
17. test_user_sets_threshold: set threshold slider to 15%, save -> badge shows "Alert @ +15%"
18. test_user_receives_notification: set threshold=10, actual=111 -> notification appears
19. test_threshold_bounds: slider clamped to 0-50%
20. test_notification_click: click notification -> navigates to /costmodel?line={id}

---

## Risks

1. **Notification spam:** Low threshold = frequent alerts. Mitigated: 24h cooldown, UI defaults 10%.
2. **Cooldown false negative:** Actual drops then rises within 24h, no re-alert. Acceptable MVP.
3. **Missing owner:** If project.owner_id NULL, no notification. Phase 2 adds cost_controller role.
4. **Wave 5 collision:** If Wave 5 #19 also subscribes to same event, both run (no conflict).
5. **Alembic merge:** If Wave 5 edits BudgetLine, resolve merge conflict.
6. **i18n coverage:** Keys must be translated (26 languages). /i18n-sweep during rollout.
7. **Event dedup:** Duplicate events -> duplicate notifications. Mitigated: cooldown + event bus idempotency.

---

## Implementation roadmap

**Phase 1 (this wave):**
1. Add columns (models, migration)
2. Implement subscriber (_wave6_costmodel_subscribers.py)
3. Add PATCH endpoint + schemas
4. Implement BudgetLineThresholdEditor React component
5. Integrate into CostModelPage detail panel
6. Full test matrix
7. i18n keys + i18n-sweep
8. E2E manual test: set threshold, update actual, verify notification

**Phase 2 (Wave 6.5):**
1. Cost-controller role lookup
2. Escalation (2nd crossing -> email)
3. Per-user threshold override
4. Historical trends graph