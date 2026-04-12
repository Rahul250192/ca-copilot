"""
Rule-Based Bank Statement Parser
─────────────────────────────────
Parses bank statement markdown tables from LlamaParse output
using regex patterns. No AI API calls needed.

Handles:
- Markdown pipe-delimited table parsing
- Bank name and account number detection
- Date parsing (multiple Indian formats)
- Transaction categorization via keywords
- Party name extraction from narrations
"""

import re
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ─── Transaction Category Keywords ───────────────────
CATEGORY_KEYWORDS = {
    "Salary": ["salary", "sal/", "payroll", "wages", "sal cr", "sal-cr"],
    "Rent": ["rent ", "lease", "rent/", "rent-"],
    "GST Payment": ["gst", "cgst", "sgst", "igst", "goods and service", "gst tds"],
    "TDS": ["tds ", "tds/", "tax deducted", "tds-", "26as"],
    "Bank Charges": ["charges", "sms alert", "maintenance", "maint chg", "folio chg", "debit card",
                      "annual fee", "service charge", "stmt chg", "ecs charge"],
    "Interest Income": ["int cr", "interest credit", "int.cr", "interest paid", "int/cr", "int on"],
    "Interest Paid": ["int dr", "interest debit", "int.dr", "int/dr", "emi int"],
    "Loan EMI": ["emi", "loan", "housing loan", "personal loan", "auto loan", "car loan"],
    "Insurance": ["insurance", "lic ", "premium", "policy"],
    "UPI": ["upi/", "upi-", "google pay", "phonepe", "paytm", "gpay", "bhim"],
    "Dividend": ["dividend", "div/", "interim div"],
    "Transfer": ["neft", "rtgs", "imps", "fund transfer", "ft-", "ft/", "trf", "mob trf"],
    "Cash Withdrawal": ["atm", "cash wdl", "atm-", "cash withdrawal", "atm wdl"],
    "Cash Deposit": ["cash dep", "cash deposit", "cdm"],
    "Refund": ["refund", "reversal", "cashback"],
    "Government": ["income tax", "advance tax", "self assessment", "mca ", "roc ", "stamp duty"],
    "Vendor Payment": ["vendor", "supplier", "payment to"],
    "Client Receipt": ["client", "receipt from", "receivable"],
    "Utilities": ["electricity", "bescom", "water", "bwssb", "gas", "broadband", "airtel", "jio", "act fibernet"],
}

# ─── Bank Detection ──────────────────────────────────
BANK_PATTERNS = {
    "State Bank of India": ["state bank", "sbi", "sbin"],
    "HDFC Bank": ["hdfc bank", "hdfc"],
    "ICICI Bank": ["icici bank", "icici"],
    "Axis Bank": ["axis bank"],
    "Kotak Mahindra Bank": ["kotak", "kkbk"],
    "Yes Bank": ["yes bank"],
    "Punjab National Bank": ["pnb", "punjab national"],
    "Bank of Baroda": ["bank of baroda", "bob"],
    "IndusInd Bank": ["indusind"],
    "Federal Bank": ["federal bank"],
    "Canara Bank": ["canara"],
    "Union Bank": ["union bank"],
    "IDBI Bank": ["idbi"],
    "Indian Bank": ["indian bank"],
    "Bank of India": ["bank of india"],
}


