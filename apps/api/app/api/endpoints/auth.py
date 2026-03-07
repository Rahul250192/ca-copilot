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


# ═══════════════════════════════════════════════
# LOGIN — Email + Password (existing flow)
# ═══════════════════════════════════════════════
@router.post("/login", response_model=token_schemas.Token)
async def login_access_token(
    db: AsyncSession = Depends(deps.get_db), form_data: OAuth2PasswordRequestForm = Depends()
) -> Any:
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    # Find user by email
    result = await db.execute(select(User).where(User.email == form_data.username))
    user = result.scalars().first()
    
    if not user or not user.hashed_password or not security.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect email or password")
        
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


# ═══════════════════════════════════════════════
# LOGIN — Phone + Password
# ═══════════════════════════════════════════════
from pydantic import BaseModel

class PhoneLoginRequest(BaseModel):
    phone_number: str
    password: str

@router.post("/login/phone", response_model=token_schemas.Token)
async def login_phone(
    *,
    db: AsyncSession = Depends(deps.get_db),
    body: PhoneLoginRequest,
) -> Any:
    """
    Login with phone number + password.
    """
    import re
    cleaned = re.sub(r'[\s\-\(\)]+', '', body.phone_number)

    result = await db.execute(select(User).where(User.phone_number == cleaned))
    user = result.scalars().first()

    if not user or not user.hashed_password or not security.verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect phone number or password")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


# ═══════════════════════════════════════════════
# SIGNUP — Email (existing flow, unchanged logic)
# ═══════════════════════════════════════════════
@router.post("/signup", response_model=user_schemas.User)
async def signup(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_in: user_schemas.UserCreate,
) -> Any:
    """
    Create new firm and owner user via email + password.
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
        firm_id=firm.id,
        signup_method="email",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    user.firm_name = firm.name
    return user


# ═══════════════════════════════════════════════
# SIGNUP — Phone Number
# ═══════════════════════════════════════════════
@router.post("/signup/phone", response_model=user_schemas.User)
async def signup_phone(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_in: user_schemas.UserCreatePhone,
) -> Any:
    """
    Create new firm and owner user via phone number + password.
    """
    # Check if phone already registered
    result = await db.execute(select(User).where(User.phone_number == user_in.phone_number))
    existing = result.scalars().first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail="A user with this phone number already exists.",
        )

    # If email provided, check that too
    if user_in.email:
        result = await db.execute(select(User).where(User.email == user_in.email))
        existing = result.scalars().first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail="The user with this email already exists in the system.",
            )

    # Create Firm
    firm = Firm(name=user_in.firm_name)
    db.add(firm)
    await db.flush()

    # Create User
    user = User(
        phone_number=user_in.phone_number,
        email=user_in.email,
        hashed_password=security.get_password_hash(user_in.password),
        full_name=user_in.full_name,
        role=UserRole.OWNER,
        firm_id=firm.id,
        signup_method="phone",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    user.firm_name = firm.name
    return user


# ═══════════════════════════════════════════════
# SIGNUP / LOGIN — Google OAuth
# ═══════════════════════════════════════════════
@router.post("/signup/google", response_model=token_schemas.Token)
async def signup_google(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_in: user_schemas.UserCreateGoogle,
) -> Any:
    """
    Sign up or log in with Google.
    Verifies the Google id_token, extracts user info, creates the
    user+firm if new, or returns a token for existing users.
    """
    from google.oauth2 import id_token as google_id_token
    from google.auth.transport import requests as google_requests

    # 1. Verify the Google id_token
    try:
        idinfo = google_id_token.verify_oauth2_token(
            user_in.google_id_token,
            google_requests.Request(),
            settings.GOOGLE_OAUTH_CLIENT_ID,
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid Google ID token.",
        )

    google_email = idinfo.get("email")
    google_name = idinfo.get("name", "")

    if not google_email:
        raise HTTPException(
            status_code=400,
            detail="Google account does not have an email address.",
        )

    # 2. Check if user already exists
    result = await db.execute(select(User).where(User.email == google_email))
    user = result.scalars().first()

    if user:
        # Existing user — just issue a token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = security.create_access_token(
            user.id, expires_delta=access_token_expires
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    # 3. New user — create firm + user
    firm_name = user_in.firm_name or f"{google_name}'s Firm"
    firm = Firm(name=firm_name)
    db.add(firm)
    await db.flush()

    user = User(
        email=google_email,
        full_name=google_name,
        hashed_password=None,  # No password for Google users
        role=UserRole.OWNER,
        firm_id=firm.id,
        signup_method="google",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Issue token for the new user
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        user.id, expires_delta=access_token_expires
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


# ═══════════════════════════════════════════════
# ME — Read / Update Profile (unchanged)
# ═══════════════════════════════════════════════
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
