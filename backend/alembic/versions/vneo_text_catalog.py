"""NEOFFICE MIGRATION — Swiss CAN/NPK text catalogue.

Creates:

* ``oe_neoffice_text_catalog``  — a catalogue of position texts
  (e.g. "CAN 135 — Béton et béton armé"), optionally scoped to a project.
* ``oe_neoffice_text_position`` — one position text, or one sub-position under
  it (self-referencing ``parent_id``). ``unit`` is NULLABLE on purpose: a
  wording line carries no unit, only a measurable sub-position does. That is
  the whole reason this is not a cost catalogue, whose ``rate`` is NOT NULL.

Every operation is guarded so the migration is safe to re-run on a partially
applied install, and a fresh install that boots the app first already has the
tables via ``Base.metadata.create_all``. The downgrade fully reverses it.

Ids are VARCHAR(36) rather than native UUID: the deployed OCE databases store
every id that way, and a native-UUID FK against a VARCHAR primary key is
rejected by PostgreSQL ("foreign key constraint cannot be implemented").

Revision ID: vneo_text_catalog
Revises: vneo_merge_v12_9
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "vneo_text_catalog"
down_revision: Union[str, None] = "vneo_merge_v12_9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CATALOG = "oe_neoffice_text_catalog"
_POSITION = "oe_neoffice_text_position"


def _has_table(inspector: sa.engine.reflection.Inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    is_sqlite = bind.dialect.name == "sqlite"
    guid_type = sa.String(36)
    json_type = sa.JSON() if is_sqlite else sa.dialects.postgresql.JSONB()

    if not _has_table(inspector, _CATALOG):
        op.create_table(
            _CATALOG,
            sa.Column("id", guid_type, primary_key=True),
            sa.Column("code", sa.String(50), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("description", sa.Text(), nullable=False, server_default=""),
            sa.Column("standard", sa.String(20), nullable=False, server_default="CAN"),
            sa.Column("language", sa.String(5), nullable=False, server_default="fr"),
            sa.Column("project_id", guid_type, nullable=True),
            sa.Column("metadata", json_type, nullable=False, server_default="{}"),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
            ),
        )
        op.create_index(f"ix_{_CATALOG}_code", _CATALOG, ["code"])
        op.create_index(f"ix_{_CATALOG}_project_id", _CATALOG, ["project_id"])

    if not _has_table(inspector, _POSITION):
        op.create_table(
            _POSITION,
            sa.Column("id", guid_type, primary_key=True),
            sa.Column(
                "catalog_id", guid_type,
                sa.ForeignKey(f"{_CATALOG}.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column(
                "parent_id", guid_type,
                sa.ForeignKey(f"{_POSITION}.id", ondelete="CASCADE"), nullable=True,
            ),
            sa.Column("code", sa.String(60), nullable=False),
            sa.Column("title", sa.String(500), nullable=False, server_default=""),
            sa.Column("body", sa.Text(), nullable=False, server_default=""),
            # Nullable on purpose — see the module docstring.
            sa.Column("unit", sa.String(20), nullable=True),
            sa.Column("assembly_id", guid_type, nullable=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("metadata", json_type, nullable=False, server_default="{}"),
            sa.Column(
                "created_at", sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
            ),
            sa.Column(
                "updated_at", sa.DateTime(timezone=True),
                server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
            ),
        )
        op.create_index(f"ix_{_POSITION}_catalog_id", _POSITION, ["catalog_id"])
        op.create_index(f"ix_{_POSITION}_parent_id", _POSITION, ["parent_id"])
        op.create_index(f"ix_{_POSITION}_code", _POSITION, ["code"])
        op.create_index(f"ix_{_POSITION}_assembly_id", _POSITION, ["assembly_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _has_table(inspector, _POSITION):
        op.drop_table(_POSITION)
    if _has_table(inspector, _CATALOG):
        op.drop_table(_CATALOG)
