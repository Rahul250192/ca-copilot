import asyncio
import json
from sqlalchemy.future import select
from app.db.session import AsyncSessionLocal
from app.models.agreements import AgreementType

async def check():
    async with AsyncSessionLocal() as db:
        for name in ["Employment Agreement", "Rent / Lease Agreement"]:
            query = select(AgreementType).where(AgreementType.name == name)
            result = await db.execute(query)
            at = result.scalars().first()
            if at:
                print(f"\n--- {at.name} ---")
                print(json.dumps(at.template_fields, indent=2))

if __name__ == "__main__":
    asyncio.run(check())
