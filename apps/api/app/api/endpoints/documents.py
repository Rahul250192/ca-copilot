import os
import shutil
from typing import Any, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.db.session import AsyncSessionLocal
from app.models.models import Document, User, Scope, DocumentStatus
from app.schemas import document as doc_schemas
from app.services.ingestion import ingest_document

router = APIRouter()

UPLOAD_DIR = "storage"

@router.post("/upload", response_model=doc_schemas.Document)
async def upload_document(
    *,
    db: AsyncSession = Depends(deps.get_db),
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    scope: Scope = Form(...),
    title: str = Form(...),
    client_id: Optional[UUID] = Form(None),
    kit_id: Optional[UUID] = Form(None),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Upload a document and start ingestion.
    """
    # Validate Scope
    if scope == Scope.FIRM:
        client_id = None
        kit_id = None
        # Limit firm docs to Owner/Admin? For now allow any staff.
    elif scope == Scope.CLIENT:
        if not client_id:
            raise HTTPException(status_code=400, detail="client_id required for CLIENT scope")
        kit_id = None
        # Validate client belongs to firm
        # (Could query DB to check if client exists and belongs to firm_id)
    elif scope == Scope.KIT:
        if not kit_id:
            raise HTTPException(status_code=400, detail="kit_id required for KIT scope")
        client_id = None

    # Define path
    bucket = None
    if scope == Scope.KIT:
        # KIT scope is common to all firms
        cloud_path = f"{kit_id}/{file.filename}"
    elif scope == Scope.CLIENT:
        # Client specific path
        cloud_path = f"{client_id}/{file.filename}"
        bucket = "client-context"
    else:
        # Hierarchical path for FIRM scope
        firm_id_str = str(current_user.firm_id)
        cloud_path = f"{firm_id_str}/{scope.value}/firm/{file.filename}"
    
    from app.services.storage import storage_service
    
    file_content = await file.read()
    uploaded_path = storage_service.upload_file(
        file_content=file_content,
        path=cloud_path,
        bucket=bucket,
        content_type=file.content_type
    )

    if not uploaded_path:
        # Fallback to local storage if cloud fails (for robustness)
        firm_id_str = str(current_user.firm_id)
        if scope == Scope.KIT:
            local_specific_id = str(kit_id)
        else:
            local_specific_id = str(client_id) if client_id else "firm"
            
        save_dir = os.path.join(UPLOAD_DIR, firm_id_str, scope.value, local_specific_id)
        os.makedirs(save_dir, exist_ok=True)
        file_path = os.path.join(save_dir, file.filename)
        print(f"Cloud upload failed or disabled, falling back to local: {file_path}")
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
        final_path = file_path
    else:
        final_path = uploaded_path

    # Create Document DB Record
    document = Document(
        title=title,
        scope=scope,
        firm_id=current_user.firm_id,
        client_id=client_id,
        kit_id=kit_id,
        status=DocumentStatus.UPLOADED,
        file_path=final_path
    )
    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Trigger Ingestion
    background_tasks.add_task(ingest_document, document.id)

    return document

@router.get("/", response_model=List[doc_schemas.Document])
async def read_documents(
    db: AsyncSession = Depends(deps.get_db),
    scope: Optional[Scope] = None,
    client_id: Optional[UUID] = None,
    kit_id: Optional[UUID] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve documents with filtering.
    """
    query = select(Document).where(Document.firm_id == current_user.firm_id)
    
    if scope:
        query = query.where(Document.scope == scope)
    if client_id:
        query = query.where(Document.client_id == client_id)
    if kit_id:
        query = query.where(Document.kit_id == kit_id)
        
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()

@router.get("/{doc_id}", response_model=doc_schemas.Document)
async def read_document(
    doc_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalars().first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Authorization check (basic)
    if doc.firm_id != current_user.firm_id:
         raise HTTPException(status_code=403, detail="Not authorized")
    return doc
