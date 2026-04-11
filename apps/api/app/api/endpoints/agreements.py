import io
import json
from typing import Any, List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.api import deps
from app.models.models import User
from app.models.agreements import AgreementCategory, AgreementType, UserAgreementTemplate, AgreementDraft
from app.schemas import agreement as schemas
from app.services.agreement_pdf import generate_agreement_html, generate_docx_from_template, docx_to_preview_html

router = APIRouter()

# In-memory cache for preview templates (avoid re-downloading from Supabase)
_preview_cache: dict = {}


# ═══════════════════════════════════
#  CATEGORIES & TYPES
# ═══════════════════════════════════

@router.get("/categories", response_model=List[schemas.AgreementCategoryOut])
async def list_categories(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """List all agreement categories with their types."""
    query = (
        select(AgreementCategory)
        .options(selectinload(AgreementCategory.agreement_types))
        .order_by(AgreementCategory.display_order)
    )
    result = await db.execute(query)
    return result.scalars().unique().all()


@router.get("/types/{type_id}", response_model=schemas.AgreementTypeDetail)
async def get_agreement_type(
    type_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Get a single agreement type with default clauses and template fields."""
    query = select(AgreementType).where(AgreementType.id == type_id)
    result = await db.execute(query)
    atype = result.scalars().first()
    if not atype:
        raise HTTPException(status_code=404, detail="Agreement type not found")
    return atype


# ═══════════════════════════════════
#  USER TEMPLATE CUSTOMIZATION
# ═══════════════════════════════════

@router.get("/types/{type_id}/template", response_model=schemas.TemplateResponse)
async def get_template(
    type_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Get user's saved template or default."""
    q = select(AgreementType).where(AgreementType.id == type_id)
    r = await db.execute(q)
    atype = r.scalars().first()
    if not atype:
        raise HTTPException(status_code=404, detail="Agreement type not found")

    uq = select(UserAgreementTemplate).where(
        UserAgreementTemplate.user_id == current_user.id,
        UserAgreementTemplate.agreement_type_id == type_id,
    )
    ur = await db.execute(uq)
    user_tmpl = ur.scalars().first()

    if user_tmpl:
        return schemas.TemplateResponse(
            agreement_type=atype, is_customized=True, clauses=user_tmpl.custom_clauses,
        )
    else:
        return schemas.TemplateResponse(
            agreement_type=atype, is_customized=False, clauses=atype.default_clauses,
        )


@router.put("/types/{type_id}/template", response_model=schemas.UserTemplateOut)
async def save_template(
    type_id: UUID,
    body: schemas.UserTemplateSave,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Save or update user's customized template."""
    q = select(AgreementType).where(AgreementType.id == type_id)
    r = await db.execute(q)
    if not r.scalars().first():
        raise HTTPException(status_code=404, detail="Agreement type not found")

    uq = select(UserAgreementTemplate).where(
        UserAgreementTemplate.user_id == current_user.id,
        UserAgreementTemplate.agreement_type_id == type_id,
    )
    ur = await db.execute(uq)
    user_tmpl = ur.scalars().first()
    clauses_data = [c.dict() for c in body.clauses]

    if user_tmpl:
        user_tmpl.custom_clauses = clauses_data
        user_tmpl.updated_at = datetime.utcnow()
    else:
        user_tmpl = UserAgreementTemplate(
            user_id=current_user.id,
            agreement_type_id=type_id,
            custom_clauses=clauses_data,
        )
        db.add(user_tmpl)

    await db.commit()
    await db.refresh(user_tmpl)
    return user_tmpl


@router.delete("/types/{type_id}/template")
async def reset_template(
    type_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Reset to default template."""
    uq = select(UserAgreementTemplate).where(
        UserAgreementTemplate.user_id == current_user.id,
        UserAgreementTemplate.agreement_type_id == type_id,
    )
    ur = await db.execute(uq)
    user_tmpl = ur.scalars().first()
    if not user_tmpl:
        raise HTTPException(status_code=404, detail="No custom template found")
    await db.delete(user_tmpl)
    await db.commit()
    return {"status": "ok", "message": "Template reset to default"}


# ═══════════════════════════════════
#  DRAFTS
# ═══════════════════════════════════

@router.post("/drafts", response_model=schemas.DraftOut)
async def create_draft(
    body: schemas.DraftCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Create a new agreement draft."""
    # Verify agreement type
    q = select(AgreementType).where(AgreementType.id == body.agreement_type_id)
    r = await db.execute(q)
    atype = r.scalars().first()
    if not atype:
        raise HTTPException(status_code=404, detail="Agreement type not found")

    draft = AgreementDraft(
        user_id=current_user.id,
        agreement_type_id=body.agreement_type_id,
        title=body.title or f"{atype.name} — Draft",
        field_values=body.field_values,
        selected_clauses=[c.dict() for c in body.selected_clauses],
    )
    db.add(draft)
    await db.commit()
    await db.refresh(draft)
    return draft


@router.get("/drafts", response_model=List[schemas.DraftListItem])
async def list_drafts(
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """List user's drafts."""
    q = (
        select(AgreementDraft)
        .where(AgreementDraft.user_id == current_user.id)
        .order_by(AgreementDraft.updated_at.desc())
    )
    r = await db.execute(q)
    return r.scalars().all()


@router.get("/drafts/{draft_id}", response_model=schemas.DraftOut)
async def get_draft(
    draft_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Get draft details."""
    q = select(AgreementDraft).where(
        AgreementDraft.id == draft_id,
        AgreementDraft.user_id == current_user.id,
    )
    r = await db.execute(q)
    draft = r.scalars().first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.put("/drafts/{draft_id}", response_model=schemas.DraftOut)
async def update_draft(
    draft_id: UUID,
    body: schemas.DraftUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Update a draft."""
    q = select(AgreementDraft).where(
        AgreementDraft.id == draft_id,
        AgreementDraft.user_id == current_user.id,
    )
    r = await db.execute(q)
    draft = r.scalars().first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    if body.title is not None:
        draft.title = body.title
    if body.field_values is not None:
        draft.field_values = body.field_values
    if body.selected_clauses is not None:
        draft.selected_clauses = [c.dict() for c in body.selected_clauses]
    draft.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(draft)
    return draft


@router.delete("/drafts/{draft_id}")
async def delete_draft(
    draft_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Delete a draft."""
    q = select(AgreementDraft).where(
        AgreementDraft.id == draft_id,
        AgreementDraft.user_id == current_user.id,
    )
    r = await db.execute(q)
    draft = r.scalars().first()
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    await db.delete(draft)
    await db.commit()
    return {"status": "ok"}


# ═══════════════════════════════════
#  AI CLAUSE SELECTION
# ═══════════════════════════════════

@router.post("/ai-select-clauses")
async def ai_select_clauses(
    body: schemas.AIClauseRequest,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    AI-powered clause recommendation.
    Returns a list of clause IDs that should be enabled based on context.
    Falls back to all is_default=True clauses if AI is unavailable.
    """
    q = select(AgreementType).where(AgreementType.id == body.agreement_type_id)
    r = await db.execute(q)
    atype = r.scalars().first()
    if not atype:
        raise HTTPException(status_code=404, detail="Agreement type not found")

    clauses = atype.default_clauses or []

    # Try AI-powered selection
    try:
        from app.services.ai_client import call_ai
        import asyncio

        clause_summary = "\n".join(
            [f"- {c['id']}: {c['title']} (default={'yes' if c.get('is_default') else 'no'})" for c in clauses]
        )

        prompt = f"""You are a legal expert specializing in Indian law.
The user is creating a "{atype.name}" agreement.
{f'Additional context: {body.context}' if body.context else ''}

Here are the available clauses:
{clause_summary}

Based on best practices and the context, recommend which clauses should be ENABLED.
Return ONLY a JSON array of clause IDs that should be enabled.
Example: ["pd_1", "pd_2", "pd_5"]"""

        reply = await call_ai(
            system_prompt="You are a legal clause recommender. Return ONLY a JSON array.",
            user_content=prompt,
            max_tokens=500,
            temperature=0.3,
        )

        import re
        reply = reply.strip()
        match = re.search(r'\[.*\]', reply, re.DOTALL)
        if match:
            recommended_ids = json.loads(match.group())
            return {
                "recommended_clause_ids": recommended_ids,
                "source": "ai",
                "message": "AI-recommended clauses based on your context.",
            }

    except Exception as e:
        print(f"AI clause selection fallback: {e}")

    # Fallback: return default clauses
    default_ids = [c["id"] for c in clauses if c.get("is_default", True)]
    return {
        "recommended_clause_ids": default_ids,
        "source": "default",
        "message": "Using default clause selection.",
    }


# ═══════════════════════════════════
#  PDF GENERATION (HTML PREVIEW)
# ═══════════════════════════════════

@router.post("/generate-preview")
async def generate_preview(
    body: schemas.GeneratePDFRequest,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """Generate HTML preview of the agreement."""
    q = select(AgreementType).where(AgreementType.id == body.agreement_type_id)
    r = await db.execute(q)
    atype = r.scalars().first()
    if not atype:
        raise HTTPException(status_code=404, detail="Agreement type not found")

    clauses = [c.dict() for c in body.selected_clauses]
    html = generate_agreement_html(
        agreement_name=atype.name,
        agreement_desc=atype.description or "",
        field_values=body.field_values,
        clauses=clauses,
    )

    # Optionally update draft status
    if body.draft_id:
        dq = select(AgreementDraft).where(
            AgreementDraft.id == body.draft_id,
            AgreementDraft.user_id == current_user.id,
        )
        dr = await db.execute(dq)
        draft = dr.scalars().first()
        if draft:
            draft.status = "generated"
            draft.updated_at = datetime.utcnow()
            await db.commit()

    return {"html": html, "agreement_name": atype.name}


# ═══════════════════════════════════
#  DOCX TEMPLATE PREVIEW (HTML)
# ═══════════════════════════════════

@router.get("/types/{type_id}/preview-template")
async def get_preview_template(
    type_id: UUID,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get the .docx template rendered as HTML with named placeholder markers.
    Used for live preview — client does string replacement on keystrokes.
    Returns {html, has_template} — if no template, has_template=false.
    """
    q = select(AgreementType).where(AgreementType.id == type_id)
    r = await db.execute(q)
    atype = r.scalars().first()
    if not atype:
        raise HTTPException(status_code=404, detail="Agreement type not found")

    if not atype.template_path:
        return {"html": None, "has_template": False}

    cache_key = str(type_id)
    if cache_key in _preview_cache:
        return {"html": _preview_cache[cache_key], "has_template": True}

    # Download template from Supabase
    try:
        from app.services.storage import SupabaseStorageService
        storage = SupabaseStorageService()
        if not storage.enabled:
            raise Exception("Supabase not available")

        template_data = storage.client.storage.from_("agreement-template").download(atype.template_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not download template: {str(e)}")

    # Convert to HTML with placeholder markers
    html = docx_to_preview_html(template_data, template_path=atype.template_path)

    # Cache it
    _preview_cache[cache_key] = html

    return {"html": html, "has_template": True}


#  DOCX GENERATION (FROM TEMPLATE)
# ═══════════════════════════════════

@router.post("/generate-docx")
async def generate_docx(
    body: schemas.GeneratePDFRequest,
    db: AsyncSession = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Generate a filled .docx from a Supabase-stored template.
    Falls back to error if no template exists for this type.
    """
    q = select(AgreementType).where(AgreementType.id == body.agreement_type_id)
    r = await db.execute(q)
    atype = r.scalars().first()
    if not atype:
        raise HTTPException(status_code=404, detail="Agreement type not found")

    if not atype.template_path:
        raise HTTPException(
            status_code=400,
            detail="No .docx template available for this agreement type. Use HTML preview instead."
        )

    # Download template from Supabase
    try:
        from app.services.storage import SupabaseStorageService
        storage = SupabaseStorageService()
        if not storage.enabled:
            raise Exception("Supabase not available")

        template_data = storage.client.storage.from_("agreement-template").download(atype.template_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not download template: {str(e)}")

    # Fill the template
    filled_docx = generate_docx_from_template(
        template_bytes=template_data,
        field_values=body.field_values,
        template_path=atype.template_path,
    )

    # Generate filename
    safe_name = atype.name.replace(' ', '_').replace('/', '_')
    party_a = body.field_values.get('landlord_name', body.field_values.get('party_a_name', ''))
    party_b = body.field_values.get('tenant_name', body.field_values.get('party_b_name', ''))
    filename = f"{safe_name}"
    if party_a:
        filename += f"_{party_a.replace(' ', '_')}"
    if party_b:
        filename += f"_{party_b.replace(' ', '_')}"
    filename += ".docx"

    return StreamingResponse(
        io.BytesIO(filled_docx),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
