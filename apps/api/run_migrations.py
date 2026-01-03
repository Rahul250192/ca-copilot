
import os
import sys
from alembic.config import Config
from alembic import command
from dotenv import load_dotenv

# Load env from root
dotenv_path = "/Users/rahulgupta/ca-copilot/.env"
load_dotenv(dotenv_path)

# Verify ENV loaded
if not os.getenv("DATABASE_URL") or not os.getenv("SECRET_KEY"):
    print("Error: DATABASE_URL or SECRET_KEY not found in env.")
    sys.exit(1)

# Run Alembic
alembic_cfg = Config("alembic.ini")
command.upgrade(alembic_cfg, "head")
print("Migration successful.")