def parse_bank_statement_from_text(extracted_text: str) -> Dict[str, Any]:
    """
    Parse bank statement from LlamaParse markdown using regex rules.
    Returns structured dict matching the AI output format.
    """
    result = {
        "bank_name": "",
        "account_number": "",
        "period_start": None,
        "period_end": None,
        "opening_balance": None,
        "closing_balance": None,
        "transactions": [],
    }

    # ── Detect Bank Name ──
    result["bank_name"] = _detect_bank(extracted_text)

    # ── Extract Account Number ──
    acc_match = re.search(r'(?:A/c|Account|Acct)\s*(?:No|Number|#)?[.:\s]*(\d[\d\sX*]+\d)', extracted_text, re.IGNORECASE)
    if acc_match:
        result["account_number"] = acc_match.group(1).strip()

    # ── Extract Transactions from Markdown Tables ──
    transactions = _parse_transactions_from_tables(extracted_text)
    result["transactions"] = transactions

    # ── Derive period and balances from transactions ──
    if transactions:
        dates = [t["date"] for t in transactions if t.get("date")]
        if dates:
            result["period_start"] = min(dates)
            result["period_end"] = max(dates)

        # First transaction balance - its amount = opening balance (rough)
        first_bal = transactions[0].get("balance")
        last_bal = transactions[-1].get("balance")
        if first_bal is not None:
            first_amt = transactions[0].get("debit") or transactions[0].get("credit") or 0
            if transactions[0].get("credit"):
                result["opening_balance"] = first_bal - first_amt
            elif transactions[0].get("debit"):
                result["opening_balance"] = first_bal + first_amt
        if last_bal is not None:
            result["closing_balance"] = last_bal

    logger.info(f"Rule parser: Bank={result['bank_name']}, "
                f"Account={result['account_number']}, "
                f"{len(transactions)} transactions")

    return result


def _detect_bank(text: str) -> str:
    """Detect bank name from text.
    Checks header area (first 500 chars) first to avoid false matches
    from bank names appearing in transaction narrations."""
    # Priority 1: Check header/account info area only (before transactions)
    header_area = text[:500].lower()
    for bank_name, keywords in BANK_PATTERNS.items():
        for kw in keywords:
            if kw in header_area:
                return bank_name

    # Priority 1b: Bank-specific field patterns in header area
    # Kotak uses "Cust.Reln.No" which is unique to their statements
    if 'cust.reln' in header_area or 'cust. reln' in header_area:
        return "Kotak Mahindra Bank"

    # Priority 2: Check the Branch/IFSC field specifically
    branch_match = re.search(r'(?:Branch|IFSC)[:\s]*([A-Za-z0-9\-\s]+)', text[:2000], re.IGNORECASE)
    if branch_match:
        branch_lower = branch_match.group(1).lower()
        for bank_name, keywords in BANK_PATTERNS.items():
            for kw in keywords:
                if kw in branch_lower:
                    return bank_name

    # Priority 3: Check full header area (up to 2000 chars)
    text_lower = text[:2000].lower()
    for bank_name, keywords in BANK_PATTERNS.items():
        for kw in keywords:
            if kw in text_lower:
                return bank_name
    return "Unknown Bank"


def _parse_transactions_from_tables(text: str) -> List[Dict]:
    """Extract transactions from markdown pipe-delimited tables."""
    transactions = []
    in_table = False
    col_map = {}

    for line in text.split('\n'):
        stripped = line.strip()

        if not stripped.startswith('|'):
            if in_table and transactions:
                # Reset for next table
                in_table = False
                col_map = {}
            continue

        # Split by pipe, preserving empty cells (important for column alignment)
        raw_cols = stripped.split('|')
        # First and last elements are empty from leading/trailing pipes — remove them
        if raw_cols and raw_cols[0].strip() == '':
            raw_cols = raw_cols[1:]
        if raw_cols and raw_cols[-1].strip() == '':
            raw_cols = raw_cols[:-1]
        cols = [c.strip() for c in raw_cols]

        # Skip separator rows (allow empty cells)
        if cols and all(re.match(r'^[-:]+$', c) or c == '' for c in cols):
            in_table = True
            continue

        # Detect header row
        if not in_table and not col_map:
            lower_cols = [c.lower() for c in cols]
            has_date = any('date' in c for c in lower_cols)
            has_money = any(k in ' '.join(lower_cols) for k in ['debit', 'credit', 'withdrawal', 'deposit', 'amount', 'dr', 'cr'])

            if has_date and has_money:
                col_map = _map_columns(lower_cols)
                in_table = True
                continue

        # Parse data rows
        if in_table and col_map and len(cols) >= 3:
            txn = _parse_transaction_row(cols, col_map)
            if txn and txn.get("date"):
                transactions.append(txn)

    # If no markdown tables found, try line-by-line parsing
    if not transactions:
        transactions = _parse_freeform_transactions(text)

    return transactions


