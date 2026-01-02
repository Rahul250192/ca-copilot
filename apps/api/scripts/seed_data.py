import asyncio
import uuid
from sqlalchemy.future import select
from app.db.session import AsyncSessionLocal
from app.models.models import Kit, User, Firm, UserRole
from app.core.security import get_password_hash

async def seed_data():
    async with AsyncSessionLocal() as db:
        # Check if Kits already exist
        result = await db.execute(select(Kit).limit(1))
        if result.scalars().first():
            print("Data already seeded. Skipping...")
            return

        print("Seeding initial Knowledge Kits...")
        kits = [
            Kit(name="GST", description="Goods and Services Tax Specialist Knowledge"),
            Kit(name="Income Tax", description="Taxation and Filing Specialist Knowledge"),
            Kit(name="Audit", description="Statutory and Internal Audit Specialist Knowledge"),
            Kit(name="ROC", description="Company Law and Compliance Specialist Knowledge"),
        ]
        db.add_all(kits)
        
        # Optional: Create a default firm/admin if you want it automated
        # firm = Firm(name="Default Firm")
        # db.add(firm)
        # await db.flush()
        # admin = User(
        #     email="admin@cacopilot.ai",
        #     hashed_password=get_password_hash("admin123"),
        #     role=UserRole.OWNER,
        #     firm_id=firm.id
        # )
        # db.add(admin)

        await db.commit()
        print("Initial Kits created successfully.")

if __name__ == "__main__":
    asyncio.run(seed_data())
