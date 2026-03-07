from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


# --- Clause ---
class Clause(BaseModel):
    id: str
    title: str
    content: str
    is_default: bool = True
    order: int = 0


# --- Template Field ---
class TemplateField(BaseModel):
    name: str
    label: str
    type: str = "text"  # text, date, number, textarea, select
    required: bool = False
    placeholder: Optional[str] = None
    options: Optional[List[str]] = None  # for select type


# --- Agreement Type ---
class AgreementTypeBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None

class AgreementTypeOut(AgreementTypeBase):
    id: UUID
    display_order: int = 0

    class Config:
        from_attributes = True

class AgreementTypeDetail(AgreementTypeOut):
    default_clauses: List[Clause] = []
    template_fields: List[TemplateField] = []
    template_path: Optional[str] = None

    class Config:
        from_attributes = True


# --- Category ---
class AgreementCategoryBase(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None

class AgreementCategoryOut(AgreementCategoryBase):
    id: UUID
    display_order: int = 0
    agreement_types: List[AgreementTypeOut] = []

    class Config:
        from_attributes = True


# --- User Template ---
class UserTemplateOut(BaseModel):
    id: UUID
    user_id: UUID
    agreement_type_id: UUID
    custom_clauses: List[Clause] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class UserTemplateSave(BaseModel):
    clauses: List[Clause]


# --- Template response ---
class TemplateResponse(BaseModel):
    agreement_type: AgreementTypeDetail
    is_customized: bool = False
    clauses: List[Clause] = []


# --- Draft ---
class DraftCreate(BaseModel):
    agreement_type_id: UUID
    title: Optional[str] = None
    field_values: Dict[str, Any] = {}
    selected_clauses: List[Clause] = []

class DraftUpdate(BaseModel):
    title: Optional[str] = None
    field_values: Optional[Dict[str, Any]] = None
    selected_clauses: Optional[List[Clause]] = None

class DraftOut(BaseModel):
    id: UUID
    user_id: UUID
    agreement_type_id: UUID
    title: Optional[str] = None
    status: str = "draft"
    field_values: Dict[str, Any] = {}
    selected_clauses: List[Clause] = []
    generated_pdf_path: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class DraftListItem(BaseModel):
    id: UUID
    agreement_type_id: UUID
    title: Optional[str] = None
    status: str = "draft"
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# --- AI Clause Selection ---
class AIClauseRequest(BaseModel):
    agreement_type_id: UUID
    context: Optional[str] = None  # user-provided description of their needs


# --- PDF Generation ---
class GeneratePDFRequest(BaseModel):
    agreement_type_id: UUID
    field_values: Dict[str, Any] = {}
    selected_clauses: List[Clause] = []
    draft_id: Optional[UUID] = None  # optional — link to draft
