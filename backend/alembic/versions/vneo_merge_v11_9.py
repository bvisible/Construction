"""merge v11.9 upstream (takeoff wave) into neoffice line

Revision ID: vneo_merge_v11_9
Revises: v3239_takeoff_page_scales, vneo_merge_v11_2
Create Date: 2026-07-16 12:52:36.052580

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v11_9'
down_revision: Union[str, None] = ('v3239_takeoff_page_scales', 'vneo_merge_v11_2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
