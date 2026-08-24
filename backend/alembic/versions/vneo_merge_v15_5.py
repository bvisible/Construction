"""merge v15.5.0 upstream into neoffice line

Revision ID: vneo_merge_v15_5
Revises: v3302_tax_combination, vneo_merge_v15_4
Create Date: 2026-08-24

Closes the two heads the v15.5.0 merge opened: upstream's chain ending at
v3302_tax_combination, and ours at vneo_merge_v15_4. No schema change of its
own.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v15_5'
down_revision: Union[str, None] = ('v3302_tax_combination', 'vneo_merge_v15_4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
