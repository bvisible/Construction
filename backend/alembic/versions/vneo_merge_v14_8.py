"""merge v14.8.1 upstream into neoffice line

Revision ID: vneo_merge_v14_8
Revises: v3292_finance_einvoice_seller_contact, vneo_merge_v14_6
Create Date: 2026-08-14

Closes the two heads the v14.8.1 merge opened: upstream's chain ending at
v3292_finance_einvoice_seller_contact, and ours at vneo_merge_v14_6. No schema
change of its own.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v14_8'
down_revision: Union[str, None] = ('v3292_finance_einvoice_seller_contact', 'vneo_merge_v14_6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
