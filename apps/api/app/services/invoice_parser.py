"""
Invoice Parser Service
──────────────────────
Replaces n8n invoice processing pipeline.
Pipeline: PDF/Image → LlamaParse (text extraction) → Claude (structured extraction) → DB
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from app.core.config import settings
from app.services.banking.statement_parser import extract_text_llamaparse, _repair_json
from app.services.ai_client import call_ai_json

logger = logging.getLogger(__name__)


INVOICE_EXTRACTION_PROMPT = """You are an AI specializing in extracting structured data from Indian invoices, bills, and receipts.

Given the raw text extracted from an invoice document, extract all relevant information into a strict JSON object.

**Rules:**
1. Extract ALL available fields accurately.
2. Dates must be ISO format: "YYYY-MM-DD"
3. Amount fields must be plain numbers (no commas, no ₹ symbol).
4. GSTIN format: 15-character alphanumeric (e.g., "07AABCU9603R1ZM").
5. For expenses_type, classify into one of:
   Sales, Purchase, Credit Note, Debit Note, Expense, Services, Rent, 
   Salary, Utilities, Insurance, Bank Charges, Professional Fees, 
   Advertising, Travel, Maintenance, Government, Other
6. If a voucher_type hint is provided, prefer that classification.
7. Extract line items if present in the invoice.

Return ONLY this exact JSON structure (no extra text, no markdown fences):
{
    "vendor_name": "string — the seller/vendor/supplier name",
    "gst_number": "string — vendor GSTIN or null",
    "buyer_gstin": "string — buyer/purchaser GSTIN or null",
    "invoice_number": "string",
    "invoice_date": "YYYY-MM-DD or null",
    "currency": "INR",
    "amount": number or null (subtotal before tax),
    "cgst_amount": number or null,
    "sgst_amount": number or null,
    "igst_amount": number or null,
    "gst_amount": number or null (total GST = CGST + SGST + IGST),
    "total_amount": number or null (grand total including tax),
    "expenses_type": "one of the categories above",
    "hsn_code": "string or null — primary HSN/SAC code",
    "place_of_supply": "string or null",
    "line_items": [
        {
            "description": "item/service description",
            "hsn_sac": "HSN or SAC code or null",
            "quantity": "string — e.g. '1', '2.5 Kg'",
            "unit_price": number or null,
            "amount": number or null (line total before tax)
        }
    ]
}"""


async def extract_invoice_data(file_bytes: bytes, filename: str, voucher_type: str = "") -> Dict[str, Any]:
    """Extract structured invoice data from a file.
    
    Args:
        file_bytes: Raw file content
        filename: Original filename
        voucher_type: Optional hint for classification (Sales, Purchase, etc.)
    
    Returns:
        Structured invoice data dict
    """
    
    # Step 1: Extract text via LlamaParse
    logger.info(f"📄 Processing invoice: {filename} ({len(file_bytes)} bytes)")
    extracted_text = await extract_text_llamaparse(file_bytes, filename)
    
    if not extracted_text or len(extracted_text.strip()) < 50:
        raise ValueError(f"Could not extract meaningful text from {filename}")
    
    logger.info(f"📝 Extracted {len(extracted_text)} chars from {filename}")
    
    # Step 2: Structure with Claude
    structured = await _structure_invoice_with_claude(extracted_text, voucher_type)
    
    logger.info(f"✅ Invoice extracted: {structured.get('invoice_number', 'N/A')} | "
                f"Vendor: {structured.get('vendor_name', 'Unknown')} | "
                f"Total: {structured.get('total_amount', 0)}")
    
    return structured


async def _structure_invoice_with_claude(extracted_text: str, voucher_type: str = "") -> Dict[str, Any]:
    """Use AI to structure invoice text into JSON."""
    
    # Add voucher type hint if provided
    user_content = extracted_text
    if voucher_type:
        user_content = f"[HINT: This document is likely a {voucher_type} invoice]\n\n{extracted_text}"
    
    logger.info(f"Sending {len(extracted_text)} chars for invoice extraction...")
    
    try:
        return await call_ai_json(
            system_prompt=INVOICE_EXTRACTION_PROMPT,
            user_content=user_content,
            temperature=0.1,
            max_tokens=4000,
        )
    except Exception as e:
        logger.error(f"AI invoice extraction failed: {e}")
        raise ValueError(f"AI extraction failed: {e}")
