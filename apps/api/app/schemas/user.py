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

class UserProfileUpdate(BaseModel):
    phone_number: Optional[str] = None
    job_title: Optional[str] = None
    # subscription_plan: Optional[str] = None # Generally not updateable by user directly, but user asked for edit profile api.
    # User said: "any user detail can be changed except for email and name"
    # So we should allow subscription_plan update for now if they want? 
    # Usually plan is updated via payment flow. But let's follow "any user detail" instruction strictly but keep it optional.
    # Actually, usually plan is critical. Let's start with safe profile fields.
    # Wait, the prompt said "any user detail can be changed except for email and name".
    # I will include subscription_plan but maybe it should be restricted to admin? 
    # "Added subscription_plan (String, default "free")"
    # "there any user detail can be changed except for email and name" -> implies strictly those 2 are blocked.
    subscription_plan: Optional[str] = None

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
