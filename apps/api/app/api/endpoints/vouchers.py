from typing import Any, List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models.models import AccountingVoucher, VoucherLedgerItem, VoucherTaxItem, User
from app.schemas import voucher as voucher_schemas

router = APIRouter()

@router.post("/", response_model=voucher_schemas.AccountingVoucher)
async def create_voucher(
    *,
    db: AsyncSession = Depends(deps.get_db),
    voucher_in: voucher_schemas.AccountingVoucherCreate,
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Create a new accounting voucher along with its ledger and tax items.
    """
    # Create voucher record
    voucher = AccountingVoucher(
        voucher_type=voucher_in.voucher_type,
        supplier_invoice_no=voucher_in.supplier_invoice_no,
        voucher_date=voucher_in.voucher_date,
        party_name=voucher_in.party_name,
        gst_number=voucher_in.gst_number,
        narration=voucher_in.narration,
        sub_total=voucher_in.sub_total,
        tax_amount=voucher_in.tax_amount,
        total_amount=voucher_in.total_amount,
        sync_status=voucher_in.sync_status,
        client_id=voucher_in.client_id,
        firm_id=current_user.firm_id
    )
    db.add(voucher)
    await db.flush()  # To get the voucher ID

    # Create Ledger Items
    for item in voucher_in.ledger_items:
        ledger_item = VoucherLedgerItem(
            voucher_id=voucher.id,
            ledger_name=item.ledger_name,
            description=item.description,
            amount=item.amount
        )
        db.add(ledger_item)

    # Create Tax Items
    for item in voucher_in.tax_items:
        tax_item = VoucherTaxItem(
            voucher_id=voucher.id,
            ledger_name=item.ledger_name,
            description=item.description,
            amount=item.amount
        )
        db.add(tax_item)

    await db.commit()
    
    # Reload with relationships
    query = select(AccountingVoucher).options(
        selectinload(AccountingVoucher.ledger_items),
        selectinload(AccountingVoucher.tax_items)
    ).where(AccountingVoucher.id == voucher.id)
    result = await db.execute(query)
    
    return result.scalars().first()

@router.get("/check-duplicate", response_model=voucher_schemas.CheckDuplicateResponse)
async def check_duplicate_voucher(
    party_name: str,
    supplier_invoice_no: str,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """
    Check if a voucher with the same supplier_invoice_no and party_name already exists for this firm.
    """
    if not supplier_invoice_no or not party_name:
        return {"is_duplicate": False, "voucher_id": None}

    query = select(AccountingVoucher).where(
        AccountingVoucher.firm_id == current_user.firm_id,
        AccountingVoucher.party_name == party_name,
        AccountingVoucher.supplier_invoice_no == supplier_invoice_no
    )
    result = await db.execute(query)
    existing_voucher = result.scalars().first()

    if existing_voucher:
        return {"is_duplicate": True, "voucher_id": existing_voucher.id}
    return {"is_duplicate": False, "voucher_id": None}
