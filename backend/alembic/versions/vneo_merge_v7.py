"""Merge the Neoffice/Protti branch with the upstream v7 migration branch.

Revision ID: vneo_merge_v7
Revises: vneo_merge_v67, v3172_closeout_init
Create Date: 2026-06-06

//// NEOFFICE PATCH — alembic branch merge (recurring).

Our permanent Protti branch (rejoined at ``vneo_merge_v67``) and the
upstream v7 wave (``v3156_payroll_batches`` … ``v3172_closeout_init``)
both descend from ``v3155_finance_connectors``, so after pulling v7 there
are two alembic heads again. This no-op merge revision rejoins them into a
single head so ``alembic upgrade head`` stays unambiguous.

This is the expected per-upgrade cost of keeping a parallel ``vneo_``
branch: each upstream wave adds a new linear chain off the last shared
revision, and we add one merge revision to close it.
"""
from __future__ import annotations

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "vneo_merge_v7"
down_revision: Union[str, Sequence[str], None] = (
    "vneo_merge_v67",
    "v3172_closeout_init",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op: this revision only rejoins two branches."""


def downgrade() -> None:
    """No-op: splitting back into two heads is not supported."""
