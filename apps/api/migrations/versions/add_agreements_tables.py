"""add agreements tables

Revision ID: add_agreements_tables
Revises: add_user_profile_fields
Create Date: 2026-02-24
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_agree_tables'
down_revision = 'add_profile_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'agreement_categories',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(), nullable=True),
        sa.Column('display_order', sa.Integer(), server_default='0'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
    )

    op.create_table(
        'agreement_types',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('category_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agreement_categories.id'), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(), nullable=True),
        sa.Column('display_order', sa.Integer(), server_default='0'),
        sa.Column('default_clauses', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
    )

    op.create_table(
        'user_agreement_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('agreement_type_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('agreement_types.id'), nullable=False),
        sa.Column('custom_clauses', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()')),
    )

    # Unique constraint: one customization per user per agreement type
    op.create_unique_constraint(
        'uq_user_agreement_template',
        'user_agreement_templates',
        ['user_id', 'agreement_type_id']
    )


def downgrade() -> None:
    op.drop_table('user_agreement_templates')
    op.drop_table('agreement_types')
    op.drop_table('agreement_categories')
