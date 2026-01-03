from typing import Any, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
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
def create_job(
    job_in: JobCreate,
    db: Session = Depends(deps.get_db),
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
    db.commit()
    db.refresh(job)
    return job

@router.get("/", response_model=List[JobResponse])
def read_jobs(
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve jobs.
    """
    # Filter by user's firm
    jobs = (
        db.query(Job)
        .filter(Job.firm_id == current_user.firm_id)
        .order_by(desc(Job.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
    return jobs

@router.get("/{id}", response_model=JobResponse)
def read_job(
    *,
    db: Session = Depends(deps.get_db),
    id: UUID,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Get job by ID.
    """
    job = db.query(Job).filter(Job.id == id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Ensure user has access (same firm)
    if job.firm_id != current_user.firm_id and current_user.role != "admin": # Basic check
         raise HTTPException(status_code=403, detail="Not enough permissions")
    
    return job
