# Gap F – PO Retainage + Period-End Reconciliation Report

## Current state (verified)

**Backend structures:**
- `oe_procurement_po` table: has `amount_subtotal`, `amount_total`, `tax_amount`; **no retainage fields**
- `oe_finance_invoice` table: has `retention_amount` (Decimal/MoneyType), applied only to invoices
- `contracts/service.py`: retention calculation on contracts; **no PO retention logic**
- `procurement/models.py`: PurchaseOrderItem links to cost_line_id; no retainage field
- `reporting/models.py`: ReportTemplate report_type does not include retainage report
- `finance/models.py`: Invoice has retention_amount; Payment has no withholding fields
- `costmodel/models.py`: BudgetLine has actual_amount; no retainage tracking

**UI state:**
- Procurement page: PO list, 3-way match, supplier scorecard; **no retainage UI**
- Finance page: invoices, budgets, EVM, connectors
- Reporting page: KPI snapshots, templates, generated reports; **no retainage report**

---

## Exact scope (demonstrable)

**Gap F delivers:**

1. **Retainage on PO commitments:**
   - Add `retention_percent` (Decimal 5,2; default 0.00) to PurchaseOrder
   - Add `retain_on_receipt` boolean (default false) to control application point
   - Computed `retainage_amount` = amount_total × retention_percent / 100
   - PO detail shows retainage %; list shows amber "Retainage 5%" badge when > 0
   - New table `oe_procurement_po_retainage_release` for audit log of releases

2. **Period-end retainage reconciliation report:**
   - New report type: `po_retainage_reconciliation`
   - Scoped to project + period_start/period_end (ISO dates)
   - Aggregates all POs issued in period with retention > 0
   - Columns: PO number, vendor, issue date, total committed, retention %, withheld, released YTD, held
   - Summary: total committed, total withheld, total released, total held
   - Exportable as PDF/CSV; schedulable template
   - Deterministic (no AI); manual release via MANAGER approval

3. **Retainage release workflow:**
   - POST /procurement/{po_id}/release-retainage/ (MANAGER only)
   - Body: amount (Decimal string), optional reason
   - Validates: amount ≤ retainage_held; PO must be issued or completed
   - Updates po.retainage_released_amount
   - Publishes procurement.po.retainage_released event
   - Each release audit-logged (who, when, amount, reason)

---

## Shared cost-spine interface (if relevant)

**Gap B owns `CostSpineService.post_actual_to_budget_line()` method.**

Gap F **does NOT define** that method; assumes it exists and that finance module calls it when:
- PO issued (retain_on_receipt=false): post_actual with full amount (retainage deducted later when released)
- Goods receipt confirmed (retain_on_receipt=true): post_actual for received quantity
- Retainage released: no re-post (already in BudgetLine.actual)

**Gap F does NOT own the cost-spine method; assumes Gap B provides it.**

---

## Backend (files, functions, endpoints, models/DDL)

### Models & DDL

**New table: `oe_procurement_po_retainage_release`**
```sql
CREATE TABLE oe_procurement_po_retainage_release (
  id VARCHAR(36) PRIMARY KEY DEFAULT GUID(),
  po_id VARCHAR(36) NOT NULL,
  release_date VARCHAR(40) NOT NULL,
  release_amount NUMERIC(18, 4) NOT NULL,
  release_reason VARCHAR(255),
  released_by_id VARCHAR(36),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  metadata_ JSON DEFAULT '{}',
  
  FOREIGN KEY (po_id) REFERENCES oe_procurement_po(id) ON DELETE CASCADE,
  INDEX ix_retainage_po_date (po_id, release_date)
);
```

**Modified table: `oe_procurement_po`**
```sql
ALTER TABLE oe_procurement_po ADD COLUMN (
  retention_percent NUMERIC(5, 2) NOT NULL DEFAULT 0.00 AFTER tax_amount,
  retain_on_receipt BOOLEAN NOT NULL DEFAULT 0 AFTER retention_percent,
  retainage_released_amount VARCHAR(50) NOT NULL DEFAULT '0' AFTER retain_on_receipt
);

CREATE INDEX ix_po_retention_percent ON oe_procurement_po(retention_percent);
```

### ORM Models

**File: `backend/app/modules/procurement/models.py` (extend PurchaseOrder)**

