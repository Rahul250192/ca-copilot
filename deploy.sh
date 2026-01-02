#!/bin/bash
# CA-Copilot Deployment Helper

echo "🚀 Starting CA-Copilot Deployment..."

# 1. Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Generating a zero-config .env with random secrets..."
    
    # Generate random 32-char strings
    RAND_DB_PASS=$(openssl rand -hex 16)
    RAND_SECRET_KEY=$(openssl rand -hex 32)
    
    # Create .env from template
    cat <<EOF > .env
DATABASE_URL=postgresql+asyncpg://postgres:${RAND_DB_PASS}@db:5432/cacopilot
POSTGRES_USER=postgres
POSTGRES_PASSWORD=${RAND_DB_PASS}
POSTGRES_DB=cacopilot
SECRET_KEY=${RAND_SECRET_KEY}
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=11520
BACKEND_CORS_ORIGINS=["*"]
EOF
    echo "✅ Generated secure random secrets in .env"
fi

# 2. Pull latest images (if using a registry) or build
echo "📦 Building services..."
docker compose -f docker-compose.prod.yml build

# 3. Start services
echo "⚡ Starting services in detached mode..."
docker compose -f docker-compose.prod.yml up -d

echo "✅ Deployment complete!"
echo "📡 API is running at http://localhost:8000"
echo "🔍 Monitor logs with: docker compose -f docker-compose.prod.yml logs -f api"
