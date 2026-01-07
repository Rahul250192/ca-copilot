#!/bin/sh
set -e

echo "🚀 Starting CA-Copilot Backend..."

# 1. Run migrations
echo "⚙️  Running database migrations..."
cd /app/apps/api
alembic upgrade head

# 2. Seed basic data (Kits)
echo "🌱 Seeding initial kits..."
python scripts/seed_data.py

# 3. Start Background Worker (Free Tier Optimization)
echo "👷 Starting Background Worker..."
python /app/apps/api/app/worker/main.py &

# 4. Start application
echo "📡 Launching Uvicorn..."
if [ "$APP_RELOAD" = "true" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --reload --proxy-headers --forwarded-allow-ips='*'
else
    exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
fi