```python
from decimal import Decimal
from sqlalchemy import Boolean, Numeric

# Add to PurchaseOrder class:

    retention_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        default=Decimal("0.00"),
        doc="Retention percentage (e.g. 5.00 for 5%)",
    )
    retain_on_receipt: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        doc="True: retainage at GR; False: at invoice",
    )
    retainage_released_amount: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="0",
        server_default="0",
        doc="Cumulative retainage released (Decimal string)",
    )

    def retainage_amount(self) -> Decimal:
        """Computed: amount_total × retention_percent / 100."""
        total = Decimal(str(self.amount_total or "0"))
        pct = self.retention_percent or Decimal("0")
        return (total * pct / Decimal("100")).quantize(Decimal("0.0001"))

    def retainage_held(self) -> Decimal:
        """Computed: retainage_amount - retainage_released_amount."""
        withheld = self.retainage_amount()
        released = Decimal(str(self.retainage_released_amount or "0"))
        return max(withheld - released, Decimal("0"))


# New class in same file:

class PORetainageRelease(Base):
    """Audit log of retainage release transactions."""

    __tablename__ = "oe_procurement_po_retainage_release"

    po_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_procurement_po.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    release_date: Mapped[str] = mapped_column(String(40), nullable=False)
    release_amount: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
    )
    release_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    released_by_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
        server_default="{}",
    )

    def __repr__(self) -> str:
        return f"<PORetainageRelease po={self.po_id} amount={self.release_amount}>"
```

### Service

**File: `backend/app/modules/procurement/service.py` (extend ProcurementService)**

```python
# Add to __init__:
    self.retainage_repo = PORetainageReleaseRepository(session)

# Add method:
    async def release_po_retainage(
        self,
        po_id: uuid.UUID,
        release_amount: Decimal,
        reason: str | None = None,
        user_id: uuid.UUID | None = None,
    ) -> PORetainageRelease:
        """Release withheld retainage on a PO.
        
        Raises 404 if PO not found, 409 if status invalid or amount > held,
        400 if amount format invalid.
        """
        po = await self.po_repo.get_by_id(po_id)
        if po is None:
            raise HTTPException(status_code=404, detail="PO not found")

        if po.status not in ("issued", "partially_received", "completed"):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot release retainage from PO in '{po.status}'",
            )

        held = po.retainage_held()
        if release_amount > held:
            raise HTTPException(
                status_code=400,
                detail=f"Release {release_amount} exceeds held {held}",
            )

        released_sum = Decimal(str(po.retainage_released_amount or "0"))
        new_released = released_sum + release_amount

        await self.po_repo.update_fields(po.id, retainage_released_amount=str(new_released))

        now = datetime.now(timezone.utc).isoformat()
        release = PORetainageRelease(
            po_id=po_id,
            release_date=now,
            release_amount=release_amount,
            release_reason=reason,
            released_by_id=user_id,
        )
        release = await self.retainage_repo.create(release)

        await _safe_publish(
            "procurement.po.retainage_released",
            {
                "po_id": str(po_id),
                "release_amount": str(release_amount),
                "released_by": str(user_id),
                "release_reason": reason,
            },
        )

        return release

    async def get_po_retainage_releases(
        self,
        po_id: uuid.UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[PORetainageRelease], int]:
        """List all retainage release records for a PO."""
        return await self.retainage_repo.list_for_po(po_id, offset=offset, limit=limit)
```

### Repository

**File: `backend/app/modules/procurement/repository.py` (add new class)**

```python
class PORetainageReleaseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, record: PORetainageRelease) -> PORetainageRelease:
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_for_po(
        self,
        po_id: uuid.UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[PORetainageRelease], int]:
        from sqlalchemy import func, select
        
        base = select(PORetainageRelease).where(PORetainageRelease.po_id == po_id)
        count_stmt = select(func.count()).select_from(base.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        stmt = (
            base.order_by(PORetainageRelease.release_date.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all()), total
```

### Schemas

**File: `backend/app/modules/procurement/schemas.py` (extend)**

```python
class PORetainageReleaseResponse(BaseModel):
    id: str
    po_id: str
    release_date: str
    release_amount: str
    release_reason: str | None = None
    released_by_id: str | None = None

    model_config = ConfigDict(from_attributes=True)


# Extend PurchaseOrderResponse:
class PurchaseOrderResponse(BaseModel):
    # ... existing fields ...
    retention_percent: str
    retain_on_receipt: bool
    retainage_amount: str  # computed
    retainage_held: str    # computed

    model_config = ConfigDict(from_attributes=True)
```

### Router

**File: `backend/app/modules/procurement/router.py` (add endpoints)**

