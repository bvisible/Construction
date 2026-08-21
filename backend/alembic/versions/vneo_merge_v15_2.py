"""merge v15.2.0 upstream into neoffice line

Revision ID: vneo_merge_v15_2
Revises: v3300_formwork_system_choice, vneo_merge_v14_8
Create Date: 2026-08-21

Closes the two heads the v15.2.0 merge opened: upstream's chain ending at
v3300_formwork_system_choice, and ours at vneo_merge_v14_8. No schema change
of its own.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v15_2'
down_revision: Union[str, None] = ('v3300_formwork_system_choice', 'vneo_merge_v14_8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
