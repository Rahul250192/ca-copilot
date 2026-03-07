from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

class VoucherLedgerItemBase(BaseModel):
    ledger_name: str
    description: Optional[str] = None
    amount: str

class VoucherLedgerItemCreate(VoucherLedgerItemBase):
    pass

class VoucherLedgerItem(VoucherLedgerItemBase):
    id: UUID
    voucher_id: UUID

    class Config:
        from_attributes = True

class VoucherTaxItemBase(BaseModel):
    ledger_name: str
    description: Optional[str] = None
    amount: str

class VoucherTaxItemCreate(VoucherTaxItemBase):
    pass

class VoucherTaxItem(VoucherTaxItemBase):
    id: UUID
    voucher_id: UUID

    class Config:
        from_attributes = True

class AccountingVoucherBase(BaseModel):
    voucher_type: str
    supplier_invoice_no: Optional[str] = None
    voucher_date: Optional[datetime] = None
    party_name: str
    gst_number: Optional[str] = None
    narration: Optional[str] = None
    sub_total: Optional[str] = "0"
    tax_amount: Optional[str] = "0"
    total_amount: Optional[str] = "0"
    sync_status: Optional[str] = "NOT_SYNCED"
    client_id: Optional[UUID] = None

class AccountingVoucherCreate(AccountingVoucherBase):
    ledger_items: List[VoucherLedgerItemCreate] = []
    tax_items: List[VoucherTaxItemCreate] = []

class AccountingVoucher(AccountingVoucherBase):
    id: UUID
    firm_id: UUID
    created_at: datetime
    updated_at: datetime
    ledger_items: List[VoucherLedgerItem] = []
    tax_items: List[VoucherTaxItem] = []

    class Config:
        from_attributes = True

class CheckDuplicateRequest(BaseModel):
    supplier_invoice_no: str
    party_name: str

class CheckDuplicateResponse(BaseModel):
    is_duplicate: bool
    voucher_id: Optional[UUID] = None
