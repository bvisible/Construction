"""Typed components & yield library schema.

Adds the two tables that hold the typed component layer attached to
``oe_costmodel_cost_line`` plus a productivity-rate library:

* ``oe_assembly_component`` — typed sub-block component
  (labor / machine / material / internal_loc / external_margin / …) hanging off
  a CostLine via CASCADE FK. Carries ``unit_rate``, ``qty``, ``yield_per_hour``,
  ``amount`` as Decimal-as-string (v3 §10). ``metadata`` JSON for downstream
  module extensions.

* ``oe_yield_library`` — productivity reference entries (units per hour) for
  labor tasks, scoped to a project or global (``project_id`` NULL).

Every operation is guarded so the migration is safe to re-run on a partially
applied install, and a fresh install that boots the app first already has all
of this via ``Base.metadata.create_all``. The downgrade fully reverses the
upgrade so a stamp roundtrip leaves the schema unchanged.

Revision ID: vneo_assembly_components
Revises: v3151_cost_spine
Create Date: 2026-06-02
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "vneo_assembly_components"
down_revision: Union[str, None] = "v3151_cost_spine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def _table_exists(bind: sa.engine.Connection, table: str) -> bool:
    inspector = sa.inspect(bind)
    return table in inspector.get_table_names()


def _index_exists(bind: sa.engine.Connection, table: str, index: str) -> bool:
    inspector = sa.inspect(bind)
    if table not in inspector.get_table_names():
        return False
    return any(ix["name"] == index for ix in inspector.get_indexes(table))


def upgrade() -> None:
    bind = op.get_bind()

    # ── Table 1: typed components ──────────────────────────────────────────
    if not _table_exists(bind, "oe_assembly_component"):
        op.create_table(
            "oe_assembly_component",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "cost_line_id",
                sa.String(length=36),
                sa.ForeignKey("oe_costmodel_cost_line.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "sub_block_label",
                sa.String(length=255),
                nullable=False,
                server_default="",
            ),
            sa.Column("component_type", sa.String(length=40), nullable=False),
            sa.Column("description", sa.Text, nullable=False, server_default=""),
            sa.Column("unit", sa.String(length=20), nullable=True),
            sa.Column(
                "unit_rate", sa.String(length=50), nullable=False, server_default="0"
            ),
            sa.Column("discount", sa.String(length=20), nullable=True),
            sa.Column("qty", sa.String(length=50), nullable=True),
            sa.Column("yield_per_hour", sa.String(length=50), nullable=True),
            sa.Column(
                "amount", sa.String(length=50), nullable=False, server_default="0"
            ),
            sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
            sa.Column(
                "metadata", sa.JSON, nullable=False, server_default=sa.text("'{}'")
            ),
        )
        logger.info("Created table oe_assembly_component")
    else:
        logger.info("oe_assembly_component already exists, skipping create_table")

    if not _index_exists(
        bind, "oe_assembly_component", "ix_oe_assembly_component_cost_line"
    ):
        op.create_index(
            "ix_oe_assembly_component_cost_line",
            "oe_assembly_component",
            ["cost_line_id"],
        )
    if not _index_exists(
        bind, "oe_assembly_component", "ix_oe_assembly_component_type"
    ):
        op.create_index(
            "ix_oe_assembly_component_type",
            "oe_assembly_component",
            ["component_type"],
        )

    # ── Table 2: yield library ─────────────────────────────────────────────
    if not _table_exists(bind, "oe_yield_library"):
        op.create_table(
            "oe_yield_library",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "project_id",
                sa.String(length=36),
                sa.ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("task_label", sa.String(length=255), nullable=False),
            sa.Column("unit", sa.String(length=20), nullable=False, server_default=""),
            sa.Column(
                "yield_per_hour",
                sa.String(length=50),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "source", sa.String(length=40), nullable=False, server_default="manual"
            ),
            sa.Column("source_ref", sa.String(length=255), nullable=True),
            sa.Column("last_calibrated_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "metadata", sa.JSON, nullable=False, server_default=sa.text("'{}'")
            ),
        )
        logger.info("Created table oe_yield_library")
    else:
        logger.info("oe_yield_library already exists, skipping create_table")

    if not _index_exists(bind, "oe_yield_library", "ix_oe_yield_library_project"):
        op.create_index(
            "ix_oe_yield_library_project", "oe_yield_library", ["project_id"]
        )
    if not _index_exists(
        bind, "oe_yield_library", "ix_oe_yield_library_task_label"
    ):
        op.create_index(
            "ix_oe_yield_library_task_label",
            "oe_yield_library",
            ["task_label"],
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _index_exists(bind, "oe_yield_library", "ix_oe_yield_library_task_label"):
        op.drop_index("ix_oe_yield_library_task_label", table_name="oe_yield_library")
    if _index_exists(bind, "oe_yield_library", "ix_oe_yield_library_project"):
        op.drop_index("ix_oe_yield_library_project", table_name="oe_yield_library")
    if _table_exists(bind, "oe_yield_library"):
        op.drop_table("oe_yield_library")

    if _index_exists(
        bind, "oe_assembly_component", "ix_oe_assembly_component_type"
    ):
        op.drop_index(
            "ix_oe_assembly_component_type", table_name="oe_assembly_component"
        )
    if _index_exists(
        bind, "oe_assembly_component", "ix_oe_assembly_component_cost_line"
    ):
        op.drop_index(
            "ix_oe_assembly_component_cost_line", table_name="oe_assembly_component"
        )
    if _table_exists(bind, "oe_assembly_component"):
        op.drop_table("oe_assembly_component")
