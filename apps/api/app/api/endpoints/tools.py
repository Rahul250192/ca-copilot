from typing import Any, Dict, List
from fastapi import APIRouter, Depends, HTTPException
from app.api import deps
from app.services.gst.verification import get_gstin_details
from app.services.gst.certificate import get_certificate_templates
from app.services.gst.certificate_remote import get_remote_templates, get_remote_template_url
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

@router.get("/certificate-templates/remote")
async def list_remote_certificate_templates(
    category: str = "",
    current_user: User = Depends(deps.get_current_user),
) -> List[Dict[str, str]]:
    """
    Fetch a list of remote templates from Supabase, optionally filtered by category folder.
    """
    return get_remote_templates(category)

@router.get("/certificate-templates/remote/url")
async def get_remote_template_signed_url(
    filename: str,
    current_user: User = Depends(deps.get_current_user),
) -> Dict[str, str]:
    """
    Get a signed URL for a remote template.
    """
    url = get_remote_template_url(filename)
    if not url:
        raise HTTPException(status_code=404, detail="Template not found or error generating URL")
    return {"url": url}

@router.get("/certificate-templates/remote/preview")
async def get_remote_template_preview(
    filename: str,
    current_user: User = Depends(deps.get_current_user),
) -> Dict[str, str]:
    """
    Get the HTML preview for a remote DOCX template.
    """
    if not filename.endswith(".docx"):
        raise HTTPException(status_code=400, detail="Only DOCX templates can be previewed as HTML")
        
    try:
        from app.services.storage import SupabaseStorageService
        storage = SupabaseStorageService()
        if not storage.enabled:
            raise Exception("Supabase not available")
            
        template_data = storage.client.storage.from_("certificate-template").download(filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not download template: {str(e)}")

    try:
        from app.services.agreement_pdf import docx_to_preview_html
        html = docx_to_preview_html(template_data)
        return {"html": html}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating preview: {str(e)}")
