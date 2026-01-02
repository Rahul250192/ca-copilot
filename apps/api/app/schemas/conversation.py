from typing import Optional, List
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

from app.schemas.kit import Kit
from app.schemas.message import Message

class ConversationBase(BaseModel):
    title: Optional[str] = None
    client_id: UUID

class ConversationCreate(ConversationBase):
    service_id: Optional[UUID] = None

class ConversationInDBBase(ConversationBase):
    id: UUID
    firm_id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class Conversation(ConversationInDBBase):
    attached_kits: List[Kit] = []
    # Messages could be loaded separately
