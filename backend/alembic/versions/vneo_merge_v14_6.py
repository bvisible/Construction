"""merge v14.6.0 upstream into neoffice line

Revision ID: vneo_merge_v14_6
Revises: v3284_payment_clock, vneo_merge_v14_3
Create Date: 2026-08-07

Closes the two heads the v14.6.0 merge opened: upstream's chain ending at
v3284_payment_clock, and ours at vneo_merge_v14_3. No schema change of its own.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v14_6'
down_revision: Union[str, None] = ('v3284_payment_clock', 'vneo_merge_v14_3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
