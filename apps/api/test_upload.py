import asyncio
import httpx
import os
from app.core.config import settings

BASE_URL = "http://localhost:8000/api/v1"

async def test_upload():
    # 1. Login to get token
    email = "test@example.com"
    password = "password123"
    
    print(f"Logging in as {email}...")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/auth/login",
            data={"username": email, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        if resp.status_code != 200:
            print(f"Login Failed: {resp.text}")
            return
        token = resp.json()["access_token"]
        print("Login Success.")

    # 2. Upload a dummy file
    headers = {"Authorization": f"Bearer {token}"}
    files = {'file': ('test_doc.txt', b'This is a test file content', 'text/plain')}
    
    print("Uploading file to /jobs/upload ...")
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"{BASE_URL}/jobs/upload",
                headers=headers,
                files=files
            )
            print(f"Status: {resp.status_code}")
            print(f"Response: {resp.text}")
        except Exception as e:
            print(f"Request Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_upload())
