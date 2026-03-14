"""
Client Drive — folder & file management.
Files stored under:  uploads/drive/{firm_id}/{client_id}/{folder_id}/{filename}
"""

import os
import uuid as _uuid
from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from fastapi.responses import FileResponse

from app.api import deps
from app.models.models import Client, User, DriveFolder, DriveFile
from app.schemas import drive as drive_schemas

router = APIRouter()

DRIVE_STORAGE_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "uploads", "drive")


def _file_type(filename: str) -> str:
    """Derive a file type category from extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".pdf",):
        return "pdf"
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"):
        return "image"
    if ext in (".xls", ".xlsx", ".csv"):
        return "spreadsheet"
    if ext in (".doc", ".docx"):
        return "doc"
    if ext in (".zip", ".rar", ".7z"):
        return "archive"
    return "other"


# ─────────────────────────────────── DEFAULT FOLDERS SEED ──
# Top-level folders
DEFAULT_FOLDERS = [
    {"name": "GST Inputs", "icon": "📥", "color": "#2563eb", "bg": "#eff6ff"},
    {"name": "GST Returns", "icon": "🧾", "color": "#059669", "bg": "#ecfdf5"},
    {"name": "Income Tax", "icon": "💰", "color": "#d97706", "bg": "#fef3c7"},
    {"name": "Invoices", "icon": "📝", "color": "#7c3aed", "bg": "#f5f3ff"},
    {"name": "CA Certificates", "icon": "📜", "color": "#1e3a8a", "bg": "#eff6ff"},
    {"name": "Agreements", "icon": "⚖️", "color": "#0f766e", "bg": "#f0fdfa"},
    {"name": "Banking", "icon": "🏦", "color": "#0369a1", "bg": "#e0f2fe"},
    {"name": "KYC Documents", "icon": "🛡️", "color": "#dc2626", "bg": "#fef2f2"},
    {"name": "Audit Reports", "icon": "🔍", "color": "#7c3aed", "bg": "#faf5ff"},
    {"name": "Miscellaneous", "icon": "📎", "color": "#64748b", "bg": "#f1f5f9"},
]

# Sub-folders inside "GST Inputs"
GST_INPUT_SUBFOLDERS = [
    {"name": "Purchase Register", "icon": "📥", "color": "#2563eb", "bg": "#eff6ff"},
    {"name": "Sales Register",    "icon": "📤", "color": "#7c3aed", "bg": "#f5f3ff"},
    {"name": "Shipping Bills",    "icon": "🚢", "color": "#0369a1", "bg": "#e0f2fe"},
    {"name": "BRC / FIRC",        "icon": "💵", "color": "#059669", "bg": "#ecfdf5"},
    {"name": "GSTR Downloads",    "icon": "📋", "color": "#d97706", "bg": "#fef3c7"},
    {"name": "E-Invoices",        "icon": "🧾", "color": "#dc2626", "bg": "#fef2f2"},
    {"name": "IMS Data",          "icon": "📄", "color": "#64748b", "bg": "#f1f5f9"},
]


async def _ensure_default_folders(
    db: AsyncSession, client_id: UUID, firm_id: UUID
):
    """Create default folders (and sub-folders) if missing.
    For existing clients, adds any folders that don't exist yet."""
    # Get existing folder names
    existing_q = select(DriveFolder.name, DriveFolder.id, DriveFolder.parent_id).where(
        DriveFolder.client_id == client_id,
        DriveFolder.firm_id == firm_id,
    )
    result = await db.execute(existing_q)
    existing = {(row.name, row.parent_id): row.id for row in result.all()}

    # 1. Create missing top-level folders
    gst_inputs_id = None
    for df in DEFAULT_FOLDERS:
        key = (df["name"], None)
        if key not in existing:
            folder = DriveFolder(
                client_id=client_id, firm_id=firm_id,
                name=df["name"], icon=df["icon"], color=df["color"], bg=df["bg"],
                parent_id=None,
            )
            db.add(folder)
            await db.flush()  # get the id
            if df["name"] == "GST Inputs":
                gst_inputs_id = folder.id
        else:
            if df["name"] == "GST Inputs":
                gst_inputs_id = existing[key]

    # 2. Create missing sub-folders under "GST Inputs"
    if gst_inputs_id:
        for sf in GST_INPUT_SUBFOLDERS:
            key = (sf["name"], gst_inputs_id)
            if key not in existing:
                sub = DriveFolder(
                    client_id=client_id, firm_id=firm_id,
                    name=sf["name"], icon=sf["icon"], color=sf["color"], bg=sf["bg"],
                    parent_id=gst_inputs_id,
                )
                db.add(sub)

    await db.commit()


