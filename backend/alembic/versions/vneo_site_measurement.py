"""neoffice: site measurements against BOQ positions

Revision ID: vneo_site_measurement
Revises: vneo_merge_v15_8
Create Date: 2026-08-26

The quantity actually built, measured on site against the position that priced
it, with the contradictory sign-off that makes it billable. See the class note
in app/modules/neoffice/models.py for why this sits next to upstream's
oe_variations_site_measurement rather than reusing it.

No server_default on the Boolean-free columns is a deliberate choice: this
migration must run on PostgreSQL, where `server_default="0"` on a Boolean is
rejected outright (cf. scripts/fix-boolean-pg-migrations.py). There is no
Boolean here, and the JSON defaults are given as valid JSON literals.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.db_types import MoneyType
from app.database import GUID

# revision identifiers, used by Alembic.
revision: str = "vneo_site_measurement"
down_revision: Union[str, None] = "vneo_merge_v15_8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "oe_neoffice_site_measurement"


def upgrade() -> None:
    # Guard like the 24 revisions upstream now guards its own: a fresh install
    # builds its tables from the models with create_all and stamps the head, so
    # the table can already be there when this runs.
    inspector = sa.inspect(op.get_bind())
    if _TABLE in inspector.get_table_names():
        return

    op.create_table(
        _TABLE,
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("boq_position_id", GUID(), nullable=False),
        sa.Column("project_id", GUID(), nullable=True),
        sa.Column("measured_quantity", MoneyType(scale=6), nullable=False,
                  server_default="0"),
        sa.Column("unit", sa.String(20), nullable=False, server_default=""),
        sa.Column("location", sa.String(500), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("photos", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("measured_at", sa.String(40), nullable=True),
        sa.Column("measured_by", sa.String(36), nullable=True),
        sa.Column("agreed_at", sa.String(40), nullable=True),
        sa.Column("agreed_by", sa.String(36), nullable=True),
        sa.Column("signature_ref", sa.String(255), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("invoiced_at", sa.String(40), nullable=True),
        sa.Column("invoice_ref", sa.String(255), nullable=False, server_default=""),
        sa.Column("metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["boq_position_id"], ["oe_boq_position.id"],
                                ondelete="CASCADE"),
    )
    op.create_index("ix_neoffice_measurement_position", _TABLE,
                    ["boq_position_id", "measured_at"])
    op.create_index(f"ix_{_TABLE}_boq_position_id", _TABLE, ["boq_position_id"])
    op.create_index(f"ix_{_TABLE}_project_id", _TABLE, ["project_id"])
    op.create_index(f"ix_{_TABLE}_status", _TABLE, ["status"])


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if _TABLE not in inspector.get_table_names():
        return
    op.drop_table(_TABLE)
