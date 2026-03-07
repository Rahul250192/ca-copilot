"""Merge heads

Revision ID: 09508c52aa37
Revises: add_agree_tables, 1234567890ab
Create Date: 2026-02-28 13:43:57.379258

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09508c52aa37'
down_revision: Union[str, None] = ('add_agree_tables', '1234567890ab')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
