import sys, asyncio, asyncpg
from app.core.config import settings

async def check():
    url = settings.DATABASE_URL.replace("postgresql://", "postgres://").replace("+asyncpg", "").replace(":6543", ":5432")
    print(f"URL: {url}")
    conn = await asyncpg.connect(url)
    users = await conn.fetch("SELECT * FROM users")
    print(f"Users found: {len(users)}")
    for u in users:
         print(f" - {u['email']}")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(check())
