"""merge v12.9 upstream (v12 major) into neoffice line

Revision ID: vneo_merge_v12_9
Revises: v3258_progress_entry_seq, vneo_merge_v11_14
Create Date: 2026-07-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v12_9'
down_revision: Union[str, None] = ('v3258_progress_entry_seq', 'vneo_merge_v11_14')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
