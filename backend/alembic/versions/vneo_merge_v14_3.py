"""merge v14.3.0 upstream into neoffice line

Revision ID: vneo_merge_v14_3
Revises: v3280_contract_templates, vneo_text_catalog
Create Date: 2026-07-31

Closes the two heads the v14.3.0 merge opened: upstream's chain ending at
v3280_contract_templates, and our own ending at vneo_text_catalog (the CAN/NPK
wording catalogue). No schema change of its own.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'vneo_merge_v14_3'
down_revision: Union[str, None] = ('v3280_contract_templates', 'vneo_text_catalog')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
