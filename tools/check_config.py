import sys
import os
sys.path.append(os.getcwd())

from app.core.config import settings

print("--- Current Local Configuration ---")
print(f"STORAGE_PROVIDER: {settings.STORAGE_PROVIDER}")
print(f"GOOGLE_CREDENTIALS_PATH: {settings.GOOGLE_CREDENTIALS_PATH}")
print(f"GOOGLE_TOKEN_PATH: {os.getenv('GOOGLE_TOKEN_PATH', 'Not Set (Defaults to token.json)')}")
print(f"SUPABASE_URL: {settings.SUPABASE_URL}")
print(f"DATABASE_URL: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'HIDDEN'}")
print("--- Check Files ---")
print(f"credentials.json exists: {os.path.exists('credentials.json')}")
print(f"token.json exists: {os.path.exists('token.json')}")
