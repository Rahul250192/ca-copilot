from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from app.schemas.kit import Kit

class ServiceBase(BaseModel):
    name: str
    description: Optional[str] = None

class ServiceCreate(ServiceBase):
    kit_ids: Optional[List[UUID]] = []

class ServiceUpdate(ServiceBase):
    kit_ids: Optional[List[UUID]] = None

class ServiceInDBBase(ServiceBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class Service(ServiceInDBBase):
    kits: List[Kit] = []
