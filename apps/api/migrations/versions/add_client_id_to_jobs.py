
"""add_client_id_to_jobs

Revision ID: 1234567890ab
Revises: create_job_tables
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1234567890ab'
down_revision = 'create_job_tables' # Changed from None
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('jobs', sa.Column('client_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index(op.f('ix_jobs_client_id'), 'jobs', ['client_id'], unique=False)
    op.create_foreign_key(None, 'jobs', 'clients', ['client_id'], ['id'])

def downgrade() -> None:
    op.drop_constraint(None, 'jobs', type_='foreignkey')
    op.drop_index(op.f('ix_jobs_client_id'), table_name='jobs')
    op.drop_column('jobs', 'client_id')
