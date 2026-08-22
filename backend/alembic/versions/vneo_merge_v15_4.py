"""merge v15.4.0 upstream into neoffice line

Revision ID: vneo_merge_v15_4
Revises: v3301_ncr_location, vneo_merge_v15_2
Create Date: 2026-08-22

Closes the two heads the v15.4.0 merge opened: upstream's chain ending at
v3301_ncr_location, and ours at vneo_merge_v15_2. No schema change of its own.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v15_4'
down_revision: Union[str, None] = ('v3301_ncr_location', 'vneo_merge_v15_2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
