"""
Drive Auto-Saver — automatically saves job output reports to the client's Drive
and to Supabase storage with clean hierarchy.

Storage hierarchy in Supabase bucket "reports":
  <firm_id>/<client_id>/<tool_name>/<Report_Prefix>_<timestamp>.xlsx

Two entry points:
  save_report_to_drive_sync(db, ...)   → for the synchronous worker
  save_report_to_drive_async(db, ...)  → for async API endpoints (reconciliation)

Flow:
  1. Map job_type → target folder name (e.g. "gstr1_vs_3b" → "GST Returns")
  2. Upload to Supabase storage with <firm>/<client>/<tool>/<file> hierarchy
  3. Find or create a DriveFolder in the DB
  4. Create a DriveFile DB record
  5. Return the drive_file_id so the Job can reference it
"""

import os
import uuid as _uuid
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.models import DriveFolder, DriveFile

logger = logging.getLogger("drive_saver")

# Reports bucket name in Supabase
REPORTS_BUCKET = "reports"


# ─────────────────────────────────── CONFIG ──

# Rule-based mapping: job_type → (folder_name, report_prefix, tool_folder)
# folder_name  = UI folder in the client Drive
# report_prefix = file prefix for display name
# tool_folder  = subfolder key in Supabase for this tool type
JOB_TYPE_TO_FOLDER = {
    # GST Reconciliation tools
    "gstr1_vs_3b":    ("GST Returns",       "GSTR1_vs_3B_Reconciliation",          "gstr1_vs_3b"),
    "gstr2b_vs_3b":   ("GST Returns",       "GSTR2B_vs_3B_Reconciliation",         "gstr2b_vs_3b"),
    "gstr2b_vs_pr":   ("GST Returns",       "GSTR2B_vs_PR_Reconciliation",         "gstr2b_vs_pr"),
    "ims_vs_pr":      ("GST Returns",       "IMS_vs_PR_Reconciliation",            "ims_vs_pr"),
    "einv_vs_sr":     ("GST Returns",       "EInvoice_vs_SR_Reconciliation",       "einv_vs_sr"),
    "gstr1_vs_einv":  ("GST Returns",       "GSTR1_vs_EInvoice_Reconciliation",    "gstr1_vs_einv"),
    "gst_recon":      ("GST Returns",       "GST_Reconciliation",                  "gst_recon"),
    # GST tools
    "annexure_b":     ("GST Returns",       "Annexure_B_Report",                   "annexure_b"),
    "gstr9_json":     ("GST Returns",       "GSTR9_JSON",                          "gstr9_json"),
    "gst_verify":     ("GST Returns",       "GSTIN_Verification_Report",           "gst_verify"),
    "hsn_plotter":    ("GST Returns",       "HSN_Plotter_Report",                  "hsn_plotter"),
    "ai_block_credit":("GST Returns",       "Blocked_Credit_Report",               "ai_block_credit"),
    # Refund / Statements
    "statement3":     ("Refund Documents",  "Statement_3_Report",                  "statement3"),
    "statement3_firc":("Refund Documents",  "Statement_3_FIRC_Report",             "statement3_firc"),
    # Documents
    "document_reader":("Documents",         "Extracted_Document",                  "document_reader"),
}


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
    if ext in (".json",):
        return "data"
    if ext in (".zip", ".rar", ".7z"):
        return "archive"
    return "other"


def _generate_display_name(job_type: str, original_output_key: str) -> str:
    """Generate a human-readable display name for the saved report."""
    _, prefix, _ = JOB_TYPE_TO_FOLDER.get(job_type, ("Miscellaneous", "Report", "misc"))
    ext = os.path.splitext(original_output_key)[1] or ".xlsx"
    date_str = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return f"{prefix}_{date_str}{ext}"


def _build_supabase_path(firm_id: UUID, client_id: UUID, job_type: str, display_name: str) -> str:
    """
    Build the Supabase storage path with hierarchy:
      <firm_id>/<client_id>/<tool_folder>/<display_name>
    """
    _, _, tool_folder = JOB_TYPE_TO_FOLDER.get(job_type, ("Miscellaneous", "Report", "misc"))
    return f"{firm_id}/{client_id}/{tool_folder}/{display_name}"


def _get_supabase_storage():
    """Get the Supabase storage service (lazy import to avoid circular)."""
    from app.services.storage import storage_service
    if storage_service.supabase.enabled:
        return storage_service.supabase
    return None


def _ensure_reports_bucket(supabase_svc):
    """Ensure the 'reports' bucket exists in Supabase."""
    try:
        supabase_svc.client.storage.create_bucket(REPORTS_BUCKET, options={"public": True})
    except Exception:
        pass  # Already exists


