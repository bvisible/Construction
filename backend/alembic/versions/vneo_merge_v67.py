"""Merge the Neoffice/Protti migration branch with the upstream v6.7 branch.

Revision ID: vneo_merge_v67
Revises: vneo_boq_position_dimensions, v3155_finance_connectors
Create Date: 2026-06-04

//// NEOFFICE PATCH — alembic branch merge.

The Protti work (typed components + BOQ position dimensions) and the
upstream v6.7 wave (ai_agents_custom, clash_source_links,
subcontract_lien_waiver, finance_connectors) both branched off
``v3151_cost_spine`` independently, producing two alembic heads:

    v3151_cost_spine
    ├─ vneo_assembly_components ─ vneo_boq_position_dimensions   (Neoffice/Protti)
    └─ v3152_ai_agents_custom ─ … ─ v3155_finance_connectors      (upstream v6.7)

This no-op merge revision rejoins them into a single head so
``alembic upgrade head`` is unambiguous again. The Protti migrations were
renamed to the ``vneo_`` prefix so they no longer collide with upstream's
``v315x`` numbering on future merges.
"""
from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "vneo_merge_v67"
down_revision: Union[str, Sequence[str], None] = (
    "vneo_boq_position_dimensions",
    "v3155_finance_connectors",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: this revision only rejoins two branches."""


def downgrade() -> None:
    """No-op: splitting back into two heads is not supported."""
