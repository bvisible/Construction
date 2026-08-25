"""merge v15.8.0 upstream into neoffice line

Revision ID: vneo_merge_v15_8
Revises: v3306_tolerance_profile_currency, vneo_merge_v15_5
Create Date: 2026-08-25

Closes the two heads the v15.8.0 merge opened: upstream's chain ending at
v3306_tolerance_profile_currency, and ours at vneo_merge_v15_5. No schema
change of its own.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v15_8'
down_revision: Union[str, None] = ('v3306_tolerance_profile_currency', 'vneo_merge_v15_5')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