# ─────────────────────────────────── SYNC VERSION (Worker) ──

def save_report_to_drive_sync(
    db: Session,
    firm_id: UUID,
    client_id: Optional[UUID],
    job_type: str,
    output_file_bytes: bytes,
    output_key: str,
) -> Optional[UUID]:
    """
    Save a job's output report to Supabase storage + client's Drive folder DB record.
    
    Supabase path: <firm_id>/<client_id>/<tool_folder>/<Report_Prefix>_<timestamp>.xlsx
    
    Args:
        db: Sync SQLAlchemy session
        firm_id: The firm UUID
        client_id: The client UUID (required — skip if None)
        job_type: The job type string (e.g. "gstr1_vs_3b")
        output_file_bytes: The raw bytes of the output file
        output_key: The original storage key/path of the output
    
    Returns:
        UUID of the created DriveFile, or None on failure
    """
    if not client_id:
        logger.info("No client_id — skipping drive save")
        return None

    if job_type not in JOB_TYPE_TO_FOLDER:
        logger.info(f"Job type '{job_type}' not mapped — skipping drive save")
        return None

    folder_name, _, tool_folder = JOB_TYPE_TO_FOLDER[job_type]

    try:
        # 1. Generate display name and Supabase path
        display_name = _generate_display_name(job_type, output_key)
        supabase_path = _build_supabase_path(firm_id, client_id, job_type, display_name)

        # 2. Upload to Supabase storage
        supabase_svc = _get_supabase_storage()
        storage_path = None
        if supabase_svc:
            _ensure_reports_bucket(supabase_svc)
            try:
                ext = os.path.splitext(output_key)[1] or ".xlsx"
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
                    if ext == ".xlsx" else "application/octet-stream"
                
                supabase_svc.client.storage.from_(REPORTS_BUCKET).upload(
                    path=supabase_path,
                    file=output_file_bytes,
                    file_options={"content-type": content_type, "upsert": "true"}
                )
                storage_path = f"supabase://{REPORTS_BUCKET}/{supabase_path}"
                logger.info(f"☁️  Uploaded to Supabase: {REPORTS_BUCKET}/{supabase_path}")
            except Exception as e:
                logger.warning(f"Supabase upload failed, falling back to local: {e}")
        
        # 3. Fallback to local disk if Supabase not available
        if not storage_path:
            DRIVE_STORAGE_ROOT = os.path.normpath(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "uploads", "drive")
            )
            save_dir = os.path.join(DRIVE_STORAGE_ROOT, str(firm_id), str(client_id), tool_folder)
            os.makedirs(save_dir, exist_ok=True)
            
            file_path = os.path.join(save_dir, display_name)
            with open(file_path, "wb") as f:
                f.write(output_file_bytes)
            storage_path = file_path
            logger.info(f"📁 Saved to local: {file_path}")

        # 4. Find or create the target Drive folder in DB
        folder = db.query(DriveFolder).filter(
            DriveFolder.client_id == client_id,
            DriveFolder.firm_id == firm_id,
            DriveFolder.name == folder_name,
        ).first()

        if not folder:
            folder_styles = _get_folder_style(folder_name)
            folder = DriveFolder(
                client_id=client_id,
                firm_id=firm_id,
                name=folder_name,
                **folder_styles,
            )
            db.add(folder)
            db.flush()
            logger.info(f"Created drive folder '{folder_name}' for client {client_id}")

        # 5. Create DriveFile record
        drive_file = DriveFile(
            folder_id=folder.id,
            client_id=client_id,
            firm_id=firm_id,
            name=display_name,
            original_name=display_name,
            file_type=_file_type(display_name),
            size_bytes=len(output_file_bytes),
            storage_path=storage_path,
        )
        db.add(drive_file)
        db.flush()

        logger.info(
            f"📁 Saved report: '{display_name}' → folder '{folder_name}' "
            f"(file_id={drive_file.id}, path={storage_path})"
        )
        return drive_file.id

    except Exception as e:
        logger.error(f"Failed to save report to drive: {e}")
        return None


# ─────────────────────────────────── ASYNC VERSION (API Endpoints) ──

