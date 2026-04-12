"""
Firm Config API
───────────────
GET/PUT endpoints for firm-level configuration.
Currently supports: gst_deadlines

The GST deadlines config is pre-seeded with government defaults on first access.
Users can customize any deadline and it persists in the DB.
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.models.models import User, FirmConfig

router = APIRouter()
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# Default GST Deadlines (Government values)
# ═══════════════════════════════════════════════════════

GST_DEADLINES_DEFAULT = {
    "monthly_returns": [
        {
            "id": "gstr1_regular",
            "return_name": "GSTR-1",
            "description": "Outward supplies — Regular taxpayer (Turnover > ₹5 Cr)",
            "due_day": 11,
            "frequency": "monthly",
            "category": "filing",
            "applicable_to": "regular",
            "is_active": True,
        },
        {
            "id": "gstr1_qrmp",
            "return_name": "GSTR-1 (QRMP)",
            "description": "Outward supplies — QRMP taxpayer (Turnover ≤ ₹5 Cr)",
            "due_day": 13,
            "frequency": "quarterly",
            "category": "filing",
            "applicable_to": "qrmp",
            "is_active": True,
        },
        {
            "id": "iff",
            "return_name": "IFF",
            "description": "Invoice Furnishing Facility — Optional B2B invoices (M1, M2 only)",
            "due_day": 13,
            "frequency": "monthly",
            "category": "filing",
            "applicable_to": "qrmp",
            "is_active": True,
            "note": "Only for Month 1 & Month 2 of each quarter",
        },
        {
            "id": "gstr3b_regular",
            "return_name": "GSTR-3B",
            "description": "Summary return with tax payment — Regular taxpayer",
            "due_day": 20,
            "frequency": "monthly",
            "category": "filing",
            "applicable_to": "regular",
            "is_active": True,
        },
        {
            "id": "gstr3b_qrmp",
            "return_name": "GSTR-3B (QRMP)",
            "description": "Summary return — QRMP (22nd/24th depends on state)",
            "due_day": 22,
            "frequency": "quarterly",
            "category": "filing",
            "applicable_to": "qrmp",
            "is_active": True,
            "note": "22nd for Cat A states, 24th for Cat B states",
        },
        {
            "id": "pmt06",
            "return_name": "PMT-06",
            "description": "GST payment challan — QRMP Month 1 & 2 (no return, only payment)",
            "due_day": 25,
            "frequency": "monthly",
            "category": "payment",
            "applicable_to": "qrmp",
            "is_active": True,
        },
        {
            "id": "gstr2b_available",
            "return_name": "GSTR-2B Available",
            "description": "Auto-generated ITC statement available for reconciliation",
            "due_day": 14,
            "frequency": "monthly",
            "category": "reference",
            "applicable_to": "all",
            "is_active": True,
        },
    ],
    "quarterly_returns": [
        {
            "id": "cmp08",
            "return_name": "CMP-08",
            "description": "Composition scheme quarterly payment",
            "due_day": 18,
            "frequency": "quarterly",
            "category": "filing",
            "applicable_to": "composition",
            "is_active": True,
            "note": "18th of month following quarter",
        },
    ],
    "annual_returns": [
        {
            "id": "gstr9",
            "return_name": "GSTR-9",
            "description": "Annual return — All regular taxpayers",
            "due_date": "31-12",
            "frequency": "annual",
            "category": "filing",
            "applicable_to": "regular",
            "is_active": True,
            "note": "31st December of next FY",
        },
        {
            "id": "gstr9c",
            "return_name": "GSTR-9C",
            "description": "Reconciliation statement — Self-certified (Turnover > ₹5 Cr)",
            "due_date": "31-12",
            "frequency": "annual",
            "category": "filing",
            "applicable_to": "regular",
            "is_active": True,
            "note": "Self-certified from FY 2020-21",
        },
    ],
    "other_deadlines": [
        {
            "id": "lut_filing",
            "return_name": "LUT Filing",
            "description": "Letter of Undertaking for exporters — before first export of FY",
            "due_date": "01-04",
            "frequency": "annual",
            "category": "compliance",
            "applicable_to": "exporters",
            "is_active": True,
        },
        {
            "id": "itc_claim_deadline",
            "return_name": "ITC Claim Deadline",
            "description": "Last date to claim ITC for previous FY (Sec 16(4))",
            "due_date": "30-11",
            "frequency": "annual",
            "category": "compliance",
            "applicable_to": "all",
            "is_active": True,
            "note": "30th November of next FY (amended from FY 2025-26)",
        },
        {
            "id": "gstr1_amendment",
            "return_name": "GSTR-1 Amendment / Credit Notes",
            "description": "Last date to amend GSTR-1 or issue credit/debit notes",
            "due_date": "30-11",
            "frequency": "annual",
            "category": "compliance",
            "applicable_to": "all",
            "is_active": True,
            "note": "Earlier of: 30th Nov next FY or date of annual return",
        },
        {
            "id": "reg_amendment",
            "return_name": "Registration Amendment",
            "description": "Amendment to GST registration details",
            "due_day": 15,
            "frequency": "event",
            "category": "compliance",
            "applicable_to": "all",
            "is_active": True,
            "note": "Within 15 days of change",
        },
        {
            "id": "revocation_cancellation",
            "return_name": "Revocation of Cancellation",
            "description": "Apply for revocation of GST cancellation",
            "due_day": 30,
            "frequency": "event",
            "category": "compliance",
            "applicable_to": "all",
            "is_active": True,
            "note": "Within 30 days of cancellation order",
        },
    ],
    "late_fees": {
        "gstr1_per_day": 50,
        "gstr1_nil_per_day": 20,
        "gstr3b_per_day": 50,
        "gstr3b_nil_per_day": 20,
        "gstr3b_max_cap_range": "2000-10000",
        "interest_rate_pct": 18,
        "interest_note": "18% p.a. on net tax liability from due date",
    },
}


# ═══════════════════════════════════════════════════════
# Pydantic Schemas
# ═══════════════════════════════════════════════════════

class ConfigUpdate(BaseModel):
    config_data: dict


# ═══════════════════════════════════════════════════════
# Endpoints
# ═══════════════════════════════════════════════════════

@router.get("/gst-deadlines")
async def get_gst_deadlines(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """Get GST deadline config for the user's firm. Seeds defaults on first access."""
    firm_id = str(current_user.firm_id)

    row = (await db.execute(
        select(FirmConfig).where(
            FirmConfig.firm_id == firm_id,
            FirmConfig.config_key == "gst_deadlines",
        )
    )).scalar_one_or_none()

    if row:
        return {"config_data": row.config_data, "is_default": False}

    # First access: seed with defaults
    config = FirmConfig(
        id=str(uuid.uuid4()),
        firm_id=firm_id,
        config_key="gst_deadlines",
        config_data=GST_DEADLINES_DEFAULT,
    )
    db.add(config)
    await db.commit()
    logger.info(f"✅ Seeded GST deadlines config for firm {firm_id}")
    return {"config_data": GST_DEADLINES_DEFAULT, "is_default": True}


