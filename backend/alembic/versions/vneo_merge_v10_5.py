"""merge v10.5 upstream (v3216-v3221) into neoffice line

Revision ID: vneo_merge_v10_5
Revises: v3221_cost_explorer_reverse_index, vneo_merge_v10
Create Date: 2026-07-07 16:38:22.866058

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v10_5'
down_revision: Union[str, None] = ('v3221_cost_explorer_reverse_index', 'vneo_merge_v10')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