def _map_columns(headers: List[str]) -> Dict[str, int]:
    """Map header names to column indices.
    Handles both separate Debit/Credit columns and combined
    'Withdrawal (Dr)/ Deposit (Cr)' column (Kotak format)."""
    col_map = {}
    for i, h in enumerate(headers):
        if 'date' in h and 'value' not in h and 'val' not in h:
            col_map['date'] = i
        elif 'value' in h and 'date' in h:
            col_map['value_date'] = i
        elif 'val' in h and 'date' in h:
            col_map['value_date'] = i
        elif any(k in h for k in ['description', 'narration', 'particular', 'detail', 'remark']):
            col_map['description'] = i
        elif ('withdraw' in h or 'dr' in h) and ('deposit' in h or 'cr' in h):
            # Combined column: "Withdrawal (Dr)/ Deposit (Cr)" (Kotak format)
            col_map['combined_amount'] = i
        elif any(k in h for k in ['withdraw', 'debit', ' dr']):
            col_map['debit'] = i
        elif any(k in h for k in ['deposit', 'credit', ' cr']):
            col_map['credit'] = i
        elif 'balance' in h:
            col_map['balance'] = i
        elif any(k in h for k in ['chq', 'cheque', 'ref', 'txn']):
            col_map['reference_no'] = i
    return col_map


def _parse_transaction_row(cols: List[str], col_map: Dict[str, int]) -> Optional[Dict]:
    """Parse a single transaction row.
    Handles both separate Debit/Credit columns and combined
    amount column with (Dr)/(Cr) suffixes."""
    txn = {
        "date": None,
        "value_date": None,
        "description": "",
        "reference_no": None,
        "debit": None,
        "credit": None,
        "balance": None,
        "category": "Other",
        "party_name": None,
    }

    for field, idx in col_map.items():
        if idx >= len(cols):
            continue
        val = cols[idx].strip()
        if not val or val == '-' or val == '--':
            continue

        if field == 'date':
            txn['date'] = _parse_date(val)
        elif field == 'value_date':
            txn['value_date'] = _parse_date(val)
        elif field == 'description':
            # Clean <br/> tags from LlamaParse output
            txn['description'] = re.sub(r'<br\s*/?>', ' ', val).strip()
        elif field == 'combined_amount':
            # Kotak format: "340,000.00(Dr)" or "76,650.00(Cr)"
            amt, direction = _parse_amount_with_direction(val)
            if amt is not None:
                if direction == 'dr':
                    txn['debit'] = amt
                else:
                    txn['credit'] = amt
        elif field == 'debit':
            txn['debit'] = _parse_amount(val)
        elif field == 'credit':
            txn['credit'] = _parse_amount(val)
        elif field == 'balance':
            # Strip (Cr)/(Dr) suffix from balance
            txn['balance'] = _parse_amount(val)
        elif field == 'reference_no':
            txn['reference_no'] = val

    if not txn['date']:
        return None

    # Categorize and extract party name
    if txn['description']:
        txn['category'] = _categorize_transaction(txn['description'])
        txn['party_name'] = _extract_party_name(txn['description'])

    return txn


def _parse_freeform_transactions(text: str) -> List[Dict]:
    """Fallback: try to parse transactions from non-table format."""
    transactions = []
    # Look for lines with date + amount pattern
    date_amount_re = re.compile(
        r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\s+(.+?)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)?'
    )
    for line in text.split('\n'):
        m = date_amount_re.search(line)
        if m:
            date_str = m.group(1)
            desc = m.group(2).strip()
            amt1 = _parse_amount(m.group(3))
            amt2 = _parse_amount(m.group(4)) if m.group(4) else None

            txn = {
                "date": _parse_date(date_str),
                "value_date": None,
                "description": desc,
                "reference_no": None,
                "debit": amt1 if amt2 is not None else None,
                "credit": amt2,
                "balance": None,
                "category": _categorize_transaction(desc),
                "party_name": _extract_party_name(desc),
            }
            if txn['date']:
                transactions.append(txn)

    return transactions