@router.put("/gst-deadlines")
async def update_gst_deadlines(
    body: ConfigUpdate,
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """Update GST deadline config for the user's firm."""
    firm_id = str(current_user.firm_id)

    row = (await db.execute(
        select(FirmConfig).where(
            FirmConfig.firm_id == firm_id,
            FirmConfig.config_key == "gst_deadlines",
        )
    )).scalar_one_or_none()

    if row:
        row.config_data = body.config_data
    else:
        row = FirmConfig(
            id=str(uuid.uuid4()),
            firm_id=firm_id,
            config_key="gst_deadlines",
            config_data=body.config_data,
        )
        db.add(row)

    await db.commit()
    logger.info(f"✅ Updated GST deadlines config for firm {firm_id}")
    return {"message": "GST deadlines updated", "config_data": row.config_data}


@router.post("/gst-deadlines/reset")
async def reset_gst_deadlines(
    current_user: User = Depends(deps.get_current_user),
    db: AsyncSession = Depends(deps.get_db),
) -> Any:
    """Reset GST deadlines to government defaults."""
    firm_id = str(current_user.firm_id)

    row = (await db.execute(
        select(FirmConfig).where(
            FirmConfig.firm_id == firm_id,
            FirmConfig.config_key == "gst_deadlines",
        )
    )).scalar_one_or_none()

    if row:
        row.config_data = GST_DEADLINES_DEFAULT
    else:
        row = FirmConfig(
            id=str(uuid.uuid4()),
            firm_id=firm_id,
            config_key="gst_deadlines",
            config_data=GST_DEADLINES_DEFAULT,
        )
        db.add(row)

    await db.commit()
    return {"message": "GST deadlines reset to defaults", "config_data": GST_DEADLINES_DEFAULT}
