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

    def _find_or_create_folder(self, folder_name: str, parent_id: str) -> Optional[str]:
        query = f"name = '{folder_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        try:
            results = self.service.files().list(
                q=query, 
                fields="files(id)",
                supportsAllDrives=True,
                includeItemsFromAllDrives=True
            ).execute()
            items = results.get('files', [])
            if items:
                return items[0]['id']
            
            # Create if not exists
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [parent_id]
            }
            folder = self.service.files().create(
                body=file_metadata, 
                fields='id',
                supportsAllDrives=True
            ).execute()
            return folder.get('id')
        except Exception as e:
            print(f"Drive Folder Error: {e}")
            return None

    def upload_file(self, file_content: bytes, path: str, content_type: str = "application/octet-stream") -> Optional[str]:
        if not self.enabled or not self.service:
            return None
        
        try:
            # Hierarchy: path is like "Firm Name/Jobs/Temp/file.zip" or "jobs/temp/id/file"
            # We want to create folders for directories in 'path' relative to self.folder_id
            
            parts = path.strip("/").split("/")
            filename = parts[-1]
            folders = parts[:-1]
            
            current_parent_id = self.folder_id
            
            # Traverse/Create folders
            if current_parent_id:
                for folder_name in folders:
                    next_id = self._find_or_create_folder(folder_name, current_parent_id)
                    if next_id:
                        current_parent_id = next_id
                    else:
                        print(f"Could not create folder {folder_name}")
                        # Fallback to current parent
                        break
            
            file_metadata = {
                'name': filename,
                'parents': [current_parent_id] if current_parent_id else []
            }
            
            media = MediaIoBaseUpload(io.BytesIO(file_content), mimetype=content_type, resumable=True)
            
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink',
                supportsAllDrives=True
            ).execute()
            
            # Return the Drive File ID 
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


class LocalStorageService:
    def __init__(self):
        self.enabled = True
        self.base_path = os.path.join(os.getcwd(), "uploads")
        if not os.path.exists(self.base_path):
            os.makedirs(self.base_path)
        print(f"📂 Local Storage initialized at: {self.base_path}")

    def upload_file(self, file_content: bytes, path: str, bucket: Optional[str] = None, content_type: str = "application/octet-stream") -> Optional[str]:
        try:
            # Construct full local path
            # path e.g. "jobs/temp/firm_id/filename"
            full_path = os.path.join(self.base_path, path)
            dir_name = os.path.dirname(full_path)
            
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)
                
            with open(full_path, "wb") as f:
                f.write(file_content)
                
            return full_path
        except Exception as e:
            print(f"Local Upload Error: {e}")
            return None

    def download_to_temp(self, path: str, bucket: Optional[str] = None) -> Optional[str]:
        try:
            # Check if path is absolute (result of previous upload) or relative
            if os.path.isabs(path):
                source_path = path
            else:
                source_path = os.path.join(self.base_path, path)
            
            if not os.path.exists(source_path):
                print(f"File not found: {source_path}")
                return None

            suffix = os.path.splitext(source_path)[1]
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            
            with open(source_path, "rb") as src, open(temp_file.name, "wb") as dst:
                dst.write(src.read())
            
            return temp_file.name
        except Exception as e:
            print(f"Local Download Error: {e}")
            return None

    def delete_file(self, path: str, bucket: Optional[str] = None) -> bool:
        try:
            if os.path.isabs(path):
                target_path = path
            else:
                target_path = os.path.join(self.base_path, path)
                
            if os.path.exists(target_path):
                os.remove(target_path)
                return True
            return False
        except Exception:
            return False


class StorageService:
    def __init__(self):
        self.provider = settings.STORAGE_PROVIDER
        print(f"🗄️ Storage Provider: {self.provider}")
        
        self.supabase = SupabaseStorageService()
        self.gdrive = GoogleDriveService()
        self.local = LocalStorageService()

    def upload_file(self, file_content: bytes, path: str, bucket: Optional[str] = None, content_type: str = "application/octet-stream") -> Optional[str]:
        if self.provider == "google_drive":
            return self.gdrive.upload_file(file_content, path, content_type)
        elif self.provider == "local":
            return self.local.upload_file(file_content, path, bucket, content_type)
        else:
            return self.supabase.upload_file(file_content, path, bucket, content_type)

    def download_to_temp(self, path: str, bucket: Optional[str] = None) -> Optional[str]:
        if self.provider == "google_drive":
            return self.gdrive.download_to_temp(path)
        elif self.provider == "local":
            return self.local.download_to_temp(path, bucket)
        else:
            return self.supabase.download_to_temp(path, bucket)

    def delete_file(self, path: str, bucket: Optional[str] = None) -> bool:
        if self.provider == "google_drive":
            return self.gdrive.delete_file(path)
        elif self.provider == "local":
            return self.local.delete_file(path, bucket)
        else:
            return self.supabase.delete_file(path, bucket)

# Singleton instance
storage_service = StorageService()
