from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel
from app.models.models import MessageRole

class Citation(BaseModel):
    document_id: UUID
    scope: str
    chunk_text: str
    chunk_index: int
    score: float # Similarity score

class MessageBase(BaseModel):
    role: MessageRole
    content: str

class MessageCreate(MessageBase):
    role: Optional[MessageRole] = MessageRole.USER

class MessageInDBBase(MessageBase):
    id: UUID
    conversation_id: UUID
    created_at: datetime
    
    class Config:
        from_attributes = True

class Message(MessageInDBBase):
    citations: Optional[List[Citation]] = None # Populated for assistant messages if available
