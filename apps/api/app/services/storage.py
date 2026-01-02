import os
import tempfile
from typing import Optional
from supabase import create_client, Client
from app.core.config import settings

class StorageService:
    def __init__(self):
        self.enabled = False
        if settings.SUPABASE_URL and settings.SUPABASE_KEY:
            try:
                self.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
                self.enabled = True
                
                # Auto-create buckets
                buckets = [settings.SUPABASE_BUCKET, "client-context"]
                for b in buckets:
                    try:
                        self.client.storage.create_bucket(
                            b, 
                            options={"public": True}
                        )
                        print(f"Created Supabase bucket: {b}")
                    except Exception as e:
                        if "already exists" not in str(e).lower():
                            print(f"Note on bucket check {b}: {e}")
            except Exception as e:
                print(f"Failed to initialize Supabase client: {e}")
                self.client = None
        else:
            self.client = None

    def upload_file(self, file_content: bytes, path: str, bucket: Optional[str] = None, content_type: str = "application/octet-stream") -> Optional[str]:
        """
        Uploads a file to Supabase Storage and returns the path.
        """
        if not self.enabled:
            print("Supabase Storage is disabled. Please set SUPABASE_URL and SUPABASE_KEY.")
            return None
        
        target_bucket = bucket or settings.SUPABASE_BUCKET
        try:
            # Standardizing path: ensure no leading slash
            clean_path = path.lstrip("/")
            
            # Use upsert=True to allow overwriting if needed
            self.client.storage.from_(target_bucket).upload(
                path=clean_path,
                file=file_content,
                file_options={"content-type": content_type, "upsert": "true"}
            )
            return clean_path
        except Exception as e:
            print(f"Error uploading file to Supabase: {e}")
            return None

    def download_to_temp(self, path: str, bucket: Optional[str] = None) -> Optional[str]:
        """
        Downloads a file from Supabase and saves it to a temporary local file.
        Returns the local path.
        """
        if not self.enabled:
            return None
        
        target_bucket = bucket or settings.SUPABASE_BUCKET
        try:
            clean_path = path.lstrip("/")
            res = self.client.storage.from_(target_bucket).download(clean_path)
            
            # Create a temporary file
            suffix = os.path.splitext(path)[1]
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_file.write(res)
            temp_file.close()
            
            return temp_file.name
        except Exception as e:
            print(f"Error downloading file from Supabase: {e}")
            return None

    def delete_file(self, path: str, bucket: Optional[str] = None) -> bool:
        """
        Deletes a file from Supabase Storage.
        """
        if not self.enabled:
            return False
        
        target_bucket = bucket or settings.SUPABASE_BUCKET
        try:
            clean_path = path.lstrip("/")
            self.client.storage.from_(target_bucket).remove([clean_path])
            return True
        except Exception as e:
            print(f"Error deleting file from Supabase: {e}")
            return False

# Singleton instance
storage_service = StorageService()
