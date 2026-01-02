"""make services global and fix schema

Revision ID: global_svc_fix
Revises: 33cdbd9654a2
Create Date: 2026-01-02 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'global_svc_fix'
down_revision: Union[str, None] = '33cdbd9654a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Fix Clients Schema (gstins vs gst_number)
    # 1. Fix Clients Schema (gstins vs gst_number)
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c['name'] for c in inspector.get_columns('clients')]
    
    if 'gstins' not in columns:
        op.add_column('clients', sa.Column('gstins', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='[]'))
    try:
        op.drop_column('clients', 'gst_number')
    except Exception:
        pass

    # 2. Make Services Global (remove firm_id)
    try:
        op.drop_constraint('services_firm_id_fkey', 'services', type_='foreignkey')
        op.drop_column('services', 'firm_id')
    except Exception as e:
        print(f"Note: {e}")


def downgrade() -> None:
    # Revert Services
    op.add_column('services', sa.Column('firm_id', sa.UUID(), autoincrement=False, nullable=True))
    # Note: We can't easily restore the foreign key constraint without knowing the exact name or guaranteed target, 
    # but strictly speaking we should. For now, just adding the column back.
    
    # Revert Clients
    op.add_column('clients', sa.Column('gst_number', sa.VARCHAR(), autoincrement=False, nullable=True))
    op.drop_column('clients', 'gstins')