# ─────────────────────────────────── FOLDERS ──

@router.get("/{client_id}/folders", response_model=List[drive_schemas.DriveFolder])
async def list_folders(
    client_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """List top-level drive folders for a client (auto-seeds defaults on first access)."""
    # Verify client ownership
    cq = select(Client).where(Client.id == client_id, Client.firm_id == current_user.firm_id)
    cr = await db.execute(cq)
    if not cr.scalars().first():
        raise HTTPException(status_code=404, detail="Client not found")

    await _ensure_default_folders(db, client_id, current_user.firm_id)

    # Only return top-level folders (parent_id IS NULL)
    query = (
        select(DriveFolder)
        .options(selectinload(DriveFolder.files), selectinload(DriveFolder.children))
        .where(
            DriveFolder.client_id == client_id,
            DriveFolder.firm_id == current_user.firm_id,
            DriveFolder.parent_id == None,
        )
        .order_by(DriveFolder.created_at)
    )
    result = await db.execute(query)
    folders = result.scalars().all()

    response = []
    for f in folders:
        response.append(drive_schemas.DriveFolder(
            id=f.id,
            client_id=f.client_id,
            firm_id=f.firm_id,
            parent_id=f.parent_id,
            name=f.name,
            icon=f.icon,
            color=f.color,
            bg=f.bg,
            created_at=f.created_at,
            file_count=len(f.files),
            total_size=sum(fi.size_bytes for fi in f.files),
            has_children=len(f.children) > 0,
        ))
    return response


@router.get("/{client_id}/folders/{folder_id}/subfolders", response_model=List[drive_schemas.DriveFolder])
async def list_subfolders(
    client_id: UUID,
    folder_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """List sub-folders inside a parent folder."""
    query = (
        select(DriveFolder)
        .options(selectinload(DriveFolder.files), selectinload(DriveFolder.children))
        .where(
            DriveFolder.client_id == client_id,
            DriveFolder.firm_id == current_user.firm_id,
            DriveFolder.parent_id == folder_id,
        )
        .order_by(DriveFolder.created_at)
    )
    result = await db.execute(query)
    folders = result.scalars().all()

    response = []
    for f in folders:
        response.append(drive_schemas.DriveFolder(
            id=f.id,
            client_id=f.client_id,
            firm_id=f.firm_id,
            parent_id=f.parent_id,
            name=f.name,
            icon=f.icon,
            color=f.color,
            bg=f.bg,
            created_at=f.created_at,
            file_count=len(f.files),
            total_size=sum(fi.size_bytes for fi in f.files),
            has_children=len(f.children) > 0,
        ))
    return response


@router.post("/{client_id}/folders", response_model=drive_schemas.DriveFolder)
async def create_folder(
    client_id: UUID,
    folder_in: drive_schemas.DriveFolderCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Create a new folder in the client drive."""
    cq = select(Client).where(Client.id == client_id, Client.firm_id == current_user.firm_id)
    cr = await db.execute(cq)
    if not cr.scalars().first():
        raise HTTPException(status_code=404, detail="Client not found")

    folder = DriveFolder(
        client_id=client_id,
        firm_id=current_user.firm_id,
        name=folder_in.name,
        icon=folder_in.icon,
        color=folder_in.color,
        bg=folder_in.bg,
    )
    db.add(folder)
    await db.commit()
    await db.refresh(folder)

    return drive_schemas.DriveFolder(
        id=folder.id,
        client_id=folder.client_id,
        firm_id=folder.firm_id,
        name=folder.name,
        icon=folder.icon,
        color=folder.color,
        bg=folder.bg,
        created_at=folder.created_at,
        file_count=0,
        total_size=0,
    )


@router.delete("/{client_id}/folders/{folder_id}")
async def delete_folder(
    client_id: UUID,
    folder_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Delete a folder and all its files."""
    q = select(DriveFolder).where(
        DriveFolder.id == folder_id,
        DriveFolder.client_id == client_id,
        DriveFolder.firm_id == current_user.firm_id,
    )
    result = await db.execute(q)
    folder = result.scalars().first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    await db.delete(folder)
    await db.commit()
    return {"status": "deleted"}


# ─────────────────────────────────── FILES ──

@router.get("/{client_id}/folders/{folder_id}/files", response_model=List[drive_schemas.DriveFile])
async def list_files(
    client_id: UUID,
    folder_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """List all files in a folder."""
    q = select(DriveFile).where(
        DriveFile.folder_id == folder_id,
        DriveFile.client_id == client_id,
        DriveFile.firm_id == current_user.firm_id,
    ).order_by(DriveFile.created_at.desc())
    result = await db.execute(q)
    return result.scalars().all()


# Mapping of GST Input sub-folder names → Supabase slug
GST_INPUT_FOLDER_SLUGS = {
    "Purchase Register": "purchase_register",
    "Sales Register": "sales_register",
    "Shipping Bills": "shipping_bills",
    "BRC / FIRC": "brc_firc",
    "GSTR Downloads": "gstr_downloads",
    "E-Invoices": "e_invoices",
    "IMS Data": "ims_data",
}

REPORTS_BUCKET = "reports"


def _get_supabase_storage():
    """Get the Supabase storage service (lazy import)."""
    try:
        from app.services.storage import storage_service
        if storage_service.supabase.enabled:
            return storage_service.supabase
        return None
    except Exception:
        return None


def _ensure_reports_bucket(supabase_svc):
    """Ensure the 'reports' bucket exists in Supabase."""
    try:
        supabase_svc.client.storage.create_bucket(REPORTS_BUCKET, options={"public": True})
    except Exception:
        pass  # Already exists


@router.post("/{client_id}/folders/{folder_id}/upload", response_model=drive_schemas.DriveFile)
async def upload_file(
    client_id: UUID,
    folder_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Upload a file into a drive folder. GST Input sub-folders save to Supabase."""
    # Verify folder ownership
    fq = select(DriveFolder).where(
        DriveFolder.id == folder_id,
        DriveFolder.client_id == client_id,
        DriveFolder.firm_id == current_user.firm_id,
    )
    fr = await db.execute(fq)
    folder = fr.scalars().first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    # Read file
    content = await file.read()
    size = len(content)

    # Unique filename to avoid collisions
    ext = os.path.splitext(file.filename)[1]
    unique_name = f"{_uuid.uuid4().hex[:12]}{ext}"

    storage_path = None

    # Check if this is a GST Input sub-folder (parent is "GST Inputs")
    is_gst_input = False
    if folder.parent_id and folder.name in GST_INPUT_FOLDER_SLUGS:
        # Verify parent is actually "GST Inputs"
        pq = select(DriveFolder).where(DriveFolder.id == folder.parent_id)
        pr = await db.execute(pq)
        parent = pr.scalars().first()
        if parent and parent.name == "GST Inputs":
            is_gst_input = True

    if is_gst_input:
        # Upload to Supabase: reports/<firm_id>/<client_id>/gst_inputs/<subfolder_slug>/<filename>
        slug = GST_INPUT_FOLDER_SLUGS[folder.name]
        supabase_path = f"{current_user.firm_id}/{client_id}/gst_inputs/{slug}/{unique_name}"

        supabase_svc = _get_supabase_storage()
        if supabase_svc:
            _ensure_reports_bucket(supabase_svc)
            try:
                content_type = file.content_type or "application/octet-stream"
                supabase_svc.client.storage.from_(REPORTS_BUCKET).upload(
                    path=supabase_path,
                    file=content,
                    file_options={"content-type": content_type, "upsert": "true"}
                )
                storage_path = f"supabase://{REPORTS_BUCKET}/{supabase_path}"
            except Exception as e:
                print(f"Supabase upload failed, falling back to local: {e}")

    # Fallback to local storage (or for non-GST-Input folders)
    if not storage_path:
        save_dir = os.path.join(
            DRIVE_STORAGE_ROOT,
            str(current_user.firm_id),
            str(client_id),
            str(folder_id),
        )
        os.makedirs(save_dir, exist_ok=True)
        file_path = os.path.join(save_dir, unique_name)
        with open(file_path, "wb") as f:
            f.write(content)
        storage_path = file_path

    # DB record
    drive_file = DriveFile(
        folder_id=folder_id,
        client_id=client_id,
        firm_id=current_user.firm_id,
        name=file.filename,
        original_name=file.filename,
        file_type=_file_type(file.filename),
        size_bytes=size,
        storage_path=storage_path,
    )
    db.add(drive_file)
    await db.commit()
    await db.refresh(drive_file)

    return drive_file


@router.delete("/{client_id}/files/{file_id}")
async def delete_file(
    client_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Delete a single file."""
    q = select(DriveFile).where(
        DriveFile.id == file_id,
        DriveFile.client_id == client_id,
        DriveFile.firm_id == current_user.firm_id,
    )
    result = await db.execute(q)
    df = result.scalars().first()
    if not df:
        raise HTTPException(status_code=404, detail="File not found")

    # Remove from storage
    if df.storage_path.startswith("supabase://"):
        # Delete from Supabase
        try:
            supabase_svc = _get_supabase_storage()
            if supabase_svc:
                # Parse: supabase://reports/<path>
                parts = df.storage_path.replace("supabase://", "").split("/", 1)
                bucket = parts[0]
                path = parts[1] if len(parts) > 1 else ""
                supabase_svc.client.storage.from_(bucket).remove([path])
        except Exception as e:
            print(f"Failed to delete from Supabase: {e}")
    elif os.path.exists(df.storage_path):
        os.remove(df.storage_path)

    await db.delete(df)
    await db.commit()
    return {"status": "deleted"}


@router.get("/{client_id}/files/{file_id}/download")
async def download_file(
    client_id: UUID,
    file_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Download a file (from local disk or Supabase)."""
    q = select(DriveFile).where(
        DriveFile.id == file_id,
        DriveFile.client_id == client_id,
        DriveFile.firm_id == current_user.firm_id,
    )
    result = await db.execute(q)
    df = result.scalars().first()
    if not df:
        raise HTTPException(status_code=404, detail="File not found")

    if df.storage_path.startswith("supabase://"):
        # Download from Supabase
        supabase_svc = _get_supabase_storage()
        if not supabase_svc:
            raise HTTPException(status_code=500, detail="Supabase not configured")

        parts = df.storage_path.replace("supabase://", "").split("/", 1)
        bucket = parts[0]
        path = parts[1] if len(parts) > 1 else ""

        try:
            file_bytes = supabase_svc.client.storage.from_(bucket).download(path)
            from fastapi.responses import Response
            return Response(
                content=file_bytes,
                media_type="application/octet-stream",
                headers={"Content-Disposition": f'attachment; filename="{df.original_name}"'}
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to download from Supabase: {e}")
    else:
        # Local file
        if not os.path.exists(df.storage_path):
            raise HTTPException(status_code=404, detail="File not found on disk")

        return FileResponse(
            path=df.storage_path,
            filename=df.original_name,
            media_type="application/octet-stream",
        )


# ─────────────────────────────────── STATS ──

@router.get("/{client_id}/stats", response_model=drive_schemas.DriveStats)
async def drive_stats(
    client_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Get aggregate drive stats for the client."""
    # Count folders
    fq = select(func.count()).select_from(DriveFolder).where(
        DriveFolder.client_id == client_id,
        DriveFolder.firm_id == current_user.firm_id,
    )
    folder_count = (await db.execute(fq)).scalar() or 0

    # Count files + total size
    ff = select(
        func.count(),
        func.coalesce(func.sum(DriveFile.size_bytes), 0),
        func.max(DriveFile.created_at),
    ).where(
        DriveFile.client_id == client_id,
        DriveFile.firm_id == current_user.firm_id,
    )
    row = (await db.execute(ff)).first()
    file_count = row[0] or 0
    total_size = row[1] or 0
    last_updated = row[2]

    return drive_schemas.DriveStats(
        total_folders=folder_count,
        total_files=file_count,
        total_size_bytes=total_size,
        last_updated=last_updated,
    )
