from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings

# Depending on the driver, we might need to fix the scheme
# PostgresDsn might output postgres:// but asyncpg needs postgresql+asyncpg://
# However, we set it explicitly in settings usually.

import ssl

# Determine SSL requirement based on the host
is_local = "localhost" in settings.DATABASE_URL or "127.0.0.1" in settings.DATABASE_URL

connect_args = {
    "command_timeout": 60,
    "statement_cache_size": 0,
}

if not is_local:
    # Production/Supabase requires SSL but might use self-signed certs via pooler
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
    connect_args=connect_args
)

AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
