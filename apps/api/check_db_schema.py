import asyncio
from sqlalchemy import text
from app.db.session import engine

async def check_schema():
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'get_invoice';"))
            columns = result.fetchall()
            print("Columns in 'get_invoice' table:")
            for row in columns:
                print(f"- {row[0]}: {row[1]}")
            
            # Also check alembic_version
            res2 = await conn.execute(text("SELECT version_num FROM alembic_version;"))
            versions = res2.fetchall()
            print("\nAlembic versions in DB:")
            for v in versions:
                print(f"- {v[0]}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(check_schema())