```python
@router.post(
    "/{po_id}/release-retainage/",
    response_model=PORetainageReleaseResponse,
    status_code=201,
)
async def release_po_retainage(
    po_id: uuid.UUID,
    body: dict = Body(...),
    user_id: CurrentUserId = None,
    _perm: None = Depends(RequirePermission("procurement.approve")),
    session: SessionDep = Depends(),
) -> PORetainageReleaseResponse:
    """Release withheld retainage on a PO (MANAGER only).
    
    Body: { "amount": "1500.00", "reason": "..." }
    """
    service = ProcurementService(session)
    release_amount = Decimal(body.get("amount", "0"))
    reason = body.get("reason")
    
    record = await service.release_po_retainage(
        po_id=po_id,
        release_amount=release_amount,
        reason=reason,
        user_id=uuid.UUID(user_id) if user_id else None,
    )
    await session.commit()
    return PORetainageReleaseResponse.model_validate(record)


@router.get("/{po_id}/retainage-releases/", response_model=list[PORetainageReleaseResponse])
async def list_po_retainage_releases(
    po_id: uuid.UUID,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    session: SessionDep = Depends(),
) -> list[PORetainageReleaseResponse]:
    """List retainage release audit log for a PO."""
    service = ProcurementService(session)
    releases, _ = await service.get_po_retainage_releases(
        po_id=po_id,
        offset=offset,
        limit=limit,
    )
    return [PORetainageReleaseResponse.model_validate(r) for r in releases]
```

### Reporting Service

**File: `backend/app/modules/reporting/service.py` (add method to ReportingService)**

```python
async def render_po_retainage_reconciliation(
    self,
    project_id: uuid.UUID,
    period_start: str,
    period_end: str,
) -> dict:
    """Render period-end PO retainage reconciliation report.
    
    Returns:
    {
        "project_id": "...",
        "period_start": "2026-06-01",
        "period_end": "2026-06-30",
        "summary": {
            "total_committed": "1500000.00",
            "total_withheld": "75000.00",
            "total_released": "25000.00",
            "total_held": "50000.00",
        },
        "po_rows": [
            {
                "po_number": "PO-001",
                "vendor_name": "...",
                "issue_date": "2026-06-05",
                "status": "issued",
                "amount_total": "100000.00",
                "retention_percent": "5.00",
                "retainage_withheld": "5000.00",
                "retainage_released_ytd": "1000.00",
                "retainage_held": "4000.00",
            },
        ],
    }
    """
    from app.modules.procurement.models import PurchaseOrder
    from sqlalchemy import select

    stmt = (
        select(PurchaseOrder)
        .where(
            PurchaseOrder.project_id == project_id,
            PurchaseOrder.retention_percent > Decimal("0"),
            PurchaseOrder.issue_date >= period_start,
            PurchaseOrder.issue_date <= period_end,
        )
        .order_by(PurchaseOrder.issue_date.asc())
    )
    result = await self.session.execute(stmt)
    pos = list(result.scalars().all())

    po_rows = []
    total_committed = Decimal("0")
    total_withheld = Decimal("0")
    total_released = Decimal("0")

    for po in pos:
        committed = Decimal(str(po.amount_total or "0"))
        withheld = po.retainage_amount()
        released = Decimal(str(po.retainage_released_amount or "0"))
        held = max(withheld - released, Decimal("0"))

        total_committed += committed
        total_withheld += withheld
        total_released += released

        vendor_name = ""
        if po.vendor_contact_id:
            try:
                from app.modules.contacts.repository import ContactRepository
                contact_repo = ContactRepository(self.session)
                contact = await contact_repo.get_by_id(po.vendor_contact_id)
                if contact:
                    vendor_name = getattr(contact, "company_name", "") or ""
            except Exception:
                pass

        po_rows.append({
            "po_id": str(po.id),
            "po_number": po.po_number,
            "vendor_name": vendor_name,
            "issue_date": po.issue_date,
            "status": po.status,
            "amount_total": str(committed),
            "currency": po.currency_code or "",
            "retention_percent": str(po.retention_percent),
            "retainage_withheld": str(withheld),
            "retainage_released_ytd": str(released),
            "retainage_held": str(held),
        })

    total_held = max(total_withheld - total_released, Decimal("0"))

    return {
        "project_id": str(project_id),
        "period_start": period_start,
        "period_end": period_end,
        "summary": {
            "total_committed": str(total_committed),
            "total_withheld": str(total_withheld),
            "total_released": str(total_released),
            "total_held": str(total_held),
        },
        "po_rows": po_rows,
    }
```

### Reporting Router

**File: `backend/app/modules/reporting/router.py` (add endpoint)**

