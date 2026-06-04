"""BOQ position dimensions JSON column.

Adds a single nullable JSON column ``dimensions`` to ``oe_boq_position`` so
typed components can carry a structured dimension map (e.g. ``{"L": 1.75,
"H": 1.6, "E": 0.2}``) that downstream pricing modules feed to the formula
engine in ``costmodel_typed`` to derive component quantities.

Additive, nullable, indexed: existing rows stay valid. Downgrade fully
reverses the upgrade.

Revision ID: vneo_boq_position_dimensions
Revises: vneo_assembly_components
Create Date: 2026-06-02
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "vneo_boq_position_dimensions"
down_revision: Union[str, None] = "vneo_assembly_components"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return any(c["name"] == column for c in insp.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "oe_boq_position", "dimensions"):
        op.add_column(
            "oe_boq_position",
            sa.Column("dimensions", sa.JSON, nullable=True),
        )
        logger.info("Added column oe_boq_position.dimensions")
    else:
        logger.info("oe_boq_position.dimensions already exists, skipping")


def downgrade() -> None:
    bind = op.get_bind()
    if _column_exists(bind, "oe_boq_position", "dimensions"):
        op.drop_column("oe_boq_position", "dimensions")
