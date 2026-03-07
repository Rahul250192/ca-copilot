import asyncio
import json
from sqlalchemy.future import select
from app.db.session import AsyncSessionLocal
from app.models.agreements import AgreementCategory, AgreementType

async def check():
    async with AsyncSessionLocal() as db:
        query = select(AgreementType)
        result = await db.execute(query)
        atypes = result.scalars().all()
        
        print(f"Found {len(atypes)} agreement types:")
        for at in atypes:
            print(f"- ID: {at.id}, Name: {at.name}, Path: {at.template_path}")
            if at.template_fields:
                print(f"  Fields: {json.dumps(at.template_fields)[:100]}...")

if __name__ == "__main__":
    asyncio.run(check())
