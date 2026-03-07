"""merge heads

Revision ID: 52a7aa767586
Revises: 1aaba0d1fa0d, e2227062bad0
Create Date: 2026-03-01 12:28:47.215968

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '52a7aa767586'
down_revision: Union[str, None] = ('1aaba0d1fa0d', 'e2227062bad0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
