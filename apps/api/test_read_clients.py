import asyncio
from app.db.session import AsyncSessionLocal
from app.models.models import User, Client, Service
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

async def test():
    try:
        async with AsyncSessionLocal() as session:
            # Get Rahul's firm_id
            u_res = await session.execute(select(User).where(User.email=="gupta.rahulg25@gmail.com"))
            user = u_res.scalars().first()
            if not user:
                print("User not found!")
                return
            print(f"User firm: {user.firm_id}")

            # The exact query from the endpoint
            query = select(Client).options(
                selectinload(Client.services).selectinload(Service.kits)
            ).where(
                Client.firm_id == user.firm_id
            ).offset(0).limit(100)
            
            result = await session.execute(query)
            clients = result.scalars().all()
            print(f"Query returned {len(clients)} clients.")
            for c in clients:
                print(c.name)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
