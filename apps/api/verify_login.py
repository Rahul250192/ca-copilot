import asyncio
from sqlalchemy import select
from app.models.models import User
from app.core.security import verify_password
from app.db.session import AsyncSessionLocal, engine

async def verify_user_login():
    async with AsyncSessionLocal() as session:
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
