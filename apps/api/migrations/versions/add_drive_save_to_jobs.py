
"""add_drive_file_id_and_metadata_to_jobs

Revision ID: a1b2c3d4e5f6
Revises: 1234567890ab
Create Date: 2026-03-14 12:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = None  # Will be auto-resolved by Alembic merge
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add drive_file_id column to jobs table — tracks where the report was auto-saved
    op.add_column('jobs', sa.Column('drive_file_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_jobs_drive_file_id', 'jobs', 'drive_files',
        ['drive_file_id'], ['id'],
        ondelete='SET NULL'
    )
    # Add metadata JSONB column to jobs table
    op.add_column('jobs', sa.Column('metadata', postgresql.JSONB(), nullable=True, server_default='{}'))

def downgrade() -> None:
    op.drop_constraint('fk_jobs_drive_file_id', 'jobs', type_='foreignkey')
    op.drop_column('jobs', 'drive_file_id')
    op.drop_column('jobs', 'metadata')
