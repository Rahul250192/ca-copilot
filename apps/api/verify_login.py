import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from app.models.models import User
from app.core.config import settings
from app.core.security import verify_password

async def verify_user_login():
    engine = create_async_engine(settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        email = "test@example.com"
        password = "password123"
        
        print(f"Fetching user {email}...")
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        
        if not user:
            print("ERROR: User not found in DB!")
            return

        print(f"User found: {user.id}")
        print(f"Stored Hash: {user.hashed_password[:10]}...")
        
        is_valid = verify_password(password, user.hashed_password)
        if is_valid:
            print("SUCCESS: Password matches!")
        else:
            print("FAILURE: Password does NOT match.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_user_login())