```python
@router.get("/po-retainage-reconciliation/", response_model=dict)
async def get_po_retainage_reconciliation(
    project_id: uuid.UUID = Query(...),
    period_start: str = Query(...),
    period_end: str = Query(...),
    user_id: CurrentUserId = None,
    _perm: None = Depends(RequirePermission("reporting.read")),
    session: SessionDep = Depends(),
    service: ReportingService = Depends(_get_service),
) -> dict:
    """Get PO retainage reconciliation for project period.
    
    Query params:
        project_id: project UUID
        period_start: ISO date YYYY-MM-DD
        period_end: ISO date YYYY-MM-DD
    """
    await verify_project_access(project_id, user_id, session)
    return await service.render_po_retainage_reconciliation(
        project_id=project_id,
        period_start=period_start,
        period_end=period_end,
    )
```

---

## Frontend (route, components, UX)

### Changes to ProcurementPage

**File: `frontend/src/features/procurement/ProcurementPage.tsx` (extend)**

- Add "Retainage" tab to PO detail side panel
- Show: retention_percent, retainage_amount, retainage_held
- Table: retainage releases (date, amount, reason, released_by)
- Button: "Release Retainage" (MANAGER only) → modal
  - Input: amount, reason
  - Validation: amount ≤ retainage_held
  - POST /procurement/{po_id}/release-retainage/
  - Toast on success; refresh table

### Changes to ReportingPage

**File: `frontend/src/features/reporting/ReportingPage.tsx` (extend)**

- Add "PO Retainage Reconciliation" to report type menu
- When selected:
  - Project picker (auto-filled if on project)
  - period_start / period_end date pickers (default current month)
  - "Run Report" button
  - Render result: header, summary chips, PO table
  - Export: PDF, CSV buttons

---

## Migration DDL

**New alembic migration: `v3156_po_retainage.py`**

```python
"""Add PO retainage support

Revision ID: v3156_po_retainage
Revises: v3155_connectors
Create Date: 2026-06-04
"""

from alembic import op
import sqlalchemy as sa

def upgrade():
    op.add_column(
        "oe_procurement_po",
        sa.Column(
            "retention_percent",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0.00",
        ),
    )
    op.add_column(
        "oe_procurement_po",
        sa.Column(
            "retain_on_receipt",
            sa.Boolean(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "oe_procurement_po",
        sa.Column(
            "retainage_released_amount",
            sa.String(50),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_index(
        "ix_po_retention_percent",
        "oe_procurement_po",
        ["retention_percent"],
    )
    
    op.create_table(
        "oe_procurement_po_retainage_release",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("po_id", sa.String(36), nullable=False),
        sa.Column("release_date", sa.String(40), nullable=False),
        sa.Column("release_amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("release_reason", sa.String(255), nullable=True),
        sa.Column("released_by_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("metadata_", sa.JSON(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["po_id"], ["oe_procurement_po.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_retainage_po_date",
        "oe_procurement_po_retainage_release",
        ["po_id", "release_date"],
    )

def downgrade():
    op.drop_table("oe_procurement_po_retainage_release")
    op.drop_index("ix_po_retention_percent", "oe_procurement_po")
    op.drop_column("oe_procurement_po", "retainage_released_amount")
    op.drop_column("oe_procurement_po", "retain_on_receipt")
    op.drop_column("oe_procurement_po", "retention_percent")
```

---

## File touch list

### Gap F owns

- `backend/app/modules/procurement/models.py` – PurchaseOrder + PORetainageRelease
- `backend/app/modules/procurement/repository.py` – PORetainageReleaseRepository
- `backend/app/modules/procurement/service.py` – release_po_retainage(), get_po_retainage_releases()
- `backend/app/modules/procurement/schemas.py` – PORetainageReleaseResponse, extend PurchaseOrderResponse
- `backend/app/modules/procurement/router.py` – /release-retainage/, /retainage-releases/
- `backend/app/modules/reporting/service.py` – render_po_retainage_reconciliation() (additive only)
- `backend/app/modules/reporting/router.py` – /po-retainage-reconciliation/ (additive only)
- `frontend/src/features/procurement/ProcurementPage.tsx` – Retainage tab + release modal
- `frontend/src/features/reporting/ReportingPage.tsx` – PO Retainage Reconciliation template
- `alembic/versions/v3156_po_retainage.py` – migration

### Overlaps with Wave 5

- `backend/app/modules/reporting/` – reporting module in flight; Gap F's changes are additive
  - New report type `po_retainage_reconciliation`
  - New method in ReportingService
  - New router endpoint
  - No edits to existing code

### Needs central verification

1. Alembic: `python -m alembic heads` == one head after merge
2. Permissions: reuse `procurement.approve` (MANAGER), `reporting.read` (EDITOR)
3. No new permission definitions
4. Embedded PG auto-creates table + columns at startup

---

## Sequencing/conflicts

