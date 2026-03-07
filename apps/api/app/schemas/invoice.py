from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class InvoiceBase(BaseModel):
    vendor_name: str
    gst_number: Optional[str] = None
    invoice_number: str
    invoice_date: datetime
    currency: Optional[str] = "INR"
    amount: Optional[str] = None
    gst_amount: Optional[str] = None
    total_amount: Optional[str] = None
    expenses_type: Optional[str] = None
    source: str
    client_email_id: Optional[str] = None

class InvoiceCreate(InvoiceBase):
    pass

class InvoiceUpdate(BaseModel):
    expenses_type: Optional[str] = None

class InvoiceInDBBase(InvoiceBase):
    id: int
    received_at: datetime

    class Config:
        from_attributes = True

class Invoice(InvoiceInDBBase):
    pass
