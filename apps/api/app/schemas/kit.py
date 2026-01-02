from typing import Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel

class KitBase(BaseModel):
    name: str
    description: Optional[str] = None

class KitCreate(KitBase):
    pass

class KitInDBBase(KitBase):
    id: UUID
    created_at: datetime

    class Config:
        from_attributes = True

class Kit(KitInDBBase):
    pass
