import asyncio
from sqlalchemy import select
from app.models.models import User
from app.db.session import AsyncSessionLocal, engine

async def check():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()
        print(f"Total Users: {len(users)}")
        for u in users:
            print(f"- {u.email}")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check())
