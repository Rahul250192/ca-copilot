from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.api import deps
from app.models.models import GetInvoice, User
from app.schemas import invoice as invoice_schemas

router = APIRouter()

@router.get("/", response_model=List[invoice_schemas.Invoice])
async def read_invoices(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
    client_email: Optional[str] = None,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Retrieve all invoices.
    """
    query = select(GetInvoice).offset(skip).limit(limit)
    if client_email:
        query = query.where(GetInvoice.client_email_id == client_email)
    result = await db.execute(query)
    return result.scalars().all()

@router.post("/", response_model=invoice_schemas.Invoice)
async def create_invoice(
    *,
    db: AsyncSession = Depends(deps.get_db),
    invoice_in: invoice_schemas.InvoiceCreate,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Create new invoice.
    """
    invoice = GetInvoice(**invoice_in.model_dump())
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice

@router.get("/{id}", response_model=invoice_schemas.Invoice)
async def read_invoice(
    id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get invoice by ID.
    """
    query = select(GetInvoice).where(GetInvoice.id == id)
    result = await db.execute(query)
    invoice = result.scalars().first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice

@router.patch("/{id}", response_model=invoice_schemas.Invoice)
async def update_invoice(
    id: int,
    invoice_in: invoice_schemas.InvoiceUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Update an invoice (specifically expenses_type).
    """
    query = select(GetInvoice).where(GetInvoice.id == id)
    result = await db.execute(query)
    invoice = result.scalars().first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    update_data = invoice_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(invoice, field, value)

    await db.commit()
    await db.refresh(invoice)
    return invoice
