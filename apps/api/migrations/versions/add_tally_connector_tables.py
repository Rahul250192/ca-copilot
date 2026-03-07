"""Add Tally connector tables: ledgers, vouchers, voucher_entries

Revision ID: tally_connector_001
Revises: add_signup_methods
Create Date: 2026-03-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = 'tally_connector_001'
down_revision = 'add_signup_methods'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── LEDGERS ──
    op.create_table(
        'ledgers',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('company_name', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('parent', sa.Text(), nullable=True),
        sa.Column('opening_balance', sa.Numeric(), nullable=True),
        sa.Column('closing_balance', sa.Numeric(), nullable=True),
        sa.Column('party_gstin', sa.Text(), nullable=True),
        sa.Column('gst_registration_type', sa.Text(), nullable=True),
        sa.Column('state', sa.Text(), nullable=True),
        sa.Column('pin_code', sa.Text(), nullable=True),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('mobile', sa.Text(), nullable=True),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('mailing_name', sa.Text(), nullable=True),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('company_name', 'name', name='uq_ledgers_company_name'),
    )
    op.create_index('idx_ledgers_company', 'ledgers', ['company_name'])
    op.create_index('idx_ledgers_parent', 'ledgers', ['company_name', 'parent'])
    op.create_index('idx_ledgers_gstin', 'ledgers', ['party_gstin'])

    # ── VOUCHERS ──
    op.create_table(
        'vouchers',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('company_name', sa.Text(), nullable=False),
        sa.Column('date', sa.Text(), nullable=True),
        sa.Column('voucher_type', sa.Text(), nullable=True),
        sa.Column('voucher_number', sa.Text(), nullable=True),
        sa.Column('party_name', sa.Text(), nullable=True),
        sa.Column('amount', sa.Numeric(), nullable=True),
        sa.Column('narration', sa.Text(), nullable=True),
        sa.Column('guid', sa.Text(), nullable=False),
        sa.Column('alter_id', sa.Text(), server_default=''),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('company_name', 'guid', name='uq_vouchers_company_guid'),
    )
    op.create_index('idx_vouchers_company', 'vouchers', ['company_name'])
    op.create_index('idx_vouchers_date', 'vouchers', ['company_name', 'date'])
    op.create_index('idx_vouchers_type', 'vouchers', ['company_name', 'voucher_type'])
    op.create_index('idx_vouchers_party', 'vouchers', ['company_name', 'party_name'])
    op.create_index('idx_vouchers_guid', 'vouchers', ['guid'])

    # ── VOUCHER ENTRIES ──
    op.create_table(
        'voucher_entries',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('company_name', sa.Text(), nullable=False),
        sa.Column('voucher_guid', sa.Text(), nullable=False),
        sa.Column('voucher_date', sa.Text(), nullable=True),
        sa.Column('voucher_type', sa.Text(), nullable=True),
        sa.Column('ledger_name', sa.Text(), nullable=False),
        sa.Column('amount', sa.Numeric(), nullable=True),
        sa.Column('is_debit', sa.Boolean(), server_default='false'),
        sa.Column('synced_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('company_name', 'voucher_guid', 'ledger_name', 'amount',
                            name='uq_ventry_company_guid_ledger_amount'),
    )
    op.create_index('idx_ventry_company', 'voucher_entries', ['company_name'])
    op.create_index('idx_ventry_guid', 'voucher_entries', ['voucher_guid'])
    op.create_index('idx_ventry_ledger', 'voucher_entries', ['company_name', 'ledger_name'])
    op.create_index('idx_ventry_date', 'voucher_entries', ['company_name', 'voucher_date'])


def downgrade() -> None:
    op.drop_table('voucher_entries')
    op.drop_table('vouchers')
    op.drop_table('ledgers')
