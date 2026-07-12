"""merge v11.2 upstream (cost bases + design options) into neoffice line

Revision ID: vneo_merge_v11_2
Revises: v3235_design_options, vneo_merge_v10_9
Create Date: 2026-07-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v11_2'
down_revision: Union[str, None] = ('v3235_design_options', 'vneo_merge_v10_9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
