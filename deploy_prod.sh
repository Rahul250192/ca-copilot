#!/bin/bash
# CA-Copilot Production Deployment Script

echo "🚀 Starting Production Deployment..."

# 1. Check for .env file
if [ ! -f .env ]; then
    echo "⚠️  .env file not found! Creating from example..."
    cp .env.example .env
    echo "❌ Please edit .env and add your OPENAI_API_KEY, then run this script again."
    exit 1
fi

# 2. Pull latest changes
echo "📥 Pulling latest code..."
git pull origin main

# 3. Build and Start
echo "🏗 Building and starting containers..."
docker compose up -d --build

# 4. Success message
echo "✅ Deployment successful!"
echo "📡 API is running at: http://localhost:8000/api/v1"
echo "📜 View documentation at: http://localhost:8000/docs"
