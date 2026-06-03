"""PostgreSQL auto-migrator (embedded PostgreSQL only).

On startup, compares the live PostgreSQL schema against the SQLAlchemy models
and adds any missing columns via ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``.

This is the PostgreSQL counterpart to :func:`app.core.sqlite_migrator.sqlite_auto_migrate`.
The embedded-PostgreSQL default runtime (v6.0.0+, no Docker) builds its schema
with ``Base.metadata.create_all``, which only ever creates *missing tables* and
never alters an existing one. So when the app is upgraded across versions, any
column added to an existing table (for example ``oe_boq_position.cost_line_id``
from the v6.4.0 cost spine) is absent from a database created under the older
version, and every ORM read of that table fails with ``UndefinedColumnError``.

This runs for the embedded server only. External PostgreSQL deployments still
manage their schema with Alembic (that path never calls this).
"""

import logging

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


async def postgres_auto_migrate(engine: AsyncEngine, base) -> int:
    """Compare SQLAlchemy models against the PostgreSQL schema and add missing columns.

    Args:
        engine: The async SQLAlchemy engine (must be PostgreSQL).
        base: The declarative ``Base`` whose metadata holds every model.

    Returns:
        Number of columns added.
    """
    columns_added = 0

    async with engine.begin() as conn:
        existing_tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))

        for table in base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # New table - create_all handles it.

            existing_cols = await conn.run_sync(
                lambda sync_conn, tn=table.name: {col["name"] for col in inspect(sync_conn).get_columns(tn)}
            )

            for col in table.columns:
                if col.name in existing_cols:
                    continue

                col_type = col.type.compile(engine.dialect)

                default = ""
                if col.server_default is not None:
                    raw = col.server_default.arg
                    if isinstance(raw, str):
                        quoted = raw if raw.startswith("'") else "'" + raw.replace("'", "''") + "'"
                        default = f" DEFAULT {quoted}"
                    else:
                        # Expression default (func.now(), CURRENT_TIMESTAMP, ...).
                        # Compile it to literal SQL; PostgreSQL accepts a function
                        # or expression as an ADD COLUMN default, unlike SQLite.
                        try:
                            compiled = str(
                                raw.compile(
                                    dialect=engine.dialect,
                                    compile_kwargs={"literal_binds": True},
                                )
                            )
                        except Exception:  # noqa: BLE001
                            compiled = ""
                        if compiled:
                            default = f" DEFAULT {compiled}"

                # Only enforce NOT NULL when a default exists to backfill the
                # rows already in the table. Without a default, adding a NOT NULL
                # column to a populated table fails, so we add it nullable and
                # let the app's Python-side default cover new writes (mirrors the
                # defensive behaviour of the SQLite migrator).
                not_null = " NOT NULL" if (not col.nullable and default) else ""

                sql = f'ALTER TABLE "{table.name}" ADD COLUMN IF NOT EXISTS "{col.name}" {col_type}{not_null}{default}'

                try:
                    await conn.execute(text(sql))
                    columns_added += 1
                    logger.info(
                        "PostgreSQL migration: added column %s.%s (%s)",
                        table.name,
                        col.name,
                        col_type,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "PostgreSQL migration: failed to add %s.%s: %s",
                        table.name,
                        col.name,
                        exc,
                    )

    if columns_added > 0:
        logger.info("PostgreSQL auto-migration complete: %d columns added", columns_added)

    return columns_added
