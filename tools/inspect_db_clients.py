import asyncio
import sys
import os
sys.path.append(os.getcwd())

from sqlalchemy.future import select
from app.db.session import AsyncSessionLocal
from app.models.models import Client

async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Client))
        clients = result.scalars().all()
        print(f"Found {len(clients)} clients:")
        for client in clients:
            print(f"Name: {client.name}, PAN: {client.pan}, CIN: {client.cin}")

if __name__ == "__main__":
    asyncio.run(main())
