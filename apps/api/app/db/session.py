import ssl
import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import text

from app.core.config import settings

logger = logging.getLogger(__name__)

# Determine SSL requirement based on the host
is_local = "localhost" in settings.DATABASE_URL or "127.0.0.1" in settings.DATABASE_URL

connect_args = {
    "command_timeout": 120,
    "statement_cache_size": 0,
    "timeout": 120,
    "server_settings": {
        "tcp_keepalives_idle": "600",
        "tcp_keepalives_interval": "30",
        "tcp_keepalives_count": "10",
    },
}

if not is_local:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    connect_args["ssl"] = ctx
else:
    connect_args["ssl"] = False

engine = create_async_engine(
    str(settings.DATABASE_URL),
    echo=False,
    future=True,
    poolclass=NullPool,
    connect_args=connect_args,
    pool_pre_ping=True,
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db():
    """DB dependency with automatic retry on connection failure."""
    last_err = None
    for attempt in range(3):
        try:
            async with AsyncSessionLocal() as session:
                yield session
                return
        except Exception as e:
            last_err = e
            if attempt < 2:
                wait = (attempt + 1) * 2  # 2s, 4s
                logger.warning(f"DB connection attempt {attempt+1} failed, retrying in {wait}s: {e}")
                await asyncio.sleep(wait)
            else:
                logger.error(f"DB connection failed after 3 attempts: {e}")
                raise last_err


async def warmup_db():
    """Pre-connect to DB on startup to avoid cold-start timeouts."""
    for attempt in range(5):
        try:
            async with AsyncSessionLocal() as session:
                await session.execute(text("SELECT 1"))
            logger.info("✅ Database warmup successful")
            return
        except Exception as e:
            wait = (attempt + 1) * 3
            logger.warning(f"DB warmup attempt {attempt+1}/5 failed: {e}. Retrying in {wait}s...")
            await asyncio.sleep(wait)
    logger.error("⚠️ Database warmup failed after 5 attempts — will retry on first request")
