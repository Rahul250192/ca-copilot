from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


# ── Folder Schemas ──

class DriveFolderCreate(BaseModel):
    name: str
    icon: str = "📁"
    color: str = "#3b82f6"
    bg: str = "#eff6ff"


class DriveFolderUpdate(BaseModel):
    name: Optional[str] = None
    icon: Optional[str] = None
    color: Optional[str] = None
    bg: Optional[str] = None


class DriveFolder(BaseModel):
    id: UUID
    client_id: UUID
    firm_id: UUID
    parent_id: Optional[UUID] = None
    name: str
    icon: str
    color: str
    bg: str
    created_at: datetime
    file_count: Optional[int] = 0
    total_size: Optional[int] = 0
    has_children: Optional[bool] = False

    class Config:
        from_attributes = True


# ── File Schemas ──

class DriveFileCreate(BaseModel):
    folder_id: UUID
    name: Optional[str] = None  # auto from upload


class DriveFile(BaseModel):
    id: UUID
    folder_id: UUID
    client_id: UUID
    firm_id: UUID
    name: str
    original_name: str
    file_type: str
    size_bytes: int
    storage_path: str
    created_at: datetime

    class Config:
        from_attributes = True


# ── Stats ──

class DriveStats(BaseModel):
    total_folders: int
    total_files: int
    total_size_bytes: int
    last_updated: Optional[datetime] = None
