import os, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text, create_engine

db_url = os.getenv('DATABASE_URL', '').replace('+asyncpg', '')
e = create_engine(db_url)
with e.connect() as conn:
    conn.execute(text("ALTER TABLE get_invoice ADD COLUMN IF NOT EXISTS synced_to_tally BOOLEAN DEFAULT FALSE"))
    conn.commit()
    print("Column added successfully!")
    
    r = conn.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='get_invoice' AND column_name='synced_to_tally'"))
    print(f"Verified: {[row[0] for row in r]}")
