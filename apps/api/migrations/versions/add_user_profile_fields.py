"""add user profile fields

Revision ID: add_profile_fields
Revises: global_svc_fix
Create Date: 2026-01-03 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_profile_fields'
down_revision: Union[str, None] = 'global_svc_fix'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use inspector to check if columns exist (idempotency)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('users')]
    
    if 'phone_number' not in columns:
        op.add_column('users', sa.Column('phone_number', sa.String(), nullable=True))
    
    if 'job_title' not in columns:
        op.add_column('users', sa.Column('job_title', sa.String(), nullable=True))
        
    if 'subscription_plan' not in columns:
        op.add_column('users', sa.Column('subscription_plan', sa.String(), nullable=True, server_default='free'))


def downgrade() -> None:
    op.drop_column('users', 'subscription_plan')
    op.drop_column('users', 'job_title')
    op.drop_column('users', 'phone_number')
