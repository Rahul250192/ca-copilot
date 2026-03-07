"""
Tally Data API — serves ledgers, vouchers and voucher_entries
from the Supabase tables synced by the Tally connector.
"""
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, desc, asc, or_

from app.api import deps
from app.models.models import Ledger, Voucher, VoucherEntry, User

router = APIRouter()


# ──────────────────────────────────────────
# LEDGERS
# ──────────────────────────────────────────
@router.get("/ledgers")
async def list_ledgers(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    company_name: Optional[str] = None,
    search: Optional[str] = None,
    parent: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> Any:
    """List ledgers with search/filter/pagination."""
    q = select(Ledger)

    if company_name:
        q = q.where(Ledger.company_name == company_name)
    if parent:
        q = q.where(Ledger.parent == parent)
    if search:
        q = q.where(or_(
            Ledger.name.ilike(f"%{search}%"),
            Ledger.parent.ilike(f"%{search}%"),
            Ledger.party_gstin.ilike(f"%{search}%"),
        ))

    # Count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    q = q.order_by(Ledger.name).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(q)
    ledgers = result.scalars().all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": -(-total // per_page),  # ceil division
        "data": [
            {
                "id": str(l.id),
                "name": l.name,
                "parent": l.parent or "",
                "company_name": l.company_name,
                "party_gstin": l.party_gstin or "",
                "gst_registration_type": l.gst_registration_type or "",
                "opening_balance": float(l.opening_balance) if l.opening_balance else 0,
                "closing_balance": float(l.closing_balance) if l.closing_balance else 0,
                "state": l.state or "",
                "email": l.email or "",
                "mobile": l.mobile or "",
                "address": l.address or "",
                "synced_at": l.synced_at.isoformat() if l.synced_at else None,
            }
            for l in ledgers
        ],
    }


@router.get("/ledgers/groups")
async def list_ledger_groups(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Get distinct ledger parent groups."""
    q = select(Ledger.parent, func.count(Ledger.id).label("count")).group_by(Ledger.parent).order_by(Ledger.parent)
    result = await db.execute(q)
    return [{"group": row[0] or "Ungrouped", "count": row[1]} for row in result]


@router.get("/ledgers/stats")
async def ledger_stats(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Summary stats for the dashboard."""
    total = (await db.execute(select(func.count(Ledger.id)))).scalar() or 0
    with_gstin = (await db.execute(
        select(func.count(Ledger.id)).where(Ledger.party_gstin != None, Ledger.party_gstin != "")
    )).scalar() or 0
    groups = (await db.execute(
        select(func.count(func.distinct(Ledger.parent)))
    )).scalar() or 0
    companies = (await db.execute(
        select(func.count(func.distinct(Ledger.company_name)))
    )).scalar() or 0

    return {"total_ledgers": total, "with_gstin": with_gstin, "groups": groups, "companies": companies}


# ──────────────────────────────────────────
# VOUCHERS
# ──────────────────────────────────────────
@router.get("/vouchers")
async def list_vouchers(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
    company_name: Optional[str] = None,
    voucher_type: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
) -> Any:
    """List vouchers with filters."""
    q = select(Voucher)
    if company_name:
        q = q.where(Voucher.company_name == company_name)
    if voucher_type:
        q = q.where(Voucher.voucher_type == voucher_type)
    if search:
        q = q.where(or_(
            Voucher.party_name.ilike(f"%{search}%"),
            Voucher.voucher_number.ilike(f"%{search}%"),
        ))

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    q = q.order_by(desc(Voucher.date)).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(q)
    vouchers = result.scalars().all()

    return {
        "total": total, "page": page, "per_page": per_page,
        "total_pages": -(-total // per_page),
        "data": [
            {
                "id": str(v.id),
                "company_name": v.company_name,
                "date": v.date,
                "voucher_type": v.voucher_type or "",
                "voucher_number": v.voucher_number or "",
                "party_name": v.party_name or "",
                "amount": float(v.amount) if v.amount else 0,
                "narration": v.narration or "",
                "guid": v.guid,
                "synced_at": v.synced_at.isoformat() if v.synced_at else None,
            }
            for v in vouchers
        ],
    }


@router.get("/vouchers/stats")
async def voucher_stats(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
) -> Any:
    """Dashboard stats for Tally vouchers by type."""
    total = (await db.execute(select(func.count(Voucher.id)))).scalar() or 0

    type_counts = {}
    for vtype in ["Sales", "Purchase", "Payment", "Receipt", "Journal", "Contra"]:
        c = (await db.execute(
            select(func.count(Voucher.id)).where(Voucher.voucher_type == vtype)
        )).scalar() or 0
        type_counts[vtype.lower()] = c

    return {"total": total, **type_counts}
