from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.core import security
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.models.models import Firm, User, UserRole
from app.schemas import token as token_schemas
from app.schemas import user as user_schemas

router = APIRouter()

@router.post("/login", response_model=token_schemas.Token)
async def login_access_token(
    db: AsyncSession = Depends(deps.get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()
    
    if not user or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }

@router.post("/signup", response_model=user_schemas.User)
async def signup(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_in: user_schemas.UserCreate,
) -> Any:
    """
    Create new firm and owner user.
    """
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == user_in.email))
    user = result.scalars().first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    
    # Create Firm
    firm = Firm(name=user_in.firm_name)
    db.add(firm)
    await db.flush() # Get firm ID
    
    # Create User
    user = User(
        email=user_in.email,
        hashed_password=security.get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=UserRole.OWNER,
        firm_id=firm.id
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    user.firm_name = firm.name
    return user

@router.get("/me", response_model=user_schemas.User)
async def read_users_me(
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get current user.
    """
    if current_user.firm:
        current_user.firm_name = current_user.firm.name
    return current_user

@router.put("/me", response_model=user_schemas.User)
async def update_user_me(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_in: user_schemas.UserProfileUpdate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Update own profile.
    """
    if user_in.full_name is not None:
        current_user.full_name = user_in.full_name
        
    if user_in.email is not None and user_in.email != current_user.email:
        # Check uniqueness
        result = await db.execute(select(User).where(User.email == user_in.email))
        existing_user = result.scalars().first()
        if existing_user:
             raise HTTPException(status_code=400, detail="Email already taken")
        current_user.email = user_in.email
        
    if user_in.firm_name is not None:
        # Update linked firm
        # We need to fetch the firm first if not loaded, but typically we can just get by ID
        result = await db.execute(select(Firm).where(Firm.id == current_user.firm_id))
        firm = result.scalars().first()
        if firm:
            firm.name = user_in.firm_name
            db.add(firm)

    if user_in.phone_number is not None:
        current_user.phone_number = user_in.phone_number
    if user_in.job_title is not None:
        current_user.job_title = user_in.job_title
    if user_in.subscription_plan is not None:
        current_user.subscription_plan = user_in.subscription_plan
        
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)
    
    if current_user.firm:
        current_user.firm_name = current_user.firm.name
        
    return current_user
