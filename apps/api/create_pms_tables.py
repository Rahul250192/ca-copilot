"""
Create PMS accounting tables in production database.
Run once: python3 create_pms_tables.py
"""
import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import text
from app.db.session import AsyncSessionLocal

# Each statement is executed independently — no multi-statement batches
STATEMENTS = [
    # 1. PMS Accounts
    """CREATE TABLE IF NOT EXISTS pms_accounts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        client_id UUID NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
        provider_name VARCHAR(200) NOT NULL,
        strategy_name VARCHAR(200),
        account_code VARCHAR(100),
        pms_start_date DATE,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        config JSONB DEFAULT '{}',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_pms_account_client ON pms_accounts(client_id)",

    # 2. Security Master
    """CREATE TABLE IF NOT EXISTS security_master (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        isin VARCHAR(12) UNIQUE,
        name VARCHAR(500) NOT NULL,
        exchange VARCHAR(20),
        aliases JSONB DEFAULT '[]',
        fmv_31jan2018 NUMERIC(15,4),
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_security_master_isin ON security_master(isin)",

    # 3. PMS Transactions
    """CREATE TABLE IF NOT EXISTS pms_transactions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        pms_account_id UUID NOT NULL REFERENCES pms_accounts(id) ON DELETE CASCADE,
        upload_id UUID REFERENCES fi_uploads(id) ON DELETE SET NULL,
        security_id UUID REFERENCES security_master(id),
        tx_date DATE NOT NULL,
        tx_type VARCHAR(30) NOT NULL,
        security_name VARCHAR(500) NOT NULL,
        exchange VARCHAR(20),
        quantity NUMERIC(15,6),
        unit_price NUMERIC(15,4),
        brokerage NUMERIC(15,2) DEFAULT 0,
        stt NUMERIC(15,2) DEFAULT 0,
        stamp_duty NUMERIC(15,2) DEFAULT 0,
        settlement_amt NUMERIC(15,2),
        narration TEXT,
        is_duplicate BOOLEAN DEFAULT FALSE,
        je_status VARCHAR(20) DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_pms_tx_account ON pms_transactions(pms_account_id)",
    "CREATE INDEX IF NOT EXISTS idx_pms_tx_date ON pms_transactions(pms_account_id, tx_date)",
    "CREATE INDEX IF NOT EXISTS idx_pms_tx_security ON pms_transactions(pms_account_id, security_name)",

    # 4. FIFO Lots
    """CREATE TABLE IF NOT EXISTS fifo_lots (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        pms_account_id UUID NOT NULL REFERENCES pms_accounts(id) ON DELETE CASCADE,
        security_id UUID REFERENCES security_master(id),
        security_name VARCHAR(500) NOT NULL,
        purchase_tx_id UUID REFERENCES pms_transactions(id) ON DELETE SET NULL,
        purchase_date DATE NOT NULL,
        original_qty NUMERIC(15,6) NOT NULL,
        remaining_qty NUMERIC(15,6) NOT NULL,
        cost_per_unit NUMERIC(15,4) NOT NULL,
        total_cost NUMERIC(15,2),
        is_opening BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_fifo_lot_account ON fifo_lots(pms_account_id)",
    "CREATE INDEX IF NOT EXISTS idx_fifo_lot_security ON fifo_lots(pms_account_id, security_name)",
    "CREATE INDEX IF NOT EXISTS idx_fifo_lot_date ON fifo_lots(pms_account_id, purchase_date)",

    # 5. Capital Gain Matches
    """CREATE TABLE IF NOT EXISTS capital_gain_matches (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        sell_tx_id UUID NOT NULL REFERENCES pms_transactions(id) ON DELETE CASCADE,
        lot_id UUID NOT NULL REFERENCES fifo_lots(id) ON DELETE CASCADE,
        qty_consumed NUMERIC(15,6) NOT NULL,
        cost_basis NUMERIC(15,2) NOT NULL,
        sale_proceeds NUMERIC(15,2) NOT NULL,
        gain_loss NUMERIC(15,2) NOT NULL,
        holding_days INTEGER,
        gain_type VARCHAR(4) NOT NULL,
        is_grandfathered BOOLEAN DEFAULT FALSE,
        effective_cost_per_unit NUMERIC(15,4),
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_cg_match_sell ON capital_gain_matches(sell_tx_id)",
    "CREATE INDEX IF NOT EXISTS idx_cg_match_lot ON capital_gain_matches(lot_id)",

    # 6. PMS Dividends
    """CREATE TABLE IF NOT EXISTS pms_dividends (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        pms_account_id UUID NOT NULL REFERENCES pms_accounts(id) ON DELETE CASCADE,
        upload_id UUID REFERENCES fi_uploads(id) ON DELETE SET NULL,
        security_id UUID REFERENCES security_master(id),
        security_name VARCHAR(500) NOT NULL,
        ex_date DATE,
        received_date DATE,
        quantity NUMERIC(15,6),
        rate_per_share NUMERIC(15,4),
        gross_amount NUMERIC(15,2) NOT NULL,
        tds_deducted NUMERIC(15,2) DEFAULT 0,
        net_received NUMERIC(15,2),
        je_status VARCHAR(20) DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_pms_div_account ON pms_dividends(pms_account_id)",
    "CREATE INDEX IF NOT EXISTS idx_pms_div_date ON pms_dividends(pms_account_id, ex_date)",

    # 7. PMS Expenses
    """CREATE TABLE IF NOT EXISTS pms_expenses (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        pms_account_id UUID NOT NULL REFERENCES pms_accounts(id) ON DELETE CASCADE,
        upload_id UUID REFERENCES fi_uploads(id) ON DELETE SET NULL,
        expense_type VARCHAR(100) NOT NULL,
        expense_date DATE,
        period_from DATE,
        period_to DATE,
        amount NUMERIC(15,2) NOT NULL,
        gst_amount NUMERIC(15,2) DEFAULT 0,
        tds_applicable NUMERIC(15,2) DEFAULT 0,
        net_payable NUMERIC(15,2),
        is_paid BOOLEAN,
        is_accrual BOOLEAN DEFAULT FALSE,
        is_stt_recon_only BOOLEAN DEFAULT FALSE,
        narration TEXT,
        je_status VARCHAR(20) DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS idx_pms_exp_account ON pms_expenses(pms_account_id)",
    "CREATE INDEX IF NOT EXISTS idx_pms_exp_type ON pms_expenses(pms_account_id, expense_type)",
]


async def main():
    print("🔄 Creating PMS accounting tables...")
    async with AsyncSessionLocal() as db:
        for i, stmt in enumerate(STATEMENTS):
            try:
                await db.execute(text(stmt))
                await db.commit()
                # Print table creation (not index) progress
                if "CREATE TABLE" in stmt:
                    table_name = stmt.split("EXISTS")[1].split("(")[0].strip()
                    print(f"  ✅ {table_name}")
            except Exception as e:
                await db.rollback()
                err_msg = str(e)[:120]
                if "already exists" in err_msg.lower():
                    pass  # silently skip
                else:
                    print(f"  ⚠ Statement {i+1}: {err_msg}")

    print("\n✅ PMS tables created successfully!")
    print("   Tables: pms_accounts, security_master, pms_transactions,")
    print("           fifo_lots, capital_gain_matches, pms_dividends, pms_expenses")


if __name__ == "__main__":
    asyncio.run(main())
