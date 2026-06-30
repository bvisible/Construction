"""merge OCE v9.4.0 upstream head into neoffice line

Revision ID: vneo_merge_v10
Revises: v3215_bim_view_folders, vneo_merge_v9
Create Date: 2026-06-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v10'
down_revision: Union[str, None] = ('v3215_bim_view_folders', 'vneo_merge_v9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
