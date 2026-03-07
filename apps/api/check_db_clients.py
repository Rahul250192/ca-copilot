import asyncio
from app.db.session import AsyncSessionLocal
from app.models.models import User, Client
from sqlalchemy.future import select

async def main():
    async with AsyncSessionLocal() as session:
        users = await session.execute(select(User))
        all_users = users.scalars().all()
        print(f"Total users: {len(all_users)}")
        for u in all_users:
            print(f"User: {u.email}, firm_id: {u.firm_id}")

        clients = await session.execute(select(Client))
        all_clients = clients.scalars().all()
        print(f"\nTotal clients: {len(all_clients)}")
        for c in all_clients:
            print(f"Client: {c.name}, firm_id: {c.firm_id}")

if __name__ == "__main__":
    asyncio.run(main())
