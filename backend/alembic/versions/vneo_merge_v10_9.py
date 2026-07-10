"""merge v10.9 upstream (estimate modules + prefab) into neoffice line

Revision ID: vneo_merge_v10_9
Revises: v3231_prefab_unit_cost_link, vneo_merge_v10_5
Create Date: 2026-07-10 10:56:16.268803

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v10_9'
down_revision: Union[str, None] = ('v3231_prefab_unit_cost_link', 'vneo_merge_v10_5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
