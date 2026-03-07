import sys, asyncio, asyncpg
from app.core.config import settings

async def check():
    url = settings.DATABASE_URL.replace("postgresql://", "postgres://").replace("+asyncpg", "").replace(":6543", ":5432")
    conn = await asyncpg.connect(url)
    invoices = await conn.fetch("SELECT * FROM get_invoice")
    print(f"Invoices found: {len(invoices)}")
    for inv in invoices:
         print(f" - {dict(inv)}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())
