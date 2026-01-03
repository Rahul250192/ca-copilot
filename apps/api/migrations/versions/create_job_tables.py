"""create job tables

Revision ID: create_job_tables
Revises: add_profile_fields
Create Date: 2026-01-03 13:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'create_job_tables'
down_revision: Union[str, None] = 'add_profile_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create Jobs Table
    op.create_table(
        'jobs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('job_type', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='QUEUED'),
        sa.Column('input_files', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('output_files', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'),
        sa.Column('created_by', sa.UUID(), nullable=False),
        sa.Column('firm_id', sa.UUID(), nullable=False), # Workspace Scope
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['firm_id'], ['firms.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_id'), 'jobs', ['id'], unique=False)
    op.create_index(op.f('ix_jobs_firm_id'), 'jobs', ['firm_id'], unique=False)

    # 2. Create Job Events Table
    op.create_table(
        'job_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('job_id', sa.UUID(), nullable=False),
        sa.Column('level', sa.String(), nullable=False, server_default='INFO'),
        sa.Column('message', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_events_job_id'), 'job_events', ['job_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_job_events_job_id'), table_name='job_events')
    op.drop_table('job_events')
    op.drop_index(op.f('ix_jobs_firm_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_id'), table_name='jobs')
    op.drop_table('jobs')
