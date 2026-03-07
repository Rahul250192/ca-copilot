import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.db.base import Base


class AgreementCategory(Base):
    __tablename__ = "agreement_categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    icon = Column(String, nullable=True)
    display_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    agreement_types = relationship("AgreementType", back_populates="category", order_by="AgreementType.display_order")


class AgreementType(Base):
    __tablename__ = "agreement_types"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    category_id = Column(UUID(as_uuid=True), ForeignKey("agreement_categories.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    icon = Column(String, nullable=True)
    display_order = Column(Integer, default=0)
    # Default clauses: [{id, title, content, is_default, order}]
    default_clauses = Column(JSONB, nullable=False, default=[])
    # Template fields: [{name, label, type, required, placeholder}]
    template_fields = Column(JSONB, nullable=False, server_default='[]')
    # Path in Supabase storage to the base template (optional)
    template_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    category = relationship("AgreementCategory", back_populates="agreement_types")


class UserAgreementTemplate(Base):
    __tablename__ = "user_agreement_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    agreement_type_id = Column(UUID(as_uuid=True), ForeignKey("agreement_types.id"), nullable=False)
    custom_clauses = Column(JSONB, nullable=False, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agreement_type = relationship("AgreementType")


class AgreementDraft(Base):
    __tablename__ = "agreement_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    agreement_type_id = Column(UUID(as_uuid=True), ForeignKey("agreement_types.id"), nullable=False)
    title = Column(String, nullable=True)
    status = Column(String, default="draft")  # draft, generated
    # Form field values filled by user: {field_name: value}
    field_values = Column(JSONB, nullable=False, default={})
    # Selected clauses (with edits): [{id, title, content, is_default, order}]
    selected_clauses = Column(JSONB, nullable=False, default=[])
    # Path to generated PDF in storage
    generated_pdf_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    agreement_type = relationship("AgreementType")
