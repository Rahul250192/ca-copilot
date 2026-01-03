import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.models.models import Service # Adjust imports based on path
from app.core.config import settings

SERVICES_TO_ADD = [
    {"name": "GST Refund", "description": "Automated GST refund filing and reconciliation"},
    {"name": "Income Tax", "description": "ITR filing for individuals and businesses"},
    {"name": "Audit", "description": "Statutory and internal audit services"},
    {"name": "GST Filing", "description": "Monthly/Quarterly GST return filing"},
    {"name": "Compliance", "description": "General regulatory compliance management"},
    {"name": "Payroll", "description": "Payroll processing and PF/ESI compliance"},
    {"name": "Company Law", "description": "ROC filings and company law matters"},
    {"name": "Accounting", "description": "Professional bookkeeping and accounting services"},
]

async def seed_services():
    # Use config database URL
    engine = create_async_engine(settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        print("Checking existing services...")
        
        for svc_data in SERVICES_TO_ADD:
            result = await session.execute(select(Service).where(Service.name == svc_data["name"]))
            existing = result.scalars().first()
            
            if existing:
                print(f"Service '{svc_data['name']}' already exists.")
            else:
                print(f"Adding Service '{svc_data['name']}'...")
                new_service = Service(
                    name=svc_data["name"],
                    description=svc_data["description"]
                )
                session.add(new_service)
        
        await session.commit()
        print("Seeding complete!")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_services())
