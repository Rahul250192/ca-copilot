from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.db.session import AsyncSessionLocal
from app.models.models import Kit, User, UserRole
from app.schemas import kit as kit_schemas

router = APIRouter()

@router.get("/", response_model=List[kit_schemas.Kit])
async def read_kits(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve kits.
    """
    query = select(Kit).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/", response_model=kit_schemas.Kit)
async def create_kit(
    *,
    db: AsyncSession = Depends(deps.get_db),
    kit_in: kit_schemas.KitCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Create new kit. Restricted to firmware owners/admins.
    """
    if current_user.role not in [UserRole.OWNER, UserRole.ADMIN]:
        raise HTTPException(status_code=403, detail="Not enough permissions")
    
    kit = Kit(
        name=kit_in.name,
        description=kit_in.description
    )
    db.add(kit)
    await db.commit()
    await db.refresh(kit)
    return kit
