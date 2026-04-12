"""
Invoice Parser Service
──────────────────────
Pipeline: PDF/Image → LlamaParse (text extraction) → Rule-based parser (structured extraction) → DB

No AI API calls — uses regex-based extraction for Indian invoices.
"""

import logging
from typing import Any, Dict

from app.core.config import settings
from app.services.banking.statement_parser import extract_text_llamaparse
from app.services.invoice_parser_rules import parse_invoice_from_text

logger = logging.getLogger(__name__)


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
    
    # Step 2: Structure with rule-based parser (no AI cost)
    structured = parse_invoice_from_text(extracted_text, voucher_type)
    
    logger.info(f"✅ Invoice extracted: {structured.get('invoice_number', 'N/A')} | "
                f"Vendor: {structured.get('vendor_name', 'Unknown')} | "
                f"Total: {structured.get('total_amount', 0)}")
    
    return structured
