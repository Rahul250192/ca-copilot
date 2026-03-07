import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional
import sqlalchemy as sa

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Integer, Boolean, Float, Table, Enum, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from app.db.base import Base

# Enums
class UserRole(str, PyEnum):
    OWNER = "owner"
    ADMIN = "admin"
    STAFF = "staff"

class SignupMethod(str, PyEnum):
    EMAIL = "email"
    PHONE = "phone"
    GOOGLE = "google"

class MessageRole(str, PyEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"

class Scope(str, PyEnum):
    FIRM = "FIRM"
    KIT = "KIT"
    CLIENT = "CLIENT"

class DocumentStatus(str, PyEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"

# Association Tables
conversation_kits = Table(
    "conversation_kits",
    Base.metadata,
    Column("conversation_id", UUID(as_uuid=True), ForeignKey("conversations.id"), primary_key=True),
    Column("kit_id", UUID(as_uuid=True), ForeignKey("kits.id"), primary_key=True),
)

service_kits = Table(
    "service_kits",
    Base.metadata,
    Column("service_id", UUID(as_uuid=True), ForeignKey("services.id"), primary_key=True),
    Column("kit_id", UUID(as_uuid=True), ForeignKey("kits.id"), primary_key=True),
)

client_services = Table(
    "client_services",
    Base.metadata,
    Column("client_id", UUID(as_uuid=True), ForeignKey("clients.id"), primary_key=True),
    Column("service_id", UUID(as_uuid=True), ForeignKey("services.id"), primary_key=True),
)

class Firm(Base):
    __tablename__ = "firms"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    users = relationship("User", back_populates="firm")
    clients = relationship("Client", back_populates="firm")

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=True)  # Nullable for phone-only signups
    hashed_password = Column(String, nullable=True)  # Nullable for Google OAuth signups
    full_name = Column(String)
    phone_number = Column(String, unique=True, nullable=True, index=True)  # Unique for phone-based login
    job_title = Column(String, nullable=True)
    subscription_plan = Column(String, default="free")
    role = Column(Enum(UserRole), default=UserRole.STAFF)
    signup_method = Column(String, default="email", nullable=False)
    firm_id = Column(UUID(as_uuid=True), ForeignKey("firms.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    firm = relationship("Firm", back_populates="users")

class Client(Base):
    __tablename__ = "clients"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    email = Column(String(255), nullable=False, server_default="admin@example.com") # Default for existing rows
    client_id = Column(String, unique=True, nullable=True)  # E.g. CL-001
    gstins = Column(JSONB, default=[])
    pan = Column(String, nullable=True)
    cin = Column(String, nullable=True)
    tan = Column(String, nullable=True)
    iec = Column(String, nullable=True)
    firm_id = Column(UUID(as_uuid=True), ForeignKey("firms.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    firm = relationship("Firm", back_populates="clients")
    conversations = relationship("Conversation", back_populates="client")
    services = relationship("Service", secondary=client_services, back_populates="clients")
    # documents relationship handled via query usually, but can be added

class Kit(Base):
    __tablename__ = "kits"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text)
    # Kits are global in this design, or could be firm specific. 
    # Requirement: "Topic Kits (attachable): specialist knowledge packs... attachable per conversation"
    created_at = Column(DateTime, default=datetime.utcnow)
    services = relationship("Service", secondary=service_kits, back_populates="kits")

class Service(Base):
    __tablename__ = "services"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    kits = relationship("Kit", secondary=service_kits, back_populates="services")
    clients = relationship("Client", secondary=client_services, back_populates="services")

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String)
    firm_id = Column(UUID(as_uuid=True), ForeignKey("firms.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    client = relationship("Client", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation")
    attached_kits = relationship("Kit", secondary=conversation_kits)

class Message(Base):
    __tablename__ = "messages"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    role = Column(Enum(MessageRole), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    conversation = relationship("Conversation", back_populates="messages")
    retrieval_logs = relationship("RetrievalLog", back_populates="message")

class Document(Base):
    __tablename__ = "documents"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String, nullable=False)
    scope = Column(Enum(Scope), nullable=False)
    
    firm_id = Column(UUID(as_uuid=True), ForeignKey("firms.id"), nullable=True) # Global usage might leave this null or specialized
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)
    kit_id = Column(UUID(as_uuid=True), ForeignKey("kits.id"), nullable=True)
    
    status = Column(Enum(DocumentStatus), default=DocumentStatus.UPLOADED)
    file_path = Column(String, nullable=True) 
    metadata_ = Column("metadata", JSONB, default={})
    
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        CheckConstraint(
            "(scope = 'FIRM' AND kit_id IS NULL AND client_id IS NULL) OR "
            "(scope = 'KIT' AND kit_id IS NOT NULL AND client_id IS NULL) OR "
            "(scope = 'CLIENT' AND client_id IS NOT NULL AND kit_id IS NULL)",
            name="check_scope_constraints"
        ),
    )
    
    embeddings = relationship("DocEmbedding", back_populates="document", cascade="all, delete-orphan")

class DocEmbedding(Base):
    __tablename__ = "doc_embeddings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer)
    embedding = Column(Vector(1536))
    metadata_ = Column("metadata", JSONB, default={})

    document = relationship("Document", back_populates="embeddings")

class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=False)
    cited_chunks = Column(JSONB) # Store list of chunk IDs or content snapshots
    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("Message", back_populates="retrieval_logs")

class GetInvoice(Base):
    __tablename__ = "get_invoice"
    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_name = Column(String(255))
    gst_number = Column(String(50))
    invoice_number = Column(String(100))
    invoice_date = Column(DateTime)
    currency = Column(String(10))
    amount = Column(String)
    gst_amount = Column(String)
    total_amount = Column(String)
    expenses_type = Column(String(100), nullable=True)
    source = Column(String(100))
    client_email_id = Column(String(255), nullable=True)
    file_path = Column(String(1000), nullable=True) # Storage path or URL to the original document
    received_at = Column(DateTime, server_default=sa.text('CURRENT_TIMESTAMP'))

class AccountingVoucher(Base):
    __tablename__ = "accounting_vouchers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voucher_type = Column(String(50), nullable=False) # e.g., Purchase, Sales, Journal
    supplier_invoice_no = Column(String(100), nullable=True)
    voucher_date = Column(DateTime, nullable=True)
    party_name = Column(String(255), nullable=False)
    gst_number = Column(String(50), nullable=True)
    narration = Column(Text, nullable=True)
    sub_total = Column(String(50), default="0") # Storing as string to avoid precision loss, similar to GetInvoice
    tax_amount = Column(String(50), default="0")
    total_amount = Column(String(50), default="0")
    sync_status = Column(String(50), default="NOT_SYNCED") # e.g. NOT_SYNCED, SYNCED
    firm_id = Column(UUID(as_uuid=True), ForeignKey("firms.id"), nullable=False)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    ledger_items = relationship("VoucherLedgerItem", back_populates="voucher", cascade="all, delete-orphan")
    tax_items = relationship("VoucherTaxItem", back_populates="voucher", cascade="all, delete-orphan")

class VoucherLedgerItem(Base):
    __tablename__ = "voucher_ledger_items"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voucher_id = Column(UUID(as_uuid=True), ForeignKey("accounting_vouchers.id"), nullable=False)
    ledger_name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    amount = Column(String(50), nullable=False)

    voucher = relationship("AccountingVoucher", back_populates="ledger_items")

class VoucherTaxItem(Base):
    __tablename__ = "voucher_tax_items"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    voucher_id = Column(UUID(as_uuid=True), ForeignKey("accounting_vouchers.id"), nullable=False)
    ledger_name = Column(String(255), nullable=False)
    description = Column(String(500), nullable=True)
    amount = Column(String(50), nullable=False)

    voucher = relationship("AccountingVoucher", back_populates="tax_items")


# ══════════════════════════════════════════════════════════════
# TALLY CONNECTOR TABLES
# Synced from Tally via /tally/sync-ledgers and /tally/sync-vouchers
# ══════════════════════════════════════════════════════════════

class Ledger(Base):
    """Tally master ledger data, synced via /tally/sync-ledgers.
    One row per ledger per company. Upserted on every sync."""
    __tablename__ = "ledgers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_name = Column(Text, nullable=False, index=True)
    name = Column(Text, nullable=False)
    parent = Column(Text, nullable=True)
    opening_balance = Column(sa.Numeric, nullable=True)     # positive = Cr, negative = Dr
    closing_balance = Column(sa.Numeric, nullable=True)
    party_gstin = Column(Text, nullable=True, index=True)
    gst_registration_type = Column(Text, nullable=True)
    state = Column(Text, nullable=True)
    pin_code = Column(Text, nullable=True)
    email = Column(Text, nullable=True)
    mobile = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    mailing_name = Column(Text, nullable=True)
    synced_at = Column(DateTime(timezone=True), server_default=sa.func.now())

    __table_args__ = (
        sa.UniqueConstraint('company_name', 'name', name='uq_ledgers_company_name'),
        Index('idx_ledgers_parent', 'company_name', 'parent'),
    )


class Voucher(Base):
    """Tally voucher headers, synced via /tally/sync-vouchers.
    One row per voucher. GUID is Tally's permanent unique ID."""
    __tablename__ = "vouchers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_name = Column(Text, nullable=False, index=True)
    date = Column(Text, nullable=True)                       # Tally returns YYYYMMDD
    voucher_type = Column(Text, nullable=True)               # Sales, Purchase, Payment, Receipt, etc.
    voucher_number = Column(Text, nullable=True)
    party_name = Column(Text, nullable=True)                 # primary party ledger name
    amount = Column(sa.Numeric, nullable=True)               # header-level net amount
    narration = Column(Text, nullable=True)
    guid = Column(Text, nullable=False)                      # Tally permanent GUID — never changes
    alter_id = Column(Text, default='')                      # increments on every Tally modification
    synced_at = Column(DateTime(timezone=True), server_default=sa.func.now())

    entries = relationship("VoucherEntry", back_populates="voucher",
                           foreign_keys="VoucherEntry.voucher_guid",
                           primaryjoin="Voucher.guid == foreign(VoucherEntry.voucher_guid)",
                           cascade="all, delete-orphan")

    __table_args__ = (
        sa.UniqueConstraint('company_name', 'guid', name='uq_vouchers_company_guid'),
        Index('idx_vouchers_date', 'company_name', 'date'),
        Index('idx_vouchers_type', 'company_name', 'voucher_type'),
        Index('idx_vouchers_party', 'company_name', 'party_name'),
        Index('idx_vouchers_guid', 'guid'),
    )


class VoucherEntry(Base):
    """Individual debit/credit ledger lines from ALLLEDGERENTRIES.LIST.
    A single ₹10,000 sales voucher produces 2 rows:
      Sundry Debtors   is_debit=true   amount=10000
      Sales Account    is_debit=false  amount=-10000"""
    __tablename__ = "voucher_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_name = Column(Text, nullable=False, index=True)
    voucher_guid = Column(Text, nullable=False, index=True)  # links to vouchers.guid
    voucher_date = Column(Text, nullable=True)               # denormalised for fast date filtering
    voucher_type = Column(Text, nullable=True)               # denormalised for fast type filtering
    ledger_name = Column(Text, nullable=False)
    amount = Column(sa.Numeric, nullable=True)               # positive = Cr, negative = Dr
    is_debit = Column(Boolean, default=False)
    synced_at = Column(DateTime(timezone=True), server_default=sa.func.now())

    voucher = relationship("Voucher", back_populates="entries",
                           foreign_keys=[voucher_guid],
                           primaryjoin="VoucherEntry.voucher_guid == Voucher.guid")

    __table_args__ = (
        sa.UniqueConstraint('company_name', 'voucher_guid', 'ledger_name', 'amount',
                            name='uq_ventry_company_guid_ledger_amount'),
        Index('idx_ventry_ledger', 'company_name', 'ledger_name'),
        Index('idx_ventry_date', 'company_name', 'voucher_date'),
    )
