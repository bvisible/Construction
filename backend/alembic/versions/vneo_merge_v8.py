"""merge OCE v8.3.1 upstream head into neoffice line

Revision ID: vneo_merge_v8
Revises: v3186_payroll_deductions_net, vneo_merge_v7
Create Date: 2026-06-15 18:47:41.940143

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v8'
down_revision: Union[str, None] = ('v3186_payroll_deductions_net', 'vneo_merge_v7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