async def save_report_to_drive_async(
    db: AsyncSession,
    firm_id: UUID,
    client_id: Optional[UUID],
    job_type: str,
    output_file_bytes: bytes,
    output_key: str,
) -> Optional[UUID]:
    """
    Async version of save_report_to_drive for use in FastAPI endpoints.
    Same logic as sync version but uses async SQLAlchemy.
    """
    if not client_id:
        logger.info("No client_id — skipping drive save")
        return None

    if job_type not in JOB_TYPE_TO_FOLDER:
        logger.info(f"Job type '{job_type}' not mapped — skipping drive save")
        return None

    folder_name, _, tool_folder = JOB_TYPE_TO_FOLDER[job_type]

    try:
        # 1. Generate display name and Supabase path
        display_name = _generate_display_name(job_type, output_key)
        supabase_path = _build_supabase_path(firm_id, client_id, job_type, display_name)

        # 2. Upload to Supabase storage
        supabase_svc = _get_supabase_storage()
        storage_path = None
        if supabase_svc:
            _ensure_reports_bucket(supabase_svc)
            try:
                ext = os.path.splitext(output_key)[1] or ".xlsx"
                content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
                    if ext == ".xlsx" else "application/octet-stream"
                
                supabase_svc.client.storage.from_(REPORTS_BUCKET).upload(
                    path=supabase_path,
                    file=output_file_bytes,
                    file_options={"content-type": content_type, "upsert": "true"}
                )
                storage_path = f"supabase://{REPORTS_BUCKET}/{supabase_path}"
                logger.info(f"☁️  Uploaded to Supabase: {REPORTS_BUCKET}/{supabase_path}")
            except Exception as e:
                logger.warning(f"Supabase upload failed, falling back to local: {e}")

        # 3. Fallback to local disk if Supabase not available
        if not storage_path:
            DRIVE_STORAGE_ROOT = os.path.normpath(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "uploads", "drive")
            )
            save_dir = os.path.join(DRIVE_STORAGE_ROOT, str(firm_id), str(client_id), tool_folder)
            os.makedirs(save_dir, exist_ok=True)
            
            file_path = os.path.join(save_dir, display_name)
            with open(file_path, "wb") as f:
                f.write(output_file_bytes)
            storage_path = file_path
            logger.info(f"📁 Saved to local: {file_path}")

        # 4. Find or create the target Drive folder in DB
        result = await db.execute(
            select(DriveFolder).where(
                DriveFolder.client_id == client_id,
                DriveFolder.firm_id == firm_id,
                DriveFolder.name == folder_name,
            )
        )
        folder = result.scalars().first()

        if not folder:
            folder_styles = _get_folder_style(folder_name)
            folder = DriveFolder(
                client_id=client_id,
                firm_id=firm_id,
                name=folder_name,
                **folder_styles,
            )
            db.add(folder)
            await db.flush()
            logger.info(f"Created drive folder '{folder_name}' for client {client_id}")

        # 5. Create DriveFile record
        drive_file = DriveFile(
            folder_id=folder.id,
            client_id=client_id,
            firm_id=firm_id,
            name=display_name,
            original_name=display_name,
            file_type=_file_type(display_name),
            size_bytes=len(output_file_bytes),
            storage_path=storage_path,
        )
        db.add(drive_file)
        await db.flush()

        logger.info(
            f"📁 Saved report: '{display_name}' → folder '{folder_name}' "
            f"(file_id={drive_file.id}, path={storage_path})"
        )
        return drive_file.id

    except Exception as e:
        logger.error(f"Failed to save report to drive: {e}")
        return None


# ─────────────────────────────────── HELPERS ──

# Folder styling to match the drive.py DEFAULT_FOLDERS
_FOLDER_STYLES = {
    "GST Returns":      {"icon": "🧾", "color": "#059669", "bg": "#ecfdf5"},
    "Income Tax":       {"icon": "💰", "color": "#d97706", "bg": "#fffbeb"},
    "Invoices":         {"icon": "🧾", "color": "#2563eb", "bg": "#eff6ff"},
    "Bank Statements":  {"icon": "🏦", "color": "#7c3aed", "bg": "#faf5ff"},
    "Refund Documents": {"icon": "💸", "color": "#0891b2", "bg": "#ecfeff"},
    "TDS Returns":      {"icon": "📑", "color": "#dc2626", "bg": "#fef2f2"},
    "Balance Sheet":    {"icon": "📊", "color": "#0d9488", "bg": "#f0fdfa"},
    "Documents":        {"icon": "📄", "color": "#6366f1", "bg": "#eef2ff"},
    "Audit Reports":    {"icon": "🔍", "color": "#7c3aed", "bg": "#faf5ff"},
    "Miscellaneous":    {"icon": "📎", "color": "#64748b", "bg": "#f1f5f9"},
}


def _get_folder_style(folder_name: str) -> dict:
    """Get icon/color/bg for a folder name, with fallback defaults."""
    return _FOLDER_STYLES.get(folder_name, {
        "icon": "📁",
        "color": "#3b82f6",
        "bg": "#eff6ff",
    })


def get_folder_name_for_job(job_type: str) -> Optional[str]:
    """Public helper to get the target folder name for a given job type."""
    if job_type in JOB_TYPE_TO_FOLDER:
        return JOB_TYPE_TO_FOLDER[job_type][0]
    return None
