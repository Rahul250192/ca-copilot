from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from app.api import deps
from app.services.gst.verification import get_gstin_details
from app.models.models import User

router = APIRouter()

@router.get("/gstin-validate")
async def gstin_validate(
    gstin: str,
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Validate a single GSTIN using Appyflow.
    """
    try:
        details = get_gstin_details(gstin)
        return details
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")
