import asyncio
import httpx
import sys
from app.core import security
from app.models.models import User
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from datetime import timedelta

BASE_URL = "http://localhost:8000/api/v1"

async def test_api():
    email = "test@example.com"
    password = "password123"

    print(f"--- 1. Testing Login API ({BASE_URL}/auth/login) ---")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/auth/login",
                data={"username": email, "password": password},
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text}")
            
            if resp.status_code == 200:
                token = resp.json()["access_token"]
                print("Login SUCCESS. Got token.")
            else:
                print("Login FAILED.")
                token = None
        except Exception as e:
            print(f"Connection Error: {e}")
            token = None

    # If login failed, generate token manually to test services
    if not token:
        print("\n--- 2. Generating Manual Token for Testing ---")
        engine = create_async_engine(settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"))
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with async_session() as session:
            result = await session.execute(select(User).where(User.email == email))
            user = result.scalars().first()
            if user:
                access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
                token = security.create_access_token(user.id, expires_delta=access_token_expires)
                print(f"Generated Token for User ID: {user.id}")
            else:
                print("CRITICAL: User not found in DB for manual token generation.")
                await engine.dispose()
                return
        await engine.dispose()

    print(f"\n--- 3. Testing Services API ({BASE_URL}/services/) ---")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"{BASE_URL}/services/",
                headers={"Authorization": f"Bearer {token}"}
            )
            print(f"Status: {resp.status_code}")
            try:
                data = resp.json()
                print(f"Services Count: {len(data)}")
                print("Services List:", [s['name'] for s in data])
            except:
                print(f"Response: {resp.text}")

        except Exception as e:
            print(f"Connection Error: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(test_api())
    except ImportError:
        # Fallback if httpx not installed, but it should be
        print("httpx module missing. Install with: pip install httpx")
