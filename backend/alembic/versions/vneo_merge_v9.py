"""merge OCE v8.8.4 upstream head into neoffice line

Revision ID: vneo_merge_v9
Revises: v3190_qms_signature_unique, vneo_merge_v8
Create Date: 2026-06-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v9'
down_revision: Union[str, None] = ('v3190_qms_signature_unique', 'vneo_merge_v8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
