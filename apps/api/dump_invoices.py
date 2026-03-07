import asyncio, asyncpg, json
from app.core.config import settings

async def main():
    url = settings.DATABASE_URL.replace("postgresql://", "postgres://").replace("+asyncpg", "").replace(":6543", ":5432")
    conn = await asyncpg.connect(url)
    invoices = await conn.fetch("SELECT * FROM get_invoice")
    
    out = []
    for inv in invoices:
        out.append(dict(inv))
    
    with open("invoices_dump.json", "w") as f:
        # datetime needs string conversion
        for o in out:
            for k,v in o.items():
                if hasattr(v, 'isoformat'):
                    o[k] = v.isoformat()
        json.dump(out, f, indent=2)
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
