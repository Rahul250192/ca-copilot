import sys, asyncio, asyncpg
from app.core.config import settings

async def check():
    url = settings.DATABASE_URL.replace("postgresql://", "postgres://").replace("+asyncpg", "").replace(":6543", ":5432")
    print(f"Connecting to: {url}")
    conn = await asyncpg.connect(url)
    tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    for t in tables:
         print(f"Table: {t['table_name']}")
    
    invs = await conn.fetch("SELECT COUNT(*) FROM get_invoice")
    print(f"get_invoice count: {invs[0]['count']}")
    
    usr = await conn.fetch("SELECT COUNT(*) FROM users")
    print(f"users count: {usr[0]['count']}")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())
