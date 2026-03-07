import asyncio
import os
import sys

# Add apps/api to sys.path
api_path = os.path.join(os.getcwd(), "apps/api")
if api_path not in sys.path:
    sys.path.append(api_path)

# Import models to ensure they are registered with SQLAlchemy
from app.models.models import User, Firm, Client, Kit, Service, Conversation, Message, Document
from app.models.job import Job
from app.db.session import AsyncSessionLocal
from sqlalchemy.future import select

async def check():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Job))
        jobs = result.scalars().all()
        print(f"Database connection successful. Job count: {len(jobs)}")

if __name__ == "__main__":
    try:
        asyncio.run(check())
    except Exception as e:
        print(f"Database connection failed: {e}")
        import traceback
        traceback.print_exc()
