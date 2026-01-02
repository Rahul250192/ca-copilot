import httpx
import asyncio

async def test_client_id():
    # Test with a simple client creation and retrieval
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Login first
        login_response = await client.post(
            "http://localhost:8000/api/v1/auth/login",
            data={"username": "test@ca.com", "password": "password123"}
        )
        
        if login_response.status_code != 200:
            print(f"Login failed: {login_response.status_code}")
            return
            
        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get clients
        clients_response = await client.get(
            "http://localhost:8000/api/v1/clients/",
            headers=headers
        )
        
        if clients_response.status_code == 200:
            clients = clients_response.json()
            if clients:
                print("✓ Client API Response Structure:")
                print(f"  - id: {clients[0]['id']}")
                print(f"  - client_id: {clients[0].get('client_id', 'MISSING!')}")
                print(f"  - name: {clients[0]['name']}")
                print(f"  - gst_number: {clients[0].get('gst_number', 'None')}")
                print(f"  - services: {len(clients[0].get('services', []))} services")
            else:
                print("No clients found")
        else:
            print(f"Failed to get clients: {clients_response.status_code}")
            print(clients_response.text)

if __name__ == "__main__":
    asyncio.run(test_client_id())
