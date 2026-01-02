from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr

from app.models.models import UserRole

# Shared properties
class UserBase(BaseModel):
    email: EmailStr
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    job_title: Optional[str] = None
    subscription_plan: Optional[str] = "free"
    role: UserRole = UserRole.STAFF

# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str
    firm_name: str # Used during signup to create the firm

class UserUpdate(UserBase):
    password: Optional[str] = None

class UserInDBBase(UserBase):
    id: UUID
    firm_id: UUID

    class Config:
        from_attributes = True

# Additional properties to return via API
class User(UserInDBBase):
    pass

class UserInDB(UserInDBBase):
    hashed_password: str
