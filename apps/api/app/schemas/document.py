from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, root_validator

from app.models.models import Scope, DocumentStatus

class DocumentBase(BaseModel):
    title: str
    scope: Scope
    firm_id: Optional[UUID] = None
    client_id: Optional[UUID] = None
    kit_id: Optional[UUID] = None

class DocumentCreate(DocumentBase):
    pass

class DocumentInDBBase(DocumentBase):
    id: UUID
    status: DocumentStatus
    created_at: datetime
    metadata_: Dict[str, Any] = None 

    class Config:
        from_attributes = True
        populate_by_name = True

class Document(DocumentInDBBase):
    pass
