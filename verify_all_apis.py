import httpx
import os
import json
import time

BASE_URL = "https://ca-copilot-api.onrender.com/api/v1"
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3Njc3OTk5OTMsInN1YiI6IjlmODFiYmQxLTZlZjUtNGY0MC1iODI0LTJiYWJlZDVmNmY0MSJ9.9PE6JEx6tKxYp3zQmpKmECTQe5sG1g4UfBjF2QIJoY8"

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

def log_test(name, response):
    status = "SUCCESS" if response.status_code < 400 else "FAILED"
    print(f"[{status}] {name} - Status: {response.status_code}")
    if response.status_code >= 400:
        print(f"      Error: {response.text}")
    return response.status_code < 400

async def run_tests():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("\n--- Starting Positive Test Suite ---\n")

        # 1. Auth Me
        r = await client.get(f"{BASE_URL}/auth/me", headers=headers)
        if not log_test("GET /auth/me", r): return
        user_info = r.json()
        print(f"      User: {user_info['email']} | Firm: {user_info['firm_id']}")

        # 2. List Kits
        r = await client.get(f"{BASE_URL}/kits/", headers=headers)
        log_test("GET /kits/", r)

        # 3. Create Kit
        kit_data = {"name": f"Test Kit {int(time.time())}", "description": "Verification Kit"}
        r = await client.post(f"{BASE_URL}/kits/", headers=headers, json=kit_data)
        if not log_test("POST /kits/ (Create)", r): return
        kit_id = r.json()["id"]

        # 4. Create Service
        svc_data = {"name": f"Test Service {int(time.time())}", "description": "Verification Service", "kit_ids": [kit_id]}
        r = await client.post(f"{BASE_URL}/services/", headers=headers, json=svc_data)
        if not log_test("POST /services/ (Create)", r): return
        service_id = r.json()["id"]

        # 5. Create Client
        client_data = {"name": f"Verification Corp {int(time.time())}"}
        r = await client.post(f"{BASE_URL}/clients/", headers=headers, json=client_data)
        if not log_test("POST /clients/ (Create)", r): return
        client_id = r.json()["id"]

        # 6. Attach Service to Client
        r = await client.put(f"{BASE_URL}/clients/{client_id}/services", headers=headers, json=[service_id])
        log_test("PUT /clients/{id}/services (Attach)", r)

        # 7. Get Client Services
        r = await client.get(f"{BASE_URL}/clients/{client_id}/services", headers=headers)
        log_test("GET /clients/{id}/services (Verify)", r)

        # 8. Upload Client Document (using dummy content)
        # We'll create a tiny dummy file for the test
        files = {"file": ("test.txt", b"Verification content for client context", "text/plain")}
        data = {"title": "Test Client Doc"}
        r = await client.post(f"{BASE_URL}/clients/{client_id}/upload", headers=headers, files=files, data=data)
        log_test("POST /clients/{id}/upload (Storage)", r)

        # 9. List Client Documents
        r = await client.get(f"{BASE_URL}/clients/{client_id}/documents", headers=headers)
        log_test("GET /clients/{id}/documents (List)", r)

        # 10. Global Upload for Kit
        files = {"file": ("kit_test.txt", b"Verification content for kit knowledge", "text/plain")}
        data = {"title": "Test Kit Doc", "scope": "KIT", "kit_id": kit_id}
        r = await client.post(f"{BASE_URL}/documents/upload", headers=headers, files=files, data=data)
        log_test("POST /documents/upload (KIT scope)", r)

        # 11. Create Conversation
        conv_data = {"title": "Verification Chat", "client_id": client_id}
        r = await client.post(f"{BASE_URL}/conversations/", headers=headers, json=conv_data)
        if not log_test("POST /conversations/ (Create)", r): return
        conv_id = r.json()["id"]

        # 12. Chat
        chat_data = {"content": "Hello, this is an automated verification check. How are you?"}
        r = await client.post(f"{BASE_URL}/conversations/{conv_id}/chat", headers=headers, json=chat_data)
        log_test("POST /conversations/{id}/chat (Talk)", r)
        if r.status_code == 200:
            print(f"      AI Response: {r.json()['content'][:100]}...")

        print("\n--- All Tests Completed ---")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_tests())
