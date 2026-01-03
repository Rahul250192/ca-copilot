import asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.models.models import Firm, User, UserRole # Adjust imports based on path
from app.core.config import settings
from app.core.security import get_password_hash

async def create_user():
    # Use config database URL
    engine = create_async_engine(settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Check/Create Firm
        print("Checking for existing firm...")
        result = await session.execute(select(Firm).where(Firm.name == "Demo Firm").limit(1))
        firm = result.scalars().first()
        
        if not firm:
            print("Creating Demo Firm...")
            firm = Firm(name="Demo Firm")
            session.add(firm)
            await session.commit()
            await session.refresh(firm)
        
        print(f"Using Firm ID: {firm.id}")

        # 2. Check/Create User
        email = "test@example.com"
        print(f"Checking for user {email}...")
        result = await session.execute(select(User).where(User.email == email).limit(1))
        user = result.scalars().first()

        if not user:
            print("Creating User...")
            hashed_pwd = get_password_hash("password123")
            user = User(
                email=email,
                hashed_password=hashed_pwd,
                full_name="Test User",
                firm_id=firm.id,
                role=UserRole.ADMIN
            )
            session.add(user)
            await session.commit()
            print("User created successfully!")
        else:
            print("User already exists. Updating password...")
            hashed_pwd = get_password_hash("password123")
            user.hashed_password = hashed_pwd
            await session.commit()
            print("Password updated to 'password123'.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(create_user())
