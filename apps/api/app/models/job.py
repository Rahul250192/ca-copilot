from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
import enum

from app.db.base import Base

class JobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class JobType(str, enum.Enum):
    STATEMENT3 = "statement3"
    STATEMENT3_FIRC = "statement3_firc"
    ANNEXURE_B = "annexure_b"
    GST_VERIFY = "gst_verify"
    GST_RECON = "gst_recon"

class Job(Base):
    __tablename__ = "jobs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4, index=True)
    job_type = Column(String, nullable=False) # Store as string for flexibility, validated by schema
    status = Column(String, default=JobStatus.QUEUED, nullable=False)
    
    input_files = Column(JSONB, default=[]) # List of file paths/IDs
    output_files = Column(JSONB, default=[]) # List of result paths
    
    # Metadata
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    firm_id = Column(UUID(as_uuid=True), ForeignKey("firms.id"), nullable=False, index=True)
    client_id = Column(UUID(as_uuid=True), ForeignKey("clients.id"), nullable=True, index=True)

    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User", backref="jobs")
    events = relationship("JobEvent", back_populates="job", cascade="all, delete-orphan", order_by="JobEvent.created_at")

class JobEvent(Base):
    __tablename__ = "job_events"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id"), nullable=False, index=True)
    level = Column(String, default="INFO")
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    job = relationship("Job", back_populates="events")
