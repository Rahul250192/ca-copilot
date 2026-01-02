import httpx
import sys

API_URL = "http://localhost:8000/api/v1"
EMAIL = "test@ca.com"
PASSWORD = "password123"

def test_gst_retrieval():
    print("🔑 Logging in...")
    resp = httpx.post(f"{API_URL}/auth/login", data={"username": EMAIL, "password": PASSWORD})
    token = resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Get Client and GST Kit
    print("🏢 Fetching Client ID...")
    clients = httpx.get(f"{API_URL}/clients/", headers=headers).json()
    client_id = clients[0]["id"]
    
    print("📦 Fetching GST Kit ID...")
    kits = httpx.get(f"{API_URL}/kits/", headers=headers).json()
    gst_kit = next(k for k in kits if k["name"] == "GST")
    kit_id = gst_kit["id"]

    # 2. Find Service or Create Conversation
    # Let's just create a direct conversation and attach the GST kit
    print("💬 Creating Conversation...")
    conv_resp = httpx.post(
        f"{API_URL}/conversations/",
        headers=headers,
        json={"title": "GST Knowledge Test", "client_id": client_id}
    ).json()
    conv_id = conv_resp["id"]
    
    print("🔗 Attaching GST Kit...")
    httpx.put(f"{API_URL}/conversations/{conv_id}/kits", headers=headers, json=[kit_id])

    # 3. Chat
    print("🌐 Sending Question: 'What is GST for beginners?'")
    chat_resp = httpx.post(
        f"{API_URL}/conversations/{conv_id}/chat",
        headers=headers,
        json={"content": "What is GST for beginners?"},
        timeout=60
    )
    
    if chat_resp.status_code == 200:
        print("\n🤖 AI Response:")
        print(chat_resp.json()["content"])
        print("\n📑 Citations provided in response:")
        for cit in chat_resp.json().get("citations", []):
            print(f"- [Scope: {cit['scope']}] Document ID: {cit['document_id']}")
    else:
        print(f"❌ Chat failed: {chat_resp.text}")

if __name__ == "__main__":
    test_gst_retrieval()
