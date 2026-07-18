"""merge v11.14 upstream (parametric assemblies + registers + security) into neoffice line

Revision ID: vneo_merge_v11_14
Revises: v3248_commissioning, vneo_merge_v11_9
Create Date: 2026-07-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v11_14'
down_revision: Union[str, None] = ('v3248_commissioning', 'vneo_merge_v11_9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
