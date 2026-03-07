import sys, asyncio, asyncpg
from app.core.config import settings

async def check():
    url = settings.DATABASE_URL.replace("postgresql://", "postgres://").replace("+asyncpg", "").replace(":6543", ":5432")
    conn = await asyncpg.connect(url)
    invoices = await conn.fetch("SELECT id, vendor_name, total_amount, amount, expenses_type FROM get_invoice")
    for inv in invoices:
         print(f"Row {inv['id']}: total_amount={inv['total_amount']}, amount={inv['amount']}, expenses_type={inv['expenses_type']}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())
