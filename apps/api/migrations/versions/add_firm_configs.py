"""Add firm_configs table for firm-level configuration storage (GST deadlines, etc.)

Revision ID: add_firm_configs
Revises: add_rule42_computations
Create Date: 2026-04-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'add_firm_configs'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use IF NOT EXISTS to be safe on re-runs
    op.execute("""
        CREATE TABLE IF NOT EXISTS firm_configs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES firms(id) ON DELETE CASCADE,
            config_key VARCHAR(100) NOT NULL,
            config_data JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            CONSTRAINT uq_firm_config_key UNIQUE (firm_id, config_key)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_firm_config_firm ON firm_configs(firm_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS firm_configs")