**Hard dependency:** Gap B (CostSpineService.post_actual_to_budget_line) must exist first.
- If Gap B not done: Gap F code compiles, retainage event fires but no subscriber.
- Recommended: Gap B → Gap F.

**Wave 5 sequencing:** Gap F's reporting additions are additive, safe to land after Wave 5.
- Central: (1) Merge Wave 5, (2) Merge Gap F, (3) Verify single alembic head + no TS1117.

**No file-disjoint conflicts in Wave 6:** Gap F touches procurement + reporting. Safe to run parallel with other gaps.

---

## TEST MATRIX (exhaustive)

### Unit tests: `backend/tests/unit/test_procurement_retainage.py`

1. PurchaseOrder.retainage_amount() = amount_total × retention_percent / 100 ✓
2. PurchaseOrder.retainage_held() = retainage_amount - retainage_released_amount ✓
3. PORetainageRelease creation ✓
4. ProcurementService.release_po_retainage()
   - Happy path: release 1000 from 5000 held → po.retainage_released_amount updated, record created
   - 404: PO not found
   - 409: PO in draft status (not issued/completed)
   - 400: amount > held
5. PORetainageReleaseRepository.create(), list_for_po() ✓
6. ProcurementService.get_po_retainage_releases() ✓

### Integration tests: `backend/tests/integration/test_po_retainage_flow.py`

1. End-to-end: create PO (retention=5%, amount=100k), issue, release 2k, release 3k
   - Assert po.retainage_amount=5k, po.retainage_held=5k → 3k → 0k
   - GET /retainage-releases/ returns 2 records
2. Multi-currency: EUR PO, retainage in EUR, report rolls up correctly
3. Permission gate: EDITOR cannot release (403), MANAGER can (201)
4. render_po_retainage_reconciliation()
   - 3 POs in period: issue dates 2026-06-01, 06-15, 07-01 (period 06-01 to 06-30)
   - Assert report includes first 2 only
   - Release 1000 from first PO; report shows total_held decremented

### Browser tests: `frontend/e2e/procurement-retainage.spec.ts`

1. PO detail: Retainage tab renders (retention %, withheld, held, releases table)
2. Release flow: click "Release Retainage", modal (amount, reason), POST succeeds, tab refreshes
3. Reporting: select "PO Retainage Reconciliation", pick project, set period, run report, export PDF/CSV
4. PO list: POs with retention > 0 show amber "Retainage 5%" badge
5. Permission: EDITOR user cannot see Release button or it is disabled
6. Zero console errors on all surfaces

---

## Risks

1. **Currency precision:** PO in foreign currency; report rolls up in project base currency. If no FX rate configured, amount kept in native currency (not zeroed). **Mitigation:** Report labels currencies; summary notes any foreign unconverted amounts.

2. **Idempotency of release:** Retrying POST /release-retainage/ twice with same amount rejects second (amount > held after first release). Acceptable for MVP; Wave 6 may add idempotency_key.

3. **Stale browser cache:** User opens PO detail, another user releases retainage, first user's page shows old held amount. **Mitigation:** Modal closes, list refreshes after release. Best practice: refresh detail on any action.

4. **Report generation latency:** Many POs (1000s) may slow report. **Mitigation:** Indexed queries (ix_po_retention_percent, ix_retainage_po_date); pagination can be added in Wave 6.

5. **Wave 5 + Gap F overlap:** Both touch reporting module. **Mitigation:** Gap F changes are additive (new method, endpoint, type); no edits to existing Wave 5 code. Central verifies single head + no TS1117 dups.

6. **retain_on_receipt field stored but not enforced:** Determines whether retainage applies at GR or invoice. Current Gap F does not wire up the logic. **Mitigation:** Field is set for future use; Wave 6+ can implement when GR confirmation becomes a cost-posting event.

---

## Notes for implementation

- **Deterministic:** All retainage math is Decimal; no AI.
- **Manual release:** MANAGER approves each release; not auto-deducted.
- **GUID IDs:** PORetainageRelease.id is VARCHAR(36) with GUID() default.
- **Idempotency:** Double-posting caught by > held check.
- **Events:** procurement.po.retainage_released fires; no subscriber yet (Wave 6 item E may add).
- **Permissions:** Reuse `procurement.approve` (MANAGER) and `reporting.read` (EDITOR); no new defs.
- **No migration blocking:** Columns + table are append-only; single alembic head maintained.

---

## Dependencies & assumptions

- **Gap B must be done first:** CostSpineService.post_actual_to_budget_line method expected.
- **Wave 5 must complete before Gap F merges:** reporting module in heavy edit.
- **Event bus operational:** procurement.po.retainage_released event fires (subscribers may not exist yet).
