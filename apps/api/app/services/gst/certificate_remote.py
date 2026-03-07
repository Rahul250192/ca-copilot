from typing import List, Dict, Optional
from app.services.storage import storage_service
from app.core.config import settings
import os

BUCKET_NAME = "certificate-template"

def get_remote_templates(category: str = "") -> List[Dict[str, str]]:
    """
    Lists all templates in the certificate-template bucket, optionally filtered by category.
    """
    if not storage_service.supabase.enabled:
        print("⚠️ Supabase storage not enabled – check SUPABASE_URL/KEY in .env")
        return []

    try:
        # Pass the category as the path to list (empty string lists root)
        folder_path = category.strip()
        files = storage_service.supabase.client.storage.from_(BUCKET_NAME).list(folder_path)
        print(f"📂 Supabase bucket '{BUCKET_NAME}' folder '{folder_path}' files: {files}")

        template_list = []
        for file in files:
            name = file.get("name")
            # Supabase sometimes returns '.emptyFolderPlaceholder'
            if name and not name.startswith("."):
                ext = os.path.splitext(name)[1].lower()
                if ext in ('.docx', '.pdf', '.html'):
                    full_path = f"{folder_path}/{name}" if folder_path else name
                    template_list.append({
                        "name": name,
                        "path": full_path,
                        "extension": ext,
                        "updated_at": file.get("updated_at")
                    })
        return template_list
    except Exception as e:
        print(f"❌ Error listing remote templates for category '{category}': {e}")
        return []

def get_remote_template_url(filename: str) -> Optional[str]:
    """
    Generates a signed URL for a specific template.
    """
    if not storage_service.supabase.enabled:
        return None

    try:
        res = storage_service.supabase.client.storage.from_(BUCKET_NAME).create_signed_url(filename, 3600)
        print(f"🔗 Signed URL response for '{filename}': {res}")
        # Handle different Supabase client versions
        url = res.get("signedURL") or res.get("signedUrl") or res.get("signed_url")
        return url
    except Exception as e:
        print(f"❌ Error getting signed URL for {filename}: {e}")
        return None
