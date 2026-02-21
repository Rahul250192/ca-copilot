import asyncio
import os
import sys
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Add apps/api to path
sys.path.append(os.path.abspath("apps/api"))

from app.models.job import Job
from app.models.models import User
from app.core.config import settings

async def check_jobs():
    engine = create_async_engine(
        settings.DATABASE_URL,
        connect_args={"statement_cache_size": 0}
    )
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        result = await session.execute(select(Job).order_by(Job.created_at.desc()).limit(10))
        jobs = result.scalars().all()
        print(f"Found {len(jobs)} recent jobs:")
        for job in jobs:
            print(f"- ID: {job.id}, Type: {job.job_type}, Status: {job.status}, Client: {job.client_id}, Created: {job.created_at}")

if __name__ == "__main__":
    asyncio.run(check_jobs())
