from typing import Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models.models import Service, Kit, User, UserRole
from app.schemas import service as service_schemas

router = APIRouter()

@router.get("/", response_model=List[service_schemas.Service])
async def read_services(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve services.
    """
    query = select(Service).options(selectinload(Service.kits)).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/", response_model=service_schemas.ServiceInDBBase)
async def create_service(
    *,
    db: AsyncSession = Depends(deps.get_db),
    service_in: service_schemas.ServiceCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Create a new service and optionally attach kits.
    """
    service = Service(
        name=service_in.name,
        description=service_in.description
    )
    
    if service_in.kit_ids:
        kit_query = select(Kit).where(Kit.id.in_(service_in.kit_ids))
        kit_result = await db.execute(kit_query)
        service.kits = kit_result.scalars().all()
        
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service

@router.get("/{service_id}", response_model=service_schemas.Service)
async def read_service(
    service_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get service by ID.
    """
    query = select(Service).options(selectinload(Service.kits)).where(
        Service.id == service_id
    )
    result = await db.execute(query)
    service = result.scalars().first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service

@router.put("/{service_id}/kits")
async def update_service_kits(
    service_id: UUID,
    kit_ids: List[UUID],
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
):
    """
    Update the kits attached to a service.
    """
    query = select(Service).where(
        Service.id == service_id
    )
    result = await db.execute(query)
    service = result.scalars().first()
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
        
    kit_query = select(Kit).where(Kit.id.in_(kit_ids))
    kit_result = await db.execute(kit_query)
    service.kits = kit_result.scalars().all()
    
    await db.commit()
    return {"status": "ok"}
