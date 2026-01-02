import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional

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
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name = Column(String)
    role = Column(Enum(UserRole), default=UserRole.STAFF)
    firm_id = Column(UUID(as_uuid=True), ForeignKey("firms.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    firm = relationship("Firm", back_populates="users")

class Client(Base):
    __tablename__ = "clients"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
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
