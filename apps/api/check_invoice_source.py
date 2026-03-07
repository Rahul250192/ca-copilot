import asyncio
from sqlalchemy import text
from app.db.session import engine

async def check_source():
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT id, source FROM get_invoice ORDER BY id DESC LIMIT 5;"))
        rows = result.fetchall()
        print("Invoices:")
        for row in rows:
            print(f"- ID: {row[0]}, Source: {row[1]}")

if __name__ == "__main__":
    asyncio.run(check_source())