def _categorize_transaction(description: str) -> str:
    """Categorize transaction by keyword matching."""
    desc_lower = description.lower()
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in desc_lower)
        if score > 0:
            scores[category] = score

    if scores:
        return max(scores, key=scores.get)
    return "Other"


def _extract_party_name(description: str) -> Optional[str]:
    """Extract counterparty name from narration."""
    desc = description.strip()

    # NEFT/RTGS/IMPS patterns: "NEFT-CR-BANKCODE-NAME-REF"
    neft_match = re.search(r'(?:NEFT|RTGS|IMPS)[-/](?:CR|DR|N)?\d*[-/]?\w*[-/]([A-Za-z\s&.]+?)(?:[-/]|$)', desc, re.IGNORECASE)
    if neft_match:
        name = neft_match.group(1).strip()
        if len(name) > 2:
            return name

    # UPI pattern: "UPI/123456/NAME/upiid@bank"
    upi_match = re.search(r'UPI/\d+/([A-Za-z\s&.]+?)/', desc, re.IGNORECASE)
    if upi_match:
        return upi_match.group(1).strip()

    # "BY CLG" / "BY TRANSFER" — cheque clearing
    clg_match = re.search(r'(?:BY CLG|BY TRANSFER|BY CLEARING)[-\s]*(.+?)(?:$|\d)', desc, re.IGNORECASE)
    if clg_match:
        name = clg_match.group(1).strip()
        if len(name) > 2:
            return name

    return None


def _parse_date(s: str) -> Optional[str]:
    """Parse date string into ISO format."""
    if not s or len(s) < 6:
        return None
    s = s.strip()
    formats = [
        '%d-%m-%Y', '%d/%m/%Y', '%d-%b-%Y', '%d/%b/%Y',
        '%d-%m-%y', '%d/%m/%y', '%d-%b-%y', '%d/%b/%y',
        '%Y-%m-%d', '%d.%m.%Y', '%d %b %Y',
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _parse_amount(s: str) -> Optional[float]:
    """Parse Indian formatted amount. Strips (Cr)/(Dr) suffixes."""
    if not s or s.strip() in ('-', '--', '', 'nil', 'Nil'):
        return None
    try:
        # Strip (Cr)/(Dr) suffixes
        cleaned = re.sub(r'\((?:Cr|Dr)\)', '', s, flags=re.IGNORECASE)
        cleaned = re.sub(r'[^\d.\-]', '', cleaned.replace(",", ""))
        return round(float(cleaned), 2) if cleaned else None
    except (ValueError, TypeError):
        return None


def _parse_amount_with_direction(s: str) -> tuple:
    """Parse amount with (Cr)/(Dr) suffix. Returns (amount, 'cr'|'dr').
    Used for combined Withdrawal/Deposit columns (Kotak format)."""
    if not s or s.strip() in ('-', '--', '', 'nil', 'Nil'):
        return None, None
    try:
        direction = 'cr'  # default
        if '(Dr)' in s or '(dr)' in s or '(DR)' in s:
            direction = 'dr'
        elif '(Cr)' in s or '(cr)' in s or '(CR)' in s:
            direction = 'cr'
        cleaned = re.sub(r'\((?:Cr|Dr)\)', '', s, flags=re.IGNORECASE)
        cleaned = re.sub(r'[^\d.\-]', '', cleaned.replace(",", ""))
        amt = round(float(cleaned), 2) if cleaned else None
        return amt, direction
    except (ValueError, TypeError):
        return None, None
