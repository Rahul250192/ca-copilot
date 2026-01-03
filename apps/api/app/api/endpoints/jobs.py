from typing import Any, List
from uuid import UUID

import os
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import desc

from app.api import deps
from app.models.job import Job, JobStatus
from app.models.models import User
from app.schemas.job import JobCreate, JobResponse, JobUpdate
from app.services.storage import storage_service

router = APIRouter()

@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_job_file(
    file: UploadFile = File(...),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Upload a file for use in a job. Returns the file path/key.
    """
    # Create a unique path for the file
    # Format: jobs/temp/{firm_id}/{filename} 
    # Use firm_id as a folder name. The new storage service will create this folder structure.
    file_content = await file.read()
    
    # Simple sanitization
    safe_name = file.filename.replace(" ", "_").replace("/", "_")
    path = f"jobs/temp/{current_user.firm_id}/{safe_name}"
    
    uploaded_path = storage_service.upload_file(
        file_content=file_content,
        path=path,
        content_type=file.content_type
    )
    
    if not uploaded_path:
        raise HTTPException(status_code=500, detail="Failed to upload file")
        
    return {"file_path": uploaded_path}


@router.post("/", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
async def create_job(
    job_in: JobCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Create a new job.
    """
    job = Job(
        job_type=job_in.job_type,
        input_files=job_in.input_files,
        status=JobStatus.QUEUED,
        created_by=current_user.id,
        firm_id=current_user.firm_id,
        client_id=job_in.client_id,
        output_files=[]
    )
    db.add(job)
    await db.commit()
    
    # Re-fetch with eager loading to allow Pydantic serialization of relationships
    result = await db.execute(select(Job).options(selectinload(Job.events)).filter(Job.id == job.id))
    job = result.scalars().first()
    
    return job

@router.get("/", response_model=List[JobResponse])
async def read_jobs(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 100,
    client_id: UUID = None
) -> Any:
    """
    Retrieve jobs.
    """

    query = select(Job).options(selectinload(Job.events)).filter(Job.firm_id == current_user.firm_id)
    
    if client_id:
        query = query.filter(Job.client_id == client_id)
        
    query = query.order_by(desc(Job.created_at)).offset(skip).limit(limit)
    
    result = await db.execute(query)
    jobs = result.scalars().all()
    return jobs

@router.get("/{id}", response_model=JobResponse)
async def read_job(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get job by ID.
    """
    result = await db.execute(select(Job).options(selectinload(Job.events)).filter(Job.id == id))
    job = result.scalars().first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Ensure user has access (same firm)
    if job.firm_id != current_user.firm_id and current_user.role != "admin": # Basic check
         raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return job

@router.get("/{id}/download")
async def download_job_file(
    *,
    db: AsyncSession = Depends(deps.get_db),
    id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Download the first output file for a job.
    """
    result = await db.execute(select(Job).options(selectinload(Job.events)).filter(Job.id == id))
    job = result.scalars().first()
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job.firm_id != current_user.firm_id and current_user.role != "admin":
         raise HTTPException(status_code=403, detail="Not enough permissions")
    
    if not job.output_files or len(job.output_files) == 0:
        raise HTTPException(status_code=404, detail="No output files for this job")
        
    file_key = job.output_files[0]
    
    # Use storage service to resolve path (Local) or download (Drive) to a served temp file
    local_path = storage_service.download_to_temp(file_key)
    
    if not local_path or not os.path.exists(local_path):
         raise HTTPException(status_code=404, detail="File not found on server")
         
    return FileResponse(local_path, media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', filename=os.path.basename(local_path))
