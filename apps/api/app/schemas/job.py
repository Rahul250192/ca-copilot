from typing import Any, Dict, List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.job import JobStatus, JobType

# Shared properties
class JobBase(BaseModel):
    job_type: JobType
    input_files: List[Any] = [] # Can be File IDs (strings) or download URLs
    client_id: Optional[UUID] = None

# Properties to receive on creation
class JobCreate(JobBase):
    pass

class JobUpdate(BaseModel):
    status: Optional[JobStatus] = None
    output_files: Optional[List[Any]] = None

class JobEventSchema(BaseModel):
    id: UUID
    level: str
    message: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class JobResponse(JobBase):
    id: UUID
    status: JobStatus
    output_files: List[Any] = []
    created_at: datetime
    updated_at: datetime
    events: List[JobEventSchema] = []
    
    class Config:
        from_attributes = True
