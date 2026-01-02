#!/bin/bash
# CA-Copilot Full Workflow Test Script

API_URL="http://localhost:8000/api/v1"

echo "🎯 Starting CA-Copilot Workflow Test..."

# 1. Signup
echo "👤 Signing up firm owner..."
signup_resp=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/auth/signup" \
  -H "Content-Type: application/json" \
  -d '{"email": "test@ca.com", "password": "password123", "full_name": "Test CA", "firm_name": "Test Firm"}')
signup_status=$(echo "$signup_resp" | tail -n 1)
if [ "$signup_status" -ne 200 ] && [ "$signup_status" -ne 400 ]; then
    echo "❌ Error: Signup failed with status $signup_status"
    echo "Response: $(echo "$signup_resp" | sed '$d')"
    exit 1
fi
echo "✅ Signup complete (or already exists)."

# 2. Login
echo "🔑 Logging in..."
login_resp=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/auth/login" \
  -d "username=test@ca.com&password=password123")
login_status=$(echo "$login_resp" | tail -n 1)

if [ "$login_status" -ne 200 ]; then
    echo "❌ Error: Login failed with status $login_status"
    echo "Response: $(echo "$login_resp" | sed '$d')"
    exit 1
fi

TOKEN=$(echo "$login_resp" | sed '$d' | jq -r .access_token)
echo "✅ Token obtained."

# 3. Create Client
echo "🏢 Creating client..."
client_resp=$(curl -s -X POST "$API_URL/clients/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Alpha Corp"}')
CLIENT_ID=$(echo "$client_resp" | jq -r .id)
if [ "$CLIENT_ID" == "null" ] || [ -z "$CLIENT_ID" ]; then
    echo "❌ Error: Failed to create client."
    echo "Response: $client_resp"
    exit 1
fi
echo "✅ Client created: $CLIENT_ID"

# 4. Get GST Kit
echo "📦 Fetching GST Kit..."
kits_resp=$(curl -s "$API_URL/kits/" -H "Authorization: Bearer $TOKEN")
KIT_ID=$(echo "$kits_resp" | jq -r '.[] | select(.name=="GST") | .id')
echo "✅ GST Kit ID: $KIT_ID"

# 5. Create Service
echo "🛠 Creating GST Service..."
service_resp=$(curl -s -X POST "$API_URL/services/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"GST Premium Service\", \"description\": \"Full GST compliance layer\", \"kit_ids\": [\"$KIT_ID\"]}")
SERVICE_ID=$(echo "$service_resp" | jq -r .id)
echo "✅ Service created: $SERVICE_ID"

# 6. Link Service to Client
echo "🔗 Linking Service to Client..."
curl -s -X PUT "$API_URL/clients/$CLIENT_ID/services" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "[\"$SERVICE_ID\"]"
echo "✅ Service linked to Client."

# 7. Verify Client List (with nested Services & Kits)
echo "🔍 Verifying Client -> Service -> Kit nesting..."
client_check=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_URL/clients/$CLIENT_ID")
service_name=$(echo "$client_check" | jq -r '.services[0].name')
kit_name=$(echo "$client_check" | jq -r '.services[0].kits[0].name')
echo "✅ Client '$CLIENT_NAME' has Service '$service_name' with Kit '$kit_name'."

# 6. Create Conversation with Service
echo "💬 Creating conversation (Auto-attaching Kits via Service)..."
conv_resp=$(curl -s -X POST "$API_URL/conversations/" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\": \"Tax Consultation\", \"client_id\": \"$CLIENT_ID\", \"service_id\": \"$SERVICE_ID\"}")
CONV_ID=$(echo "$conv_resp" | jq -r .id)
if [ "$CONV_ID" == "null" ] || [ -z "$CONV_ID" ]; then
    echo "❌ Error: Failed to create conversation."
    echo "Response: $conv_resp"
    exit 1
fi
echo "✅ Conversation created: $CONV_ID"

# 7. Seed Sample Knowledge
echo "🌱 Seeding sample knowledge across 3 layers..."
# Running this via docker compose. Path is absolute based on Dockerfile WORKDIR /app
docker compose exec -T api python /app/apps/api/scripts/seed_samples.py
echo "✅ Knowledge seeded."

# 8. Chat - The specialized specialist test
echo "🤖 Sending chat message..."
echo "Question: 'What are my GST filing dates for my FIFO client and what is the onboarding policy?'"
echo "--------------------------------------------------"
curl -s -X POST "$API_URL/conversations/$CONV_ID/chat" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "What are my GST filing dates for my FIFO client and what is the onboarding policy?"}' | jq .
echo "--------------------------------------------------"

echo "🚀 Test Flow Complete!"
