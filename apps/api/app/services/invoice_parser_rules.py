"""
Production-Grade Rule-Based Invoice Parser for Indian Documents
═══════════════════════════════════════════════════════════════
Extracts structured invoice data from LlamaParse markdown output
using regex patterns. No AI API calls needed.

Handles all common Indian invoice formats:
─────────────────────────────────────────
• GST Tax Invoice (B2B with CGST/SGST/IGST breakup)
• Bill of Supply (composition/exempt dealers)
• E-commerce invoices (Amazon, Flipkart, Myntra, Meesho)
• Utility bills (Airtel, Jio, BSNL, BESCOM, Tata Power)
• Credit Note / Debit Note
• E-invoice with IRN number
• Professional service invoices (CA/CS/Legal)
• Hotel & Travel invoices
• Fuel (petrol pump) bills
• Restaurant / Food delivery invoices
• Rent receipts
• Government challans (TDS/GST)
• Medical / Hospital bills
• Subscription / SaaS invoices

Indian formatting handled:
──────────────────────────
• Indian number system (1,23,456.78 — lakhs/crores)
• ₹ / Rs. / INR currency symbols
• DD/MM/YYYY, DD-MMM-YYYY, DD.MM.YYYY date formats
• GSTIN validation (15-char alphanumeric)
• HSN (goods, 4-8 digits) and SAC (services, 6 digits) codes
• State codes (01-38) for Place of Supply
• Reverse Charge Mechanism (RCM) detection
• Multiple GST rates (0%, 5%, 12%, 18%, 28%)
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# GSTIN Extraction
# ═══════════════════════════════════════════════════════════

# GSTIN format: 2 digits state + 10 char PAN + 1 entity + 1 check digit
GSTIN_RE = re.compile(r'\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z0-9][A-Z][A-Z0-9])\b')

# State Code → State Name (for Place of Supply)
STATE_CODES = {
    "01": "Jammu & Kashmir", "02": "Himachal Pradesh", "03": "Punjab",
    "04": "Chandigarh", "05": "Uttarakhand", "06": "Haryana",
    "07": "Delhi", "08": "Rajasthan", "09": "Uttar Pradesh",
    "10": "Bihar", "11": "Sikkim", "12": "Arunachal Pradesh",
    "13": "Nagaland", "14": "Manipur", "15": "Mizoram",
    "16": "Tripura", "17": "Meghalaya", "18": "Assam",
    "19": "West Bengal", "20": "Jharkhand", "21": "Odisha",
    "22": "Chhattisgarh", "23": "Madhya Pradesh", "24": "Gujarat",
    "25": "Daman & Diu", "26": "Dadra & Nagar Haveli", "27": "Maharashtra",
    "29": "Karnataka", "30": "Goa", "32": "Kerala",
    "33": "Tamil Nadu", "34": "Puducherry", "35": "Andaman & Nicobar",
    "36": "Telangana", "37": "Andhra Pradesh", "38": "Ladakh",
}


def _extract_gstins(text: str) -> Dict[str, Optional[str]]:
    """
    Extract seller and buyer GSTIN. Uses context clues to determine which is which.
    Returns: {"seller_gstin": "...", "buyer_gstin": "...", "seller_state": "...", "buyer_state": "..."}
    """
    result = {"seller_gstin": None, "buyer_gstin": None,
              "seller_state": None, "buyer_state": None}

    # Find all GSTINs with their positions
    matches = list(GSTIN_RE.finditer(text))
    if not matches:
        return result

    # Unique GSTINs only (same GSTIN may appear multiple times)
    seen = set()
    unique_matches = []
    for m in matches:
        gstin = m.group(1)
        if gstin not in seen:
            seen.add(gstin)
            unique_matches.append(m)

    if len(unique_matches) >= 2:
        # Check context around each GSTIN to determine seller vs buyer
        for m in unique_matches:
            gstin = m.group(1)
            # Look at text BEFORE this GSTIN (within 150 chars)
            start = max(0, m.start() - 150)
            context_before = text[start:m.start()].lower()
            # Also look at text AFTER (within 50 chars for "(Seller)" labels)
            end = min(len(text), m.end() + 50)
            context_after = text[m.end():end].lower()

            is_buyer = any(kw in context_before for kw in [
                'bill to', 'buyer', 'customer', 'ship to', 'shipped to',
                'consignee', 'sold to', 'recipient', 'client',
                'details of receiver', 'billed to', 'm/s',
            ]) or any(kw in context_after for kw in ['buyer', 'recipient'])

            is_seller = any(kw in context_before for kw in [
                'sold by', 'seller', 'supplier', 'vendor',
                'billed by', 'ship from', 'consignor',
                'issued by', 'details of supplier', 'service provider',
            ]) or any(kw in context_after for kw in ['seller', 'supplier'])

            if is_buyer and not is_seller:
                if not result["buyer_gstin"]:
                    result["buyer_gstin"] = gstin
            elif is_seller and not is_buyer:
                if not result["seller_gstin"]:
                    result["seller_gstin"] = gstin

        # If context didn't help, first = seller, second = buyer
        if not result["seller_gstin"]:
            result["seller_gstin"] = unique_matches[0].group(1)
        if not result["buyer_gstin"]:
            for m in unique_matches:
                if m.group(1) != result["seller_gstin"]:
                    result["buyer_gstin"] = m.group(1)
                    break

    elif len(unique_matches) == 1:
        gstin = unique_matches[0].group(1)
        # Check if this single GSTIN appears in a buyer context
        start = max(0, unique_matches[0].start() - 200)
        context_before = text[start:unique_matches[0].start()].lower()
        is_buyer_context = any(kw in context_before for kw in [
            'bill to', 'buyer', 'customer', 'ship to', 'shipped to',
            'consignee', 'sold to', 'recipient', 'client',
            'details of receiver', 'billed to', 'm/s',
        ])
        if is_buyer_context:
            result["buyer_gstin"] = gstin
        else:
            result["seller_gstin"] = gstin

    # Derive state from GSTIN state code
    if result["seller_gstin"]:
        result["seller_state"] = STATE_CODES.get(result["seller_gstin"][:2])
    if result["buyer_gstin"]:
        result["buyer_state"] = STATE_CODES.get(result["buyer_gstin"][:2])

    return result


# ═══════════════════════════════════════════════════════════
# Invoice Number Extraction
# ═══════════════════════════════════════════════════════════

INVOICE_NO_PATTERNS = [
    # Markdown bullet: "- **Invoice No.**: HKNCHO/25-26/87" — must come first
    re.compile(r'\*\*Invoice\s*No\.?\*\*\s*[:\s]*([A-Za-z0-9/\-_]+(?:[/\-][A-Za-z0-9]+)*)', re.IGNORECASE),
    # Bold label on same line: "**Invoice No. :** 385"
    re.compile(r'\*\*Invoice\s*No\.?\s*[:\s]*\*\*\s*[:\s]*([A-Za-z0-9/\-_]+(?:[/\-][A-Za-z0-9]+)*)', re.IGNORECASE),
    # Bold label with value on next line: "**Invoice No.**\nIN/2025-2026/079"
    re.compile(r'\*\*Invoice\s*No\.?\*\*\s*\n\s*([A-Za-z0-9/\-_]+(?:[/\-][A-Za-z0-9]+)*)', re.IGNORECASE),
    # Standard: "Invoice No: INV-2024-001" or "Invoice Number: ABC/123"
    re.compile(r'(?:Invoice|Inv|Tax\s*Invoice)\s*(?:No|Number|#|Num|Ref)[.:\s]*([A-Za-z0-9/\-_]+(?:[/\-][A-Za-z0-9]+)*)', re.IGNORECASE),
    # "Bill No: 1234" — common in retail
    re.compile(r'Bill\s*(?:No|Number|#)[.:\s]*([A-Za-z0-9/\-_]+)', re.IGNORECASE),
    # "Invoice: ABC-123"
    re.compile(r'(?:Invoice|Bill)\s*:\s*([A-Za-z0-9/\-_]+)', re.IGNORECASE),
    # "Reference No: REF1234" — require alphanumeric start (not "erence")
    re.compile(r'(?:Ref|Reference)\s*(?:No|Number|#)\s*[.:\s]+([A-Za-z0-9][A-Za-z0-9/\-_]*)', re.IGNORECASE),
    # IRN for E-invoice
    re.compile(r'IRN\s*[:\s]*([A-Fa-f0-9]{64})', re.IGNORECASE),
    # Credit Note / Debit Note
    re.compile(r'(?:Credit|Debit)\s*(?:Note)\s*(?:No|Number|#)?[.:\s]*([A-Za-z0-9/\-_]+)', re.IGNORECASE),
    # Document No (general)
    re.compile(r'(?:Doc|Document)\s*(?:No|Number|#)?[.:\s]*([A-Za-z0-9/\-_]+)', re.IGNORECASE),
]


# ═══════════════════════════════════════════════════════════
# Date Extraction — All Indian Formats
# ═══════════════════════════════════════════════════════════

DATE_KEYWORD_PATTERNS = [
    re.compile(r'(?:Invoice\s*Date|Date\s*of\s*(?:Invoice|Issue|Supply)|Inv\.?\s*Date|Bill\s*Date|Dated?)\s*[:\s]*(.{8,30})', re.IGNORECASE),
    re.compile(r'(?:Document\s*Date|Txn\s*Date|Transaction\s*Date)\s*[:\s]*(.{8,30})', re.IGNORECASE),
]

DATE_FORMATS = [
    (r'\d{4}-\d{2}-\d{2}',          '%Y-%m-%d'),      # 2024-03-15
    (r'\d{2}/\d{2}/\d{4}',          '%d/%m/%Y'),      # 15/03/2024
    (r'\d{2}-\d{2}-\d{4}',          '%d-%m-%Y'),      # 15-03-2024
    (r'\d{2}\.\d{2}\.\d{4}',        '%d.%m.%Y'),      # 15.03.2024
    (r'\d{2}\s+[A-Za-z]{3,9}\s+\d{4}', '%d %B %Y'),  # 15 March 2024
    (r'\d{2}\s+[A-Za-z]{3}\s+\d{4}',   '%d %b %Y'),  # 15 Mar 2024
    (r'\d{2}-[A-Za-z]{3}-\d{4}',    '%d-%b-%Y'),      # 15-Mar-2024
    (r'\d{2}/[A-Za-z]{3}/\d{4}',    '%d/%b/%Y'),      # 15/Mar/2024
    (r'\d{2}-[A-Za-z]{3,9}-\d{4}',  '%d-%B-%Y'),      # 15-March-2024
    (r'\d{1,2}-[A-Za-z]{3}-\d{2}',  '%d-%b-%y'),      # 4-Feb-26 (D-Mon-YY)
    (r'\d{1,2}/\d{1,2}/\d{4}',      '%d/%m/%Y'),      # 2/1/2025 (D/M/YYYY)
    (r'\d{1,2}/\d{1,2}/\d{2}',      '%d/%m/%y'),      # 15/3/24 (D/M/YY)
    (r'\d{1,2}-\d{1,2}-\d{2}',      '%d-%m-%y'),      # 15-3-24 (D-M-YY)
]


def _extract_date(text: str) -> Optional[str]:
    """Try multiple date formats and return ISO date string."""
    if not text:
        return None
    for pattern_str, fmt in DATE_FORMATS:
        m = re.search(pattern_str, text)
        if m:
            try:
                raw = m.group()
                # Normalize month names to standard abbreviations
                month_map = {
                    'january': 'Jan', 'february': 'Feb', 'march': 'Mar',
                    'april': 'Apr', 'may': 'May', 'june': 'Jun',
                    'july': 'Jul', 'august': 'Aug', 'september': 'Sep',
                    'october': 'Oct', 'november': 'Nov', 'december': 'Dec',
                }
                raw_lower = raw.lower()
                for full_name, abbr in month_map.items():
                    if full_name in raw_lower:
                        raw = re.sub(full_name, abbr, raw, flags=re.IGNORECASE)
                        fmt_to_use = fmt.replace('%B', '%b')
                        break
                else:
                    fmt_to_use = fmt

                dt = datetime.strptime(raw.strip(), fmt_to_use)
                # Fix 2-digit year
                if dt.year < 100:
                    dt = dt.replace(year=dt.year + 2000)
                # Sanity: reject dates before 2000 or after 2030
                if 2000 <= dt.year <= 2030:
                    return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def _find_invoice_date(text: str) -> Optional[str]:
    """Find invoice date using keyword context first, then fallback."""
    # 1. Look near date keywords
    for pattern in DATE_KEYWORD_PATTERNS:
        m = pattern.search(text)
        if m:
            date = _extract_date(m.group(1))
            if date:
                return date

    # 2. Look in first 500 chars (invoice header area)
    date = _extract_date(text[:500])
    if date:
        return date

    # 3. Last resort — anywhere in text
    return _extract_date(text)


# ═══════════════════════════════════════════════════════════
# Amount Extraction — Indian Number Format
# ═══════════════════════════════════════════════════════════

def _parse_amount(s: str) -> float:
    """
    Parse Indian formatted amount. Handles:
    - ₹1,23,456.78 (lakhs system)
    - Rs. 11,998,855.80 (western commas)
    - 1234.50
    - (1,234.50) — negative in parentheses
    - 1234 (no decimals)
    """
    if not s or s.strip() in ('-', '--', '', 'nil', 'Nil', 'N/A', '—', '–'):
        return 0
    s = s.strip()
    # Handle negative in parentheses: (1,234.50)
    is_negative = s.startswith('(') and s.endswith(')')
    # Remove currency symbols, spaces, and keep only digits, dots, minus
    cleaned = re.sub(r'[₹$€£¥]|Rs\.?|INR|/-', '', s)
    cleaned = re.sub(r'[^\d.\-()]', '', cleaned.replace(",", ""))
    cleaned = cleaned.strip('()')
    try:
        val = round(float(cleaned), 2) if cleaned else 0
        return -val if is_negative else val
    except (ValueError, TypeError):
        return 0


# Amount keyword → field mapping (checked in order, first match wins per field)
AMOUNT_EXTRACTION_RULES = [
    # ── Total / Grand Total (highest priority for total_amount) ──
    ('total_amount', [
        re.compile(r'(?:Grand\s*Total|Total\s*(?:Invoice\s*)?Amount|Net\s*(?:Amount\s*)?Payable|Amount\s*Payable|Invoice\s*Total|Bill\s*Amount|Total\s*Due|Balance\s*Due|Amount\s*Due|Payable\s*Amount)\s*[:\s|]*[₹Rs.INR\s]*([\d,]+\.?\d*)', re.IGNORECASE),
        # Markdown table row: | Grand Total | ₹12,500.00 |
        re.compile(r'\|\s*(?:Grand\s*Total|Total\s*Amount|Net\s*Payable)\s*\|[^|]*?[₹Rs.\s]*([\d,]+\.?\d*)\s*\|?', re.IGNORECASE),
        # "Total ₹12,500.00" at end of line
        re.compile(r'^Total\s*[:\s]*[₹Rs.INR\s]*([\d,]+\.?\d*)\s*$', re.IGNORECASE | re.MULTILINE),
    ]),

    # ── Taxable Value / Subtotal ──
    ('amount', [
        re.compile(r'(?:Sub\s*[-\s]?Total|Taxable\s*(?:Value|Amount)|Amount\s*(?:Before|Excl\.?)\s*Tax|Base\s*Amount|Assessable\s*Value)\s*[:\s|]*[₹Rs.INR\s]*([\d,]+\.?\d*)', re.IGNORECASE),
        re.compile(r'\|\s*(?:Sub\s*Total|Taxable\s*Value|Taxable\s*Amount)\s*\|[^|]*?[₹Rs.\s]*([\d,]+\.?\d*)\s*\|?', re.IGNORECASE),
    ]),

    # ── CGST ──
    ('cgst_amount', [
        re.compile(r'CGST\s*(?:@\s*\d+\.?\d*\s*%?)?\s*[:\s|]*[₹Rs.\s]*([\d,]+\.?\d*)', re.IGNORECASE),
        re.compile(r'Central\s*(?:GST|Goods\s*(?:&|and)\s*Service\s*Tax)\s*[:\s|]*[₹Rs.\s]*([\d,]+\.?\d*)', re.IGNORECASE),
    ]),

    # ── SGST / UTGST ──
    ('sgst_amount', [
        re.compile(r'(?:SGST|UTGST)\s*(?:@\s*\d+\.?\d*\s*%?)?\s*[:\s|]*[₹Rs.\s]*([\d,]+\.?\d*)', re.IGNORECASE),
        re.compile(r'State\s*(?:GST|Goods\s*(?:&|and)\s*Service\s*Tax)\s*[:\s|]*[₹Rs.\s]*([\d,]+\.?\d*)', re.IGNORECASE),
    ]),

    # ── IGST ──
    ('igst_amount', [
        re.compile(r'IGST\s*(?:@\s*\d+\.?\d*\s*%?)?\s*[:\s|]*[₹Rs.\s]*([\d,]+\.?\d*)', re.IGNORECASE),
        re.compile(r'Integrated\s*(?:GST|Goods\s*(?:&|and)\s*Service\s*Tax)\s*[:\s|]*[₹Rs.\s]*([\d,]+\.?\d*)', re.IGNORECASE),
    ]),

    # ── Total GST / Total Tax ──
    ('gst_amount', [
        re.compile(r'(?:Total\s*(?:GST|Tax)|GST\s*Amount|Tax\s*Amount)\s*[:\s|]*[₹Rs.\s]*([\d,]+\.?\d*)', re.IGNORECASE),
    ]),

    # ── GST Rate (for reference) ──
    ('gst_rate', [
        re.compile(r'(?:GST|Tax)\s*(?:Rate)?[:\s]*@?\s*(\d+\.?\d*)\s*%', re.IGNORECASE),
        re.compile(r'(\d+\.?\d*)\s*%\s*(?:GST|Tax)', re.IGNORECASE),
    ]),

    # ── Discount ──
    ('discount', [
        re.compile(r'(?:Discount|Disc\.?|Less)\s*[:\s|]*[₹Rs.\s-]*([\d,]+\.?\d*)', re.IGNORECASE),
    ]),

    # ── Round Off ──
    ('round_off', [
        re.compile(r'(?:Round\s*Off|Rounding|Adj\.?)\s*[:\s|]*[₹Rs.\s-]*([\d,]+\.?\d*)', re.IGNORECASE),
    ]),

    # ── TCS (on e-commerce) ──
    ('tcs_amount', [
        re.compile(r'TCS\s*(?:@\s*[\d.]+%?)?\s*[:\s|]*[₹Rs.\s]*([\d,]+\.?\d*)', re.IGNORECASE),
    ]),

    # ── Amount in Words (for cross-validation) ──
    ('amount_in_words', [
        re.compile(r'(?:Amount\s*in\s*Words?|Rupees?|In\s*Words?)\s*[:\s]*(.+?)(?:\n|Only|$)', re.IGNORECASE),
    ]),
]


def _extract_amounts(text: str) -> Dict[str, Any]:
    """Extract all amount fields from text."""
    amounts = {}
    for field, patterns in AMOUNT_EXTRACTION_RULES:
        for pattern in patterns:
            m = pattern.search(text)
            if m:
                if field == 'amount_in_words':
                    amounts[field] = m.group(1).strip()
                elif field == 'gst_rate':
                    amounts[field] = float(m.group(1))
                else:
                    val = _parse_amount(m.group(1))
                    if val > 0:
                        amounts[field] = val
                break  # first match per field wins

    # ── Parse tax summary table ──
    # Handles: | Tax Rate | Taxable Amt. | CGST Amt. | SGST Amt. | Total Tax |
    #          | 18%      | 40,500.00    | 3,645.00  | 3,645.00  | 7,290.00  |
    # Also:    | Tax Rate | Taxable Amt. | IGST Amt. | Total Tax |
    _parse_tax_summary_table(text, amounts)

    # ── Parse Grand Total / Add : CGST/SGST/IGST from main table rows ──
    _parse_tax_rows_from_table(text, amounts)

    return amounts


def _parse_tax_summary_table(text: str, amounts: Dict[str, Any]) -> None:
    """Parse structured tax summary table for CGST/SGST/IGST/taxable amounts."""
    tables = _find_all_tables(text)
    for headers, rows in tables:
        headers_lower = [h.lower().strip() for h in headers]
        # Detect tax summary table by header keywords
        has_tax_rate = any('tax' in h and 'rate' in h for h in headers_lower)
        has_taxable = any('taxable' in h for h in headers_lower)
        if not (has_tax_rate or has_taxable):
            continue

        # Map columns
        col_indices = {}
        for i, h in enumerate(headers_lower):
            if 'taxable' in h:
                col_indices['taxable'] = i
            elif 'cgst' in h:
                col_indices['cgst'] = i
            elif 'sgst' in h or 'utgst' in h:
                col_indices['sgst'] = i
            elif 'igst' in h:
                col_indices['igst'] = i
            elif 'total' in h and 'tax' in h:
                col_indices['total_tax'] = i
            elif 'rate' in h or '%' in h:
                col_indices['rate'] = i

        # Sum across all rate rows (some invoices have multiple rates)
        for row in rows:
            if 'taxable' in col_indices and col_indices['taxable'] < len(row):
                val = _parse_amount(row[col_indices['taxable']])
                if val > 0:
                    amounts['amount'] = amounts.get('amount', 0) + val if 'amount' in amounts and len(rows) > 1 else val
            if 'cgst' in col_indices and col_indices['cgst'] < len(row):
                val = _parse_amount(row[col_indices['cgst']])
                if val > 0:
                    amounts['cgst_amount'] = amounts.get('cgst_amount', 0) + val if 'cgst_amount' in amounts else val
            if 'sgst' in col_indices and col_indices['sgst'] < len(row):
                val = _parse_amount(row[col_indices['sgst']])
                if val > 0:
                    amounts['sgst_amount'] = amounts.get('sgst_amount', 0) + val if 'sgst_amount' in amounts else val
            if 'igst' in col_indices and col_indices['igst'] < len(row):
                val = _parse_amount(row[col_indices['igst']])
                if val > 0:
                    amounts['igst_amount'] = amounts.get('igst_amount', 0) + val if 'igst_amount' in amounts else val
            if 'total_tax' in col_indices and col_indices['total_tax'] < len(row):
                val = _parse_amount(row[col_indices['total_tax']])
                if val > 0:
                    amounts['gst_amount'] = amounts.get('gst_amount', 0) + val if 'gst_amount' in amounts else val
            if 'rate' in col_indices and col_indices['rate'] < len(row):
                rate_str = row[col_indices['rate']].strip().rstrip('%').strip()
                try:
                    amounts['gst_rate'] = float(rate_str)
                except (ValueError, TypeError):
                    pass


def _parse_tax_rows_from_table(text: str, amounts: Dict[str, Any]) -> None:
    """Parse 'Add : CGST', 'Add : SGST/IGST', 'Grand Total' rows from main item table.
    Also handles AKP-style tables where tax labels appear in middle columns."""
    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('|'):
            continue
        cols = [c.strip() for c in stripped.split('|') if c.strip()]
        if not cols:
            continue

        # Join all columns for keyword scanning (handles keywords in any column)
        all_cols_lower = ' '.join(c.lower() for c in cols)
        first_col = cols[0].lower().strip()

        # "Grand Total" / "Total with tax" row — last non-empty column is the total
        if 'grand total' in first_col or 'total with tax' in first_col:
            for col in reversed(cols):
                val = _parse_amount(col)
                if val > 0:
                    if 'total_amount' not in amounts:
                        amounts['total_amount'] = val
                    break

        # "Add : CGST" or "OUTPUT CGST" row OR CGST@9% / CGST @ 9% in any column
        elif ('cgst' in first_col and ('add' in first_col or 'output' in first_col)) or \
             ('cgst' in all_cols_lower and 'cgst_amount' not in amounts):
            # Find a real amount (not just the percentage or label)
            for col in reversed(cols):
                col_clean = re.sub(r'\\\*\\\*|\*\*', '', col).strip()
                col_lower = col_clean.lower()
                # Skip label columns (CGST@9%, R/off, etc.) and percentages
                if any(kw in col_lower for kw in ['cgst', 'sgst', 'igst', 'gst', 'r/off', 'round']):
                    continue
                if re.match(r'^[\d.]+\s*%$', col_clean):
                    continue  # skip pure percentage values
                val = _parse_amount(col_clean)
                if val > 0:
                    amounts['cgst_amount'] = val
                    break

        # "Add : SGST" or "OUTPUT SGST" row OR SGST@9% / SGST @ 9% in any column
        elif (('sgst' in first_col or 'utgst' in first_col) and ('add' in first_col or 'output' in first_col)) or \
             (('sgst' in all_cols_lower or 'utgst' in all_cols_lower) and 'sgst_amount' not in amounts):
            for col in reversed(cols):
                col_clean = re.sub(r'\\\*\\\*|\*\*', '', col).strip()
                col_lower = col_clean.lower()
                if any(kw in col_lower for kw in ['cgst', 'sgst', 'igst', 'gst', 'utgst', 'r/off', 'round']):
                    continue
                if re.match(r'^[\d.]+\s*%$', col_clean):
                    continue
                val = _parse_amount(col_clean)
                if val > 0:
                    amounts['sgst_amount'] = val
                    break

        # "Add : IGST" row OR IGST@18% / IGST @ 18% in any column
        elif ('igst' in first_col and ('add' in first_col or 'output' in first_col)) or \
             ('igst' in all_cols_lower and 'igst_amount' not in amounts):
            for col in reversed(cols):
                col_clean = re.sub(r'\\\*\\\*|\*\*', '', col).strip()
                col_lower = col_clean.lower()
                if any(kw in col_lower for kw in ['cgst', 'sgst', 'igst', 'gst', 'r/off', 'round']):
                    continue
                if re.match(r'^[\d.]+\s*%$', col_clean):
                    continue
                val = _parse_amount(col_clean)
                if val > 0:
                    amounts['igst_amount'] = val
                    break

        # "Total Amount After Tax" row — alias for Grand Total
        elif 'total amount after tax' in all_cols_lower:
            for col in reversed(cols):
                val = _parse_amount(col)
                if val > 0:
                    if 'total_amount' not in amounts:
                        amounts['total_amount'] = val
                    break

        # "Total Amount Before Tax" / "Sub Total" row — taxable amount
        elif 'total amount before tax' in all_cols_lower or 'sub total' in first_col:
            for col in reversed(cols):
                val = _parse_amount(col)
                if val > 0:
                    if 'amount' not in amounts:
                        amounts['amount'] = val
                    break


# ═══════════════════════════════════════════════════════════
# Vendor Name Extraction
# ═══════════════════════════════════════════════════════════

# Indian company suffixes for validation
COMPANY_SUFFIXES = re.compile(
    r'(?:Pvt\.?\s*Ltd\.?|Private\s*Limited|Limited|Ltd\.?|LLP|'
    r'Enterprises?|Industries|Solutions|Services|Traders?|'
    r'Associates|Consultants?|Corporation|Corp\.?|'
    r'Agency|Agencies|Logistics|Technologies|Tech|'
    r'Infra|Infrastructure|Builders|Developers|'
    r'Pharma|Pharmaceuticals|Distributors?|Dealers?|'
    r'Manufacturers?|International|India|'
    r'Co\.?\s*(?:Pvt\.?)?|& Co\.?|Group|Retail)\b',
    re.IGNORECASE
)


def _extract_vendor_name(text: str) -> str:
    """Extract vendor/seller name from invoice text. Multiple strategies."""

    # Find the buyer section boundary so we can skip names in it
    buyer_section_start = _find_buyer_section_start(text)

    # Strategy 1: Explicit "Sold by" / "Seller" / "Billed by" labels
    labeled_patterns = [
        re.compile(r'(?:Sold\s*by|Seller\s*(?:Name)?|Supplier|Billed\s*by|Issued\s*by|Service\s*Provider)\s*[:\s]+(.+?)(?:\n|GSTIN|GST\s*No|Address|Ph|Tel|Email|Mob|PIN|CIN)', re.IGNORECASE),
    ]
    for pattern in labeled_patterns:
        m = pattern.search(text)
        if m:
            name = _clean_vendor_name(m.group(1))
            if _is_valid_vendor_name(name):
                return name

    # Strategy 1b: "For VENDOR_NAME" in signature area (e.g., "For HKNC & COMPANY", "For D.R. ELECTRICALS")
    # Strip ** markers first, handle parenthetical suffixes
    for_matches = re.findall(r'(?:^|\n)\s*\*{0,2}\s*[Ff]or\s+\*{0,2}\s*([A-Z][A-Za-z\s&.,\-/]+?)(?:\(.*?\))?\s*\*{0,2}\s*$', text, re.MULTILINE)
    if for_matches:
        # Filter: skip sentences, keep short company names
        for_vendor_fallback = None
        for candidate in reversed(for_matches):
            name = _clean_vendor_name(candidate)
            # Skip sentences (too long, starts with common lowercase words)
            if len(name) > 60:
                continue
            if name.lower().startswith(('certified', 'the ', 'we ', 'all ', 'this ')):
                continue
            if _is_valid_vendor_name(name) and not _is_header_label(name):
                for_vendor_fallback = name
                break
    else:
        for_vendor_fallback = None

    search_area = text[:buyer_section_start] if buyer_section_start else text[:800]

    # Strategy 2: Markdown heading (# VENDOR NAME) BEFORE buyer section
    # This is critical for LlamaParse output like: # HKNC & COMPANY, Chartered Accountants
    heading_matches = re.findall(r'^#+\s+(.+?)\s*$', search_area, re.MULTILINE)
    for heading in heading_matches:
        # Strip HTML tags like <u>
        cleaned = re.sub(r'<[^>]+>', '', heading).strip()
        name = _clean_vendor_name(cleaned)
        if _is_valid_vendor_name(name) and not _is_header_label(name):
            return name

    # Strategy 3: First bold text in markdown BEFORE buyer section
    bold_matches = re.findall(r'\*\*(.+?)\*\*', search_area)
    for bold in bold_matches:
        name = _clean_vendor_name(bold)
        if _is_valid_vendor_name(name) and not _is_header_label(name):
            return name

    # Strategy 4: Company name with known suffix BEFORE buyer section
    suffix_match = re.search(
        r'([A-Z][A-Za-z\s&.\-]{2,60}(?:' + COMPANY_SUFFIXES.pattern + r'))',
        search_area, re.IGNORECASE
    )
    if suffix_match:
        name = _clean_vendor_name(suffix_match.group(1))
        if _is_valid_vendor_name(name):
            return name

    # Strategy 5: M/s pattern BEFORE buyer section only
    ms_match = re.search(r'M/s\.?\s+(.+?)(?:\n|,|\(|GSTIN|GST)', search_area, re.IGNORECASE)
    if ms_match:
        name = _clean_vendor_name(ms_match.group(1))
        if _is_valid_vendor_name(name):
            return name

    # Strategy 6: First prominent line (all-caps or Title Case, not a label)
    for line in search_area.split('\n')[:20]:
        line = line.strip().replace('**', '').replace('#', '').strip()
        if not line or len(line) < 4 or len(line) > 100:
            continue
        if _is_header_label(line):
            continue
        if (line.isupper() and len(line) > 5) or (line.istitle() and len(line) > 8):
            if not any(c in line for c in ['|', '---', 'http', '@']):
                return _clean_vendor_name(line)

    # Strategy 7: Text right before first GSTIN
    gstin_match = GSTIN_RE.search(text)
    if gstin_match:
        before_gstin = text[max(0, gstin_match.start()-200):gstin_match.start()]
        lines = [l.strip().replace('**', '') for l in before_gstin.split('\n') if l.strip()]
        for line in reversed(lines):
            if _is_valid_vendor_name(line) and not _is_header_label(line):
                return _clean_vendor_name(line)

    # Strategy 8: Fall back to "For VENDOR" from signature area
    if for_vendor_fallback:
        return for_vendor_fallback

    return "Unknown Vendor"


def _find_buyer_section_start(text: str) -> int:
    """Find where the buyer/recipient section starts in the invoice."""
    buyer_keywords = [
        'bill to', 'billed to', 'buyer', 'customer', 'ship to',
        'shipped to', 'sold to', 'recipient', 'consignee', 'details of receiver',
    ]
    text_lower = text.lower()
    earliest = len(text)
    for kw in buyer_keywords:
        pos = text_lower.find(kw)
        if pos != -1 and pos < earliest:
            earliest = pos
    return earliest if earliest < len(text) else 0


def _clean_vendor_name(name: str) -> str:
    """Clean up extracted vendor name."""
    name = name.strip()
    # Remove markdown bold markers
    name = name.replace('**', '')
    name = name.rstrip(',').rstrip(':').strip()
    name = re.sub(r'\s+', ' ', name)  # collapse whitespace
    # Remove trailing GSTIN or address bits (word boundaries to avoid matching inside words like "COMPANY")
    name = re.sub(r'\s*\b(?:GSTIN|GST\s*No|CIN|PAN\b|TAN\b|Address|Phone|Tel\b|Mob\b|PIN\s*:).*$', '', name, flags=re.IGNORECASE)
    # Remove leading serial numbers "1. " or "A. "
    name = re.sub(r'^\d+\.\s*', '', name)
    return name.strip()


def _is_valid_vendor_name(name: str) -> bool:
    """Check if extracted text looks like a valid vendor name."""
    if not name or len(name) < 3 or len(name) > 120:
        return False
    # Not just numbers
    if re.match(r'^[\d\s.,/-]+$', name):
        return False
    # Not a date
    if re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$', name):
        return False
    # Not a table separator line
    if re.match(r'^[-|\s]+$', name):
        return False
    # Not a single generic word ("State", "Name", etc.)
    if name.lower().strip() in ('state', 'name', 'address', 'place', 'date', 'total'):
        return False
    return True


def _is_header_label(text: str) -> bool:
    """Check if text is a document label, not a company name."""
    labels = [
        'tax invoice', 'invoice', 'bill of supply', 'credit note', 'debit note',
        'proforma', 'quotation', 'estimate', 'delivery challan', 'purchase order',
        'receipt', 'gstin', 'gst number', 'pan', 'cin', 'tan', 'date', 'address',
        'phone', 'email', 'mobile', 'fax', 'website', 'subject', 'dear sir',
        'to whom', 'bill to', 'ship to', 'sold to', 'page', 'original', 'duplicate',
        'triplicate', 'copy', 'e-invoice', 'irn', 'ack no', 'place of supply',
        'reverse charge', 'invoice no', 'dated', 'gr/rr', 'transport', 'vehicle',
        'station', 'billed to', 'shipped to',
        'state', 'mob', 'e-mail', 'e- mail', 'gst in', 'pan no',
        'buyer', 'consignee', 'dispatched', 'destination', 'shipping',
        'declaration', 'delivery note', 'reference no', 'buyer\'s order',
        'bill of lading', 'terms of delivery', 'motor vehicle',
        'g.r.', 'g.r ', 'vehicle no', 'transport name', 'place &',
        'total package', 'wt.', 'sr. no',
    ]
    text_lower = text.lower().strip()
    return any(text_lower.startswith(lbl) or text_lower == lbl for lbl in labels)


# ═══════════════════════════════════════════════════════════
# HSN/SAC Code Extraction
# ═══════════════════════════════════════════════════════════

def _extract_hsn_sac_codes(text: str) -> List[str]:
    """Extract all HSN/SAC codes from text."""
    codes = set()

    # HSN/SAC in labeled context
    labeled = re.findall(r'(?:HSN|SAC|HSN/SAC|Service\s*Code)\s*[:\s]*(\d{4,8})', text, re.IGNORECASE)
    codes.update(labeled)

    # HSN/SAC in table columns (4-8 digit numbers in a column that's likely HSN)
    # Look for numbers in pipe-delimited tables that are 4-8 digits
    for line in text.split('\n'):
        if '|' in line:
            cols = [c.strip() for c in line.split('|') if c.strip()]
            for col in cols:
                if re.match(r'^\d{4,8}$', col.strip()):
                    codes.add(col.strip())

    return list(codes)


# ═══════════════════════════════════════════════════════════
# Place of Supply Extraction
# ═══════════════════════════════════════════════════════════

def _extract_place_of_supply(text: str, seller_gstin: str = None, buyer_gstin: str = None) -> Optional[str]:
    """Extract Place of Supply from text or derive from GSTINs."""

    # Strip markdown bold markers for pattern matching
    clean_text = text.replace('**', '')

    # 1. Explicit label
    pos_patterns = [
        re.compile(r'Place\s*of\s*Supply\s*[:\s]*([A-Za-z\s]+?)(?:\(|\d|,|$|\n|\|)', re.IGNORECASE),
        re.compile(r'Place\s*of\s*Supply\s*[:\s]*\(?(\d{2})\)?\s*[-–]?\s*([A-Za-z\s]+)', re.IGNORECASE),
        re.compile(r'State\s*(?:Name|Code)?\s*[:\s]*([A-Za-z\s]+?)(?:\(|\d|,|$|\n)', re.IGNORECASE),
    ]
    for pattern in pos_patterns:
        m = pattern.search(clean_text)
        if m:
            # If we matched state code, look up name
            if m.lastindex >= 2:
                state_name = m.group(2).strip()
            else:
                state_name = m.group(1).strip()
            if state_name and len(state_name) > 2:
                return state_name

    # 2. Derive from buyer GSTIN state code
    if buyer_gstin:
        state = STATE_CODES.get(buyer_gstin[:2])
        if state:
            return state

    # 3. Derive from seller GSTIN state code
    if seller_gstin:
        state = STATE_CODES.get(seller_gstin[:2])
        if state:
            return state

    return None


# ═══════════════════════════════════════════════════════════
# Line Item Extraction from Markdown Tables
# ═══════════════════════════════════════════════════════════

# Keywords that identify a line-item table header
LINE_ITEM_HEADER_KEYWORDS = [
    'description', 'particular', 'item', 'product', 'service',
    'goods', 'material', 'name', 'details', 'fuel',
]

LINE_ITEM_AMOUNT_KEYWORDS = [
    'amount', 'total', 'value', 'price', 'rate', 'qty',
    'quantity', 'unit', 'hsn', 'sac', 'taxable',
    'charge', 'fee', 'cost', 'sl', 'sr', 'no',
]

# Known "total" row labels to skip (matched at START of description)
TOTAL_ROW_START_KEYWORDS = [
    'total', 'grand total', 'sub total', 'subtotal', 'net amount',
    'total with tax', 'total amount',
    'round off', 'rounding', 'discount', 'less:',
    'balance', 'payable', 'tcs ', 'cess ',
    'add :', 'add:', 'add :',  # "Add : CGST", "Add : IGST" rows
    'output cgst', 'output sgst', 'output igst',  # "OUTPUT CGST 9%" rows
    'rupees ',  # "Rupees One Lakh..." amount-in-words in wrong column
    'consignee', 'buyer (', 'buyer(', 'dispatched', 'dispatch doc',
    'bill of lading', 'terms of delivery', 'motor vehicle',
    'delivery note', 'reference no', "buyer's order",
]
# These skip a row only if the ENTIRE description matches
TOTAL_ROW_EXACT_KEYWORDS = [
    'cgst', 'sgst', 'igst', 'gst', 'tax', 'vat',
]


def _extract_line_items(text: str) -> List[Dict[str, Any]]:
    """Extract line items from all markdown tables in the document."""
    items = []
    tables = _find_all_tables(text)

    for headers, rows in tables:
        # Check if this table looks like a line-item table
        headers_lower = [h.lower() for h in headers]
        has_item_col = any(any(kw in h for kw in LINE_ITEM_HEADER_KEYWORDS) for h in headers_lower)
        has_amount_col = any(any(kw in h for kw in LINE_ITEM_AMOUNT_KEYWORDS) for h in headers_lower)

        if not (has_item_col or has_amount_col):
            continue  # Not a line-item table

        # Map columns
        col_map = _map_line_item_columns(headers_lower)

        for row in rows:
            item = _parse_line_item_row(row, col_map, headers_lower)
            if item:
                items.append(item)

    # If no tables found, try key-value pair extraction
    if not items:
        items = _extract_line_items_freeform(text)

    return items


def _find_all_tables(text: str) -> List[Tuple[List[str], List[List[str]]]]:
    """Find all markdown tables and return (headers, rows) for each."""
    tables = []
    current_header = None
    current_rows = []
    saw_separator = False

    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('|'):
            if current_header and current_rows:
                tables.append((current_header, current_rows))
            current_header = None
            current_rows = []
            saw_separator = False
            continue

        cols = [c.strip() for c in stripped.split('|')]
        cols = [c for c in cols if c]  # remove empty from leading/trailing pipes

        if not cols:
            continue

        # Separator row (|---|---|)
        if all(re.match(r'^[-:]+$', c) for c in cols):
            saw_separator = True
            continue

        if not saw_separator:
            # This is a header row
            current_header = cols
        else:
            # This is a data row
            current_rows.append(cols)

    # Don't forget the last table
    if current_header and current_rows:
        tables.append((current_header, current_rows))

    return tables


def _map_line_item_columns(headers: List[str]) -> Dict[str, int]:
    """Map header names to their roles for line-item extraction."""
    col_map = {}
    amount_indices = []  # Track all amount columns to handle duplicates
    for i, h in enumerate(headers):
        if any(k in h for k in ['sr', 'sl', 's.no', '#', 'no.']) and 'invoice' not in h:
            col_map['serial'] = i
        elif any(k in h for k in ['desc', 'particular', 'item', 'product', 'service', 'goods', 'material', 'name', 'detail', 'fuel', 'type']):
            col_map['description'] = i
        elif any(k in h for k in ['hsn', 'sac']):
            col_map['hsn_sac'] = i
        elif any(k in h for k in ['qty', 'quantity', 'nos', 'unit']) and 'price' not in h:
            col_map['quantity'] = i
        elif any(k in h for k in ['rate', 'price', 'mrp']) and 'disc' not in h:
            col_map['unit_price'] = i
        elif any(k in h for k in ['uom', 'unit of']):
            col_map['uom'] = i
        elif any(k in h for k in ['disc', 'rebate']):
            col_map['discount'] = i
        elif any(k in h for k in ['gst', 'tax']) and '%' in h:
            col_map['gst_pct'] = i
        elif any(k in h for k in ['cgst']):
            col_map['cgst'] = i
        elif any(k in h for k in ['sgst', 'utgst']):
            col_map['sgst'] = i
        elif any(k in h for k in ['igst']):
            col_map['igst'] = i
        elif any(k in h for k in ['taxable', 'assessable']):
            col_map['taxable_value'] = i
        elif any(k in h for k in ['amount', 'total', 'value', 'net']):
            amount_indices.append(i)

    # For duplicate "Amount" columns (common in Indian invoices with 2 Amount columns),
    # use the FIRST one as it typically contains line-item amounts.
    # The second is often used for subtotals or tax rows.
    if amount_indices:
        col_map['amount'] = amount_indices[0]

    return col_map


def _parse_line_item_row(cols: List[str], col_map: Dict[str, int], headers: List[str]) -> Optional[Dict]:
    """Parse a single table row into a line item dict."""
    item = {
        "description": "",
        "hsn_sac": "",
        "quantity": "1",
        "unit_price": None,
        "amount": None,
        "gst_rate": None,
        "cgst": None,
        "sgst": None,
        "igst": None,
        "discount": None,
    }

    if col_map:
        for field, idx in col_map.items():
            if idx >= len(cols):
                continue
            val = cols[idx].strip()
            if not val or val in ('-', '--', '—'):
                continue

            if field == 'serial':
                continue  # skip serial number
            elif field == 'description':
                # Clean HTML tags from LlamaParse output (e.g., <br/> line breaks in cells)
                cleaned = re.sub(r'<br\s*/?>', ' | ', val)   # <br/> → readable separator
                cleaned = re.sub(r'<[^>]+>', '', cleaned)        # strip any remaining HTML
                # Clean escaped markdown bold markers (\*\*text\*\*)
                cleaned = re.sub(r'\\\*\\\*', '', cleaned)
                cleaned = cleaned.replace('**', '')
                item['description'] = cleaned.strip()
            elif field == 'hsn_sac':
                item['hsn_sac'] = val
            elif field == 'quantity':
                # Clean escaped markdown bold and extract numeric part
                qty_clean = re.sub(r'\\\*\\\*|\*\*', '', val).strip()
                # Extract just the number from "300 PCS", "6,500 PCS", "75.00 Metre"
                qty_match = re.match(r'^([\d,]+\.?\d*)\s*', qty_clean)
                if qty_match:
                    item['quantity'] = qty_match.group(1).replace(',', '')
                else:
                    item['quantity'] = qty_clean
            elif field == 'unit_price':
                item['unit_price'] = _parse_amount(val)
            elif field == 'uom':
                pass  # store if needed later
            elif field == 'discount':
                item['discount'] = _parse_amount(val)
            elif field == 'gst_pct':
                item['gst_rate'] = _parse_amount(val)
            elif field == 'cgst':
                item['cgst'] = _parse_amount(val)
            elif field == 'sgst':
                item['sgst'] = _parse_amount(val)
            elif field == 'igst':
                item['igst'] = _parse_amount(val)
            elif field in ('amount', 'taxable_value'):
                item['amount'] = _parse_amount(val)
    else:
        # Positional fallback for tables without proper headers
        if len(cols) >= 5:
            # Serial | Description | HSN | Qty | Rate | Amount
            start = 0
            if re.match(r'^\d+\.?$', cols[0].strip()):
                start = 1  # skip serial number
            item['description'] = cols[start]
            # Check if next col is HSN (4-8 digit number)
            next_col = cols[start + 1] if start + 1 < len(cols) else ""
            if re.match(r'^\d{4,8}$', next_col.strip()):
                item['hsn_sac'] = next_col.strip()
            item['unit_price'] = _parse_amount(cols[-2])
            item['amount'] = _parse_amount(cols[-1])
        elif len(cols) >= 3:
            item['description'] = cols[0]
            item['amount'] = _parse_amount(cols[-1])
        elif len(cols) >= 2:
            item['description'] = cols[0]
            item['amount'] = _parse_amount(cols[-1])

    # ── Validation ──
    desc = item['description'].strip()
    if not desc or len(desc) < 2:
        return None
    # Skip if description is just a number (serial) or formatted amount
    if re.match(r'^[\d,]+\.?\d*$', desc):
        return None
    # Skip if description looks like a percentage "@ 18.00 %" or just "9 %"
    if re.match(r'^@?\s*[\d.]+\s*%?$', desc):
        return None
    # Skip if description is just a quantity label like "6,900 PCS" or "300 PCS"
    if re.match(r'^[\d,]+\s*(?:PCS|NOS|KGS?|LTRS?|MTR|ROLLS?|SETS?|BOX|DOZEN|PKT|PC)$', desc, re.IGNORECASE):
        return None
    # Skip total/summary rows
    desc_lower = desc.lower()
    if any(desc_lower.startswith(kw) for kw in TOTAL_ROW_START_KEYWORDS):
        return None
    if desc_lower.strip() in TOTAL_ROW_EXACT_KEYWORDS:
        return None

    return item


def _extract_line_items_freeform(text: str) -> List[Dict]:
    """Fallback: extract items from non-table invoice formats."""
    items = []
    # Pattern: "1. Item description — ₹1,234.00"
    line_item_re = re.compile(
        r'^\s*\d+[.)]\s+(.+?)\s*[-–—:]\s*[₹Rs.INR\s]*([\d,]+\.?\d*)',
        re.MULTILINE
    )
    for m in line_item_re.finditer(text):
        desc = m.group(1).strip()
        amount = _parse_amount(m.group(2))
        if desc and amount > 0:
            items.append({
                "description": desc,
                "hsn_sac": "",
                "quantity": "1",
                "unit_price": amount,
                "amount": amount,
            })
    return items


# ═══════════════════════════════════════════════════════════
# Invoice Type & Document Classification
# ═══════════════════════════════════════════════════════════

def _detect_document_type(text: str) -> str:
    """Detect the type of invoice document."""
    text_lower = text[:2000].lower()
    if 'credit note' in text_lower or 'cr. note' in text_lower:
        return "Credit Note"
    elif 'debit note' in text_lower or 'dr. note' in text_lower:
        return "Debit Note"
    elif 'bill of supply' in text_lower:
        return "Bill of Supply"
    elif 'proforma' in text_lower:
        return "Proforma Invoice"
    elif 'delivery challan' in text_lower:
        return "Delivery Challan"
    elif 'e-invoice' in text_lower or 'irn' in text_lower:
        return "E-Invoice"
    elif 'purchase order' in text_lower:
        return "Purchase Order"
    elif 'quotation' in text_lower or 'estimate' in text_lower:
        return "Quotation"
    elif 'receipt' in text_lower and 'rent' in text_lower:
        return "Rent Receipt"
    elif 'tax invoice' in text_lower:
        return "Tax Invoice"
    return "Invoice"


def _detect_rcm(text: str) -> bool:
    """Detect if Reverse Charge Mechanism applies.
    Checks for explicit 'Reverse Charge: Y/Yes' — returns False for 'N/No'."""
    # Check explicit Y/N first
    explicit = re.search(r'Reverse\s*Charge\s*[:\s]*([YyNn]|Yes|No)\b', text, re.IGNORECASE)
    if explicit:
        val = explicit.group(1).strip().upper()
        return val in ('Y', 'YES')
    # If no explicit Y/N, check for presence of RCM keywords
    return bool(re.search(r'(?:RCM|under\s*reverse\s*charge)', text, re.IGNORECASE))


def _extract_irn(text: str) -> Optional[str]:
    """Extract E-Invoice IRN number (64-char hex)."""
    m = re.search(r'(?:IRN|Invoice\s*Reference)\s*[:\s]*([A-Fa-f0-9]{64})', text, re.IGNORECASE)
    return m.group(1) if m else None


# ═══════════════════════════════════════════════════════════
# Expense Type Classification — Comprehensive Indian Context
# ═══════════════════════════════════════════════════════════

EXPENSE_KEYWORDS = {
    # Direct expenses → Purchase/Sales
    'Purchase': ['purchase', 'bought', 'procurement', 'buying', 'raw material', 'stock', 'inventory',
                 'goods purchased', 'material purchased', 'traded goods'],
    'Sales': ['sales', 'sold', 'selling', 'revenue', 'goods sold'],

    # Office & Admin
    'Rent': ['rent', 'lease', 'tenancy', 'rental', 'office space', 'godown', 'warehouse rent'],
    'Salary': ['salary', 'wages', 'payroll', 'compensation', 'stipend', 'honorarium'],
    'Office Expenses': ['stationery', 'printing', 'cartridge', 'toner', 'pen', 'paper', 'office supply',
                        'pantry', 'courier', 'postage', 'stamp'],

    # Utilities & Communication
    'Electricity': ['electricity', 'electric', 'power', 'bescom', 'bses', 'tata power', 'adani',
                    'msedcl', 'torrent', 'cesc', 'wbsedcl'],
    'Telephone & Internet': ['airtel', 'jio', 'vodafone', 'idea', 'bsnl', 'mtnl', 'act fibernet',
                             'broadband', 'internet', 'wifi', 'telephone', 'mobile', 'sim', 'recharge',
                             'tata play', 'dish tv'],
    'Water Charges': ['water', 'bwssb', 'mcgm', 'dda water'],

    # Professional Services
    'Professional Fees': ['professional fee', 'consulting', 'advisory', 'consultancy', 'retainer',
                          'ca fee', 'audit fee', 'cs fee', 'legal fee', 'advocate', 'lawyer',
                          'architect', 'valuer', 'chartered accountant', 'company secretary'],
    'Software & IT': ['software', 'saas', 'subscription', 'license', 'domain', 'hosting',
                      'cloud', 'aws', 'azure', 'google cloud', 'zoho', 'tally',
                      'microsoft', 'adobe', 'slack', 'github', 'notion'],

    # Marketing
    'Advertising': ['advertising', 'marketing', 'promotion', 'ad campaign', 'google ads',
                    'facebook ads', 'billboard', 'hoarding', 'pamphlet', 'brochure',
                    'meta ads', 'instagram', 'linkedin ads'],

    # Travel & Conveyance
    'Travel': ['travel', 'tour', 'flight', 'air ticket', 'train ticket', 'irctc',
               'makemytrip', 'goibibo', 'cleartrip', 'yatra'],
    'Hotel & Accommodation': ['hotel', 'lodge', 'lodging', 'resort', 'tariff', 'room rent', 'room charge',
                               'stay', 'night', 'check-in', 'guest house', 'accommodation',
                               'oyo', 'treebo', 'fab hotels', 'taj', 'itc', 'marriott',
                               'oberoi', 'laundry', 'room service', 'sea view', 'deluxe room',
                               'suite', 'restaurant charge'],
    'Conveyance': ['cab', 'uber', 'ola', 'rapido', 'auto', 'taxi', 'parking',
                   'toll', 'fastag', 'metro card'],
    'Fuel': ['petrol', 'diesel', 'fuel', 'cng', 'petroleum', 'indian oil', 'iocl',
             'hp', 'hindustan petroleum', 'bpcl', 'bharat petroleum', 'shell',
             'reliance petrol', 'nayara'],

    # Insurance
    'Insurance': ['insurance', 'policy', 'premium', 'lic', 'mediclaim', 'health insurance',
                  'fire insurance', 'vehicle insurance', 'motor insurance', 'keyman'],

    # Maintenance & Repair
    'Repair & Maintenance': ['maintenance', 'repair', 'amc', 'annual maintenance',
                              'service charge', 'upkeep', 'plumber', 'electrician',
                              'carpenter', 'painter', 'pest control', 'housekeeping'],

    # Food & Beverages
    'Food & Beverages': ['restaurant', 'food', 'catering', 'swiggy', 'zomato', 'dunzo',
                          'canteen', 'meals', 'tiffin', 'tea', 'coffee', 'beverage'],

    # Bank & Finance
    'Bank Charges': ['bank charge', 'transaction fee', 'processing fee', 'locker rent',
                     'cheque book', 'dd charge', 'wire transfer', 'swift', 'forex'],

    # Government & Compliance
    'Government Fees': ['challan', 'roc', 'mca', 'stamp duty', 'registration',
                        'court fee', 'municipal', 'corporation', 'panchayat',
                        'trade license', 'labor license', 'factory license'],

    # Medical
    'Medical': ['hospital', 'clinic', 'medical', 'doctor', 'pharmacy', 'medicine',
                'diagnostic', 'lab test', 'pathology', 'physiotherapy', 'dental'],

    # E-commerce
    'E-commerce Purchase': ['amazon', 'flipkart', 'myntra', 'meesho', 'snapdeal',
                            'nykaa', 'ajio', 'bigbasket', 'grofers', 'blinkit',
                            'jiomart', 'dmart'],

    # Education & Training
    'Training & Education': ['training', 'seminar', 'conference', 'workshop', 'course',
                              'certification', 'coaching', 'tuition', 'udemy', 'coursera'],

    # Assets
    'Furniture & Fixtures': ['furniture', 'chair', 'table', 'desk', 'almirah', 'rack',
                              'godrej', 'featherlite', 'nilkamal'],
    'Computer & Electronics': ['computer', 'laptop', 'printer', 'scanner', 'monitor',
                                'keyboard', 'mouse', 'ups', 'projector', 'tv', 'ac',
                                'dell', 'hp', 'lenovo', 'apple', 'macbook', 'asus', 'acer'],
    'Machinery': ['machine', 'equipment', 'plant', 'tool', 'generator', 'compressor'],
}


def _classify_expense(text: str, voucher_type: str = "") -> str:
    """Classify expense type from invoice text using weighted keyword scoring."""
    if voucher_type and voucher_type != "Other":
        return voucher_type

    text_lower = text.lower()
    scores = {}
    for category, keywords in EXPENSE_KEYWORDS.items():
        score = 0
        for kw in keywords:
            # Count occurrences, weight longer keywords higher
            count = text_lower.count(kw)
            if count > 0:
                weight = len(kw.split()) + 1  # multi-word keywords score higher
                score += count * weight
        if score > 0:
            scores[category] = score

    if scores:
        return max(scores, key=scores.get)
    return "Other"


# ═══════════════════════════════════════════════════════════
# MAIN PARSER — Public Interface
# ═══════════════════════════════════════════════════════════

def parse_invoice_from_text(extracted_text: str, voucher_type: str = "") -> Dict[str, Any]:
    """
    Parse invoice data from LlamaParse extracted text using rule-based extraction.
    Returns structured dict matching the database schema.

    Args:
        extracted_text: Raw markdown from LlamaParse
        voucher_type: Optional hint (Sales, Purchase, etc.)

    Returns:
        Dict with: vendor_name, gst_number, invoice_number, invoice_date,
                   amount, cgst_amount, sgst_amount, igst_amount, gst_amount,
                   total_amount, expenses_type, hsn_code, place_of_supply,
                   line_items, document_type, is_rcm, irn
    """

    result = {
        "vendor_name": "",
        "gst_number": None,
        "buyer_gstin": None,
        "invoice_number": "N/A",
        "invoice_date": None,
        "currency": "INR",
        "amount": None,
        "cgst_amount": None,
        "sgst_amount": None,
        "igst_amount": None,
        "gst_amount": None,
        "total_amount": None,
        "gst_rate": None,
        "discount": None,
        "tcs_amount": None,
        "round_off": None,
        "expenses_type": voucher_type or "Other",
        "hsn_code": None,
        "place_of_supply": None,
        "line_items": [],
        "document_type": "Invoice",
        "is_rcm": False,
        "irn": None,
        "amount_in_words": None,
    }

    # ── 1. GSTIN Extraction (context-aware seller vs buyer) ──
    gstin_data = _extract_gstins(extracted_text)
    result["gst_number"] = gstin_data["seller_gstin"]
    result["buyer_gstin"] = gstin_data["buyer_gstin"]

    # ── 2. Invoice Number ──
    for pattern in INVOICE_NO_PATTERNS:
        m = pattern.search(extracted_text)
        if m:
            inv_no = m.group(1).strip()
            # Validate: not too short, not just "No" or "Date"
            if len(inv_no) >= 2 and inv_no.lower() not in ('no', 'number', 'date', 'na', 'n/a'):
                result["invoice_number"] = inv_no
                break

    # ── 3. Invoice Date ──
    result["invoice_date"] = _find_invoice_date(extracted_text)

    # ── 4. All Amounts ──
    amounts = _extract_amounts(extracted_text)
    for field in ['amount', 'cgst_amount', 'sgst_amount', 'igst_amount',
                  'gst_amount', 'total_amount', 'gst_rate', 'discount',
                  'tcs_amount', 'round_off', 'amount_in_words']:
        if field in amounts:
            result[field] = amounts[field]

    # ── 5. Smart Amount Computation ──
    cgst = result.get("cgst_amount") or 0
    sgst = result.get("sgst_amount") or 0
    igst = result.get("igst_amount") or 0

    # Compute GST total from components
    if (cgst or sgst or igst) and not result.get("gst_amount"):
        result["gst_amount"] = round(cgst + sgst + igst, 2)

    # Compute total from subtotal + GST
    if result.get("amount") and result.get("gst_amount") and not result.get("total_amount"):
        total = result["amount"] + result["gst_amount"]
        if result.get("discount"):
            total -= result["discount"]
        if result.get("tcs_amount"):
            total += result["tcs_amount"]
        result["total_amount"] = round(total, 2)

    # Derive subtotal from total - GST
    if result.get("total_amount") and not result.get("amount") and result.get("gst_amount"):
        result["amount"] = round(result["total_amount"] - result["gst_amount"], 2)

    # Derive GST from total - subtotal
    if result.get("total_amount") and result.get("amount") and not result.get("gst_amount"):
        computed_gst = result["total_amount"] - result["amount"]
        if computed_gst > 0:
            result["gst_amount"] = round(computed_gst, 2)

    # If we have GST rate but no GST amount, compute it
    if result.get("amount") and result.get("gst_rate") and not result.get("gst_amount"):
        result["gst_amount"] = round(result["amount"] * result["gst_rate"] / 100, 2)
        if not result.get("total_amount"):
            result["total_amount"] = round(result["amount"] + result["gst_amount"], 2)

    # If we only found total (no subtotal/GST split), use it as-is
    if not result.get("amount") and not result.get("total_amount"):
        # Try to find any large number as the total
        # Exclude phone numbers (>10 digits), account numbers, etc.
        big_amounts = re.findall(r'[₹Rs.INR\s]*([\d,]+\.?\d+)', extracted_text)
        parsed_amounts = [_parse_amount(a) for a in big_amounts]
        # Filter: must be > 100 AND < 100 crore (reasonable invoice range)
        parsed_amounts = [a for a in parsed_amounts if 100 < a < 1_000_000_000]
        if parsed_amounts:
            result["total_amount"] = max(parsed_amounts)

    # ── 6. Vendor Name ──
    result["vendor_name"] = _extract_vendor_name(extracted_text)

    # ── 7. HSN/SAC Codes ──
    hsn_codes = _extract_hsn_sac_codes(extracted_text)
    if hsn_codes:
        result["hsn_code"] = hsn_codes[0]  # Primary HSN

    # ── 8. Place of Supply ──
    result["place_of_supply"] = _extract_place_of_supply(
        extracted_text, result.get("gst_number"), result.get("buyer_gstin")
    )

    # ── 9. Line Items ──
    result["line_items"] = _extract_line_items(extracted_text)

    # ── 10. Cross-validate amounts from line items ──
    if result["line_items"] and not result.get("amount"):
        line_total = sum(item.get("amount") or 0 for item in result["line_items"])
        if line_total > 0:
            result["amount"] = round(line_total, 2)

    # ── 11. Document Type & RCM ──
    result["document_type"] = _detect_document_type(extracted_text)
    result["is_rcm"] = _detect_rcm(extracted_text)
    result["irn"] = _extract_irn(extracted_text)

    # ── 12. Expense Classification ──
    result["expenses_type"] = _classify_expense(extracted_text, voucher_type)

    # ── 13. Determine IGST vs CGST+SGST from state comparison ──
    if gstin_data["seller_state"] and gstin_data["buyer_state"]:
        is_interstate = gstin_data["seller_state"] != gstin_data["buyer_state"]
        if is_interstate and result.get("gst_amount") and not result.get("igst_amount"):
            result["igst_amount"] = result["gst_amount"]
            result["cgst_amount"] = None
            result["sgst_amount"] = None
        elif not is_interstate and result.get("gst_amount") and not result.get("cgst_amount"):
            result["cgst_amount"] = round(result["gst_amount"] / 2, 2)
            result["sgst_amount"] = round(result["gst_amount"] / 2, 2)
            result["igst_amount"] = None

    logger.info(f"📄 Invoice parsed: {result['document_type']} | "
                f"#{result['invoice_number']} | "
                f"Vendor: {result['vendor_name']} | "
                f"GSTIN: {result['gst_number']} | "
                f"Total: ₹{result['total_amount']} | "
                f"Items: {len(result['line_items'])} | "
                f"Type: {result['expenses_type']}")

    return result
