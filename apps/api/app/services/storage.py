import os
import tempfile
import io
from typing import Optional
from app.core.config import settings

# --- Google Drive Dependencies ---
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    GOOGLE_AVAILABLE = True
except ImportError:
    GOOGLE_AVAILABLE = False
    print("Google Drive dependencies not found. Install google-api-python-client google-auth")

# --- Supabase Dependencies ---
try:
    from supabase import create_client, Client as SupabaseClient
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False


class GoogleDriveService:
    def __init__(self):
        self.enabled = False
        self.service = None
        self.folder_id = settings.GOOGLE_DRIVE_FOLDER_ID
        
        if GOOGLE_AVAILABLE and settings.GOOGLE_CREDENTIALS_PATH and os.path.exists(settings.GOOGLE_CREDENTIALS_PATH):
            try:
                creds = service_account.Credentials.from_service_account_file(
                    settings.GOOGLE_CREDENTIALS_PATH, 
                    scopes=['https://www.googleapis.com/auth/drive']
                )
                self.service = build('drive', 'v3', credentials=creds)
                self.enabled = True
                print("✅ Google Drive Service Initialized")
            except Exception as e:
                print(f"❌ Failed to init Google Drive: {e}")

    def upload_file(self, file_content: bytes, path: str, content_type: str = "application/octet-stream") -> Optional[str]:
        if not self.enabled or not self.service:
            return None
        
        try:
            # 1. Create file metadata
            # Note: Path "folder/file" mapping to Drive Folders is complex. 
            # Simplified: We just upload everything to the Root Folder with the filename = path
            # Or better: We specifically put it in the configured folder.
            
            # Simple approach: Flatten path slashes to dashes for filename uniqueness
            filename = path.replace("/", "_")
            
            file_metadata = {
                'name': filename,
                'parents': [self.folder_id] if self.folder_id else []
            }
            
            media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype=content_type, resumable=True)
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()
            
            print(f"Uploaded to Drive: ID={file.get('id')}")
            # Return the Drive File ID as the "path" for future reference
            return file.get('id')
            
        except Exception as e:
            print(f"Google Drive Upload Error: {e}")
            return None

    def download_to_temp(self, file_id: str) -> Optional[str]:
        if not self.enabled: 
            return None
            
        try:
            # 1. Get file metadata to determine extension
            meta = self.service.files().get(fileId=file_id, fields='name').execute()
            filename = meta.get('name', 'file.pdf')
            suffix = os.path.splitext(filename)[1]
            if not suffix:
                suffix = ".pdf"

            # 2. Download content
            request = self.service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
                
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            temp_file.write(fh.getvalue())
            temp_file.close()
            return temp_file.name
        except Exception as e:
            # Maybe it's not a file ID but a path? (Fallback logic if needed)
            print(f"Google Drive Download Error: {e}")
            return None

    def delete_file(self, file_id: str) -> bool:
        if not self.enabled: return False
        try:
            self.service.files().delete(fileId=file_id).execute()
            return True
        except Exception as e:
            print(f"Google Drive Delete Error: {e}")
            return False


class SupabaseStorageService:
    def __init__(self):
        self.enabled = False
        if SUPABASE_AVAILABLE and settings.SUPABASE_URL and settings.SUPABASE_KEY:
            try:
                self.client: SupabaseClient = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
                self.enabled = True
                # Auto-create buckets
                buckets = [settings.SUPABASE_BUCKET, "client-context"]
                for b in buckets:
                    try:
                        self.client.storage.create_bucket(b, options={"public": True})
                    except Exception:
                        pass 
            except Exception as e:
                print(f"Failed to init Supabase: {e}")
        
    def upload_file(self, file_content: bytes, path: str, bucket: Optional[str] = None, content_type: str = "application/octet-stream") -> Optional[str]:
        if not self.enabled: return None
        target_bucket = bucket or settings.SUPABASE_BUCKET
        try:
            clean_path = path.lstrip("/")
            self.client.storage.from_(target_bucket).upload(
                path=clean_path,
                file=file_content,
                file_options={"content-type": content_type, "upsert": "true"}
            )
            return clean_path
        except Exception as e:
            print(f"Supabase Upload Error: {e}")
            return None

    def download_to_temp(self, path: str, bucket: Optional[str] = None) -> Optional[str]:
        if not self.enabled: return None
        target_bucket = bucket or settings.SUPABASE_BUCKET
        try:
            clean_path = path.lstrip("/")
            res = self.client.storage.from_(target_bucket).download(clean_path)
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            temp_file.write(res)
            temp_file.close()
            return temp_file.name
        except Exception as e:
            print(f"Supabase Download Error: {e}")
            return None

    def delete_file(self, path: str, bucket: Optional[str] = None) -> bool:
        if not self.enabled: return False
        target_bucket = bucket or settings.SUPABASE_BUCKET
        try:
            clean_path = path.lstrip("/")
            self.client.storage.from_(target_bucket).remove([clean_path])
            return True
        except Exception:
            return False


class StorageService:
    def __init__(self):
        self.provider = settings.STORAGE_PROVIDER
        print(f"🗄️ Storage Provider: {self.provider}")
        
        self.supabase = SupabaseStorageService()
        self.gdrive = GoogleDriveService()

    def upload_file(self, file_content: bytes, path: str, bucket: Optional[str] = None, content_type: str = "application/octet-stream") -> Optional[str]:
        if self.provider == "google_drive":
            # For Drive, we ignore buckets and just use the specific folder
            return self.gdrive.upload_file(file_content, path, content_type)
        else:
            return self.supabase.upload_file(file_content, path, bucket, content_type)

    def download_to_temp(self, path: str, bucket: Optional[str] = None) -> Optional[str]:
        if self.provider == "google_drive":
            # Path is assumed to be File ID for Drive
            return self.gdrive.download_to_temp(path)
        else:
            return self.supabase.download_to_temp(path, bucket)

    def delete_file(self, path: str, bucket: Optional[str] = None) -> bool:
        if self.provider == "google_drive":
            return self.gdrive.delete_file(path)
        else:
            return self.supabase.delete_file(path, bucket)

# Singleton instance
storage_service = StorageService()
