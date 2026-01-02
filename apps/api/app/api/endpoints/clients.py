from typing import Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from sqlalchemy.orm import selectinload
from app.api import deps
from app.models.models import Client, User, UserRole, Service
from app.schemas import client as client_schemas

router = APIRouter()

@router.get("/", response_model=List[client_schemas.Client])
async def read_clients(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve clients.
    """
    query = select(Client).options(
        selectinload(Client.services).selectinload(Service.kits)
    ).where(
        Client.firm_id == current_user.firm_id
    ).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/", response_model=client_schemas.Client)
async def create_client(
    *,
    db: AsyncSession = Depends(deps.get_db),
    client_in: client_schemas.ClientCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Create new client.
    """
    client = Client(
        name=client_in.name,
        gstins=client_in.gstins,
        pan=client_in.pan,
        cin=client_in.cin,
        tan=client_in.tan,
        iec=client_in.iec,
        firm_id=current_user.firm_id
    )
    
    if client_in.service_ids:
        # Fetch and attach services
        service_query = select(Service).where(Service.id.in_(client_in.service_ids))
        service_result = await db.execute(service_query)
        client.services = service_result.scalars().all()
        
    db.add(client)
    await db.commit()
    await db.refresh(client, ["services"])
    return client

@router.get("/{client_id}", response_model=client_schemas.Client)
async def read_client(
    client_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get client by ID.
    """
    query = select(Client).options(selectinload(Client.services)).where(
        Client.id == client_id, 
        Client.firm_id == current_user.firm_id
    )
    result = await db.execute(query)
    client = result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return client

from app.schemas import service as service_schemas

@router.get("/{client_id}/services", response_model=List[service_schemas.Service])
async def read_client_services(
    client_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get services for a specific client.
    """
    query = select(Client).options(
        selectinload(Client.services).selectinload(Service.kits)
    ).where(
        Client.id == client_id, 
        Client.firm_id == current_user.firm_id
    )
    result = await db.execute(query)
    client = result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    return client.services

@router.put("/{client_id}/services")
async def attach_services(
    client_id: UUID,
    service_ids: List[UUID],
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Attach services to a client.
    """
    query = select(Client).options(selectinload(Client.services)).where(
        Client.id == client_id, 
        Client.firm_id == current_user.firm_id
    )
    result = await db.execute(query)
    client = result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
        
    service_query = select(Service).where(Service.id.in_(service_ids))
    service_result = await db.execute(service_query)
    client.services = service_result.scalars().all()
    
    await db.commit()
    return {"status": "ok"}

from fastapi import UploadFile, File, Form, BackgroundTasks
from app.models.models import Document, Scope, DocumentStatus
from app.services.ingestion import ingest_document
import os

@router.post("/{client_id}/upload")
async def upload_client_document(
    client_id: UUID,
    *,
    db: AsyncSession = Depends(deps.get_db),
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    title: str = Form(...),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Upload a document specific to a client context.
    Stored in: client-context/{client_id}/{filename}
    """
    # Verify client ownership
    query = select(Client).where(Client.id == client_id, Client.firm_id == current_user.firm_id)
    result = await db.execute(query)
    client = result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Define path & bucket
    cloud_path = f"{client_id}/{file.filename}"
    bucket = "client-context"
    
    from app.services.storage import storage_service
    
    file_content = await file.read()
    uploaded_path = storage_service.upload_file(
        file_content=file_content,
        path=cloud_path,
        bucket=bucket,
        content_type=file.content_type
    )

    if not uploaded_path:
        # Fallback to local
        UPLOAD_DIR = "storage"
        firm_id_str = str(current_user.firm_id)
        save_dir = os.path.join(UPLOAD_DIR, firm_id_str, "CLIENT", str(client_id))
        os.makedirs(save_dir, exist_ok=True)
        file_path = os.path.join(save_dir, file.filename)
        with open(file_path, "wb") as buffer:
            buffer.write(file_content)
        final_path = file_path
    else:
        final_path = uploaded_path
        print(f"File uploaded to cloud: {final_path} (Bucket: {bucket})")

    # Create Document DB Record
    try:
        document = Document(
            title=title,
            scope=Scope.CLIENT,
            firm_id=current_user.firm_id,
            client_id=client_id,
            status=DocumentStatus.UPLOADED,
            file_path=final_path
        )
        db.add(document)
        await db.commit()
        await db.refresh(document)
        print(f"Document record created in DB: {document.id}")
    except Exception as e:
        print(f"Error creating document record in DB: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

    # Trigger Ingestion
    background_tasks.add_task(ingest_document, document.id)

    return document

from app.schemas import document as doc_schemas

@router.get("/{client_id}/documents", response_model=List[doc_schemas.Document])
async def read_client_documents(
    client_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve documents specific to a client context.
    """
    # Verify client ownership
    query = select(Client).where(Client.id == client_id, Client.firm_id == current_user.firm_id)
    result = await db.execute(query)
    client = result.scalars().first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    # Fetch documents
    doc_query = select(Document).where(
        Document.client_id == client_id,
        Document.firm_id == current_user.firm_id,
        Document.scope == Scope.CLIENT
    ).offset(skip).limit(limit)
    
    doc_result = await db.execute(doc_query)
    return doc_result.scalars().all()
