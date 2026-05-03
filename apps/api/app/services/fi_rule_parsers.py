"""
Rule-Based Financial Instrument Parsers
────────────────────────────────────────
Parses Demat, PMS, and 26AS markdown from LlamaParse output
using regex patterns. No AI API calls needed.

CAS/MF parser already exists at: app/services/cas_parser.py
"""

import re
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
# DEMAT (CDSL/NSDL) Parser
# ═══════════════════════════════════════════════════════

def parse_demat_markdown(raw_text: str) -> Dict[str, Any]:
    """Parse Demat holding statement from markdown."""
    result = {
        "dp_id": None,
        "client_id": None,
        "depository": None,
        "statement_date": None,
        "holdings": [],
        "transactions": [],
        "dividends": [],
        "capital_gains_summary": {"short_term_gain": None, "long_term_gain": None, "total_gain": None},
    }

    # Detect depository
    text_upper = raw_text[:2000].upper()
    if "CDSL" in text_upper:
        result["depository"] = "CDSL"
    elif "NSDL" in text_upper:
        result["depository"] = "NSDL"

    # Extract DP ID and Client ID
    dp_match = re.search(r'(?:DP\s*ID|Depository\s*Participant)[:\s]*(\w+)', raw_text, re.IGNORECASE)
    if dp_match:
        result["dp_id"] = dp_match.group(1).strip()

    cl_match = re.search(r'(?:Client\s*ID|BO\s*ID|Beneficiary)[:\s]*(\w+)', raw_text, re.IGNORECASE)
    if cl_match:
        result["client_id"] = cl_match.group(1).strip()

    # Parse holdings from tables
    result["holdings"] = _parse_demat_holdings(raw_text)

    # Parse transactions from tables
    result["transactions"] = _parse_demat_transactions(raw_text)

    # Also create 'funds' alias for dashboard compatibility
    result["funds"] = [
        {
            "fund_name": h["scrip_name"],
            "name": h["scrip_name"],
            "market_value": h.get("market_value", 0),
            "current_value": h.get("market_value", 0),
        }
        for h in result["holdings"]
    ]

    logger.info(f"Demat parser: {result['depository']}, "
                f"{len(result['holdings'])} holdings, "
                f"{len(result['transactions'])} transactions")

    return result


def _parse_demat_holdings(text: str) -> List[Dict]:
    """Extract holding rows from markdown tables."""
    holdings = []
    in_table = False
    header_cols = []

    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('|'):
            if in_table:
                in_table = False
                header_cols = []
            continue

        cols = [c.strip() for c in stripped.split('|') if c.strip()]

        # Skip separator
        if all(re.match(r'^[-:]+$', c) for c in cols):
            in_table = True
            continue

        # Detect holdings header
        lower_line = stripped.lower()
        if any(kw in lower_line for kw in ['isin', 'scrip', 'company', 'security']):
            if any(kw in lower_line for kw in ['qty', 'quantity', 'balance', 'holding', 'units']):
                header_cols = [c.lower() for c in cols]
                in_table = True
                continue

        if in_table and len(cols) >= 2:
            holding = _map_demat_holding(cols, header_cols)
            if holding:
                holdings.append(holding)

    return holdings


def _map_demat_holding(cols: List[str], headers: List[str]) -> Optional[Dict]:
    """Map a table row to a holding dict."""
    h = {
        "isin": "",
        "scrip_name": "",
        "quantity": 0,
        "avg_cost": None,
        "market_value": None,
        "market_price": None,
    }

    if headers and len(cols) == len(headers):
        for i, hdr in enumerate(headers):
            val = cols[i]
            if any(k in hdr for k in ['isin']):
                isin_match = re.search(r'(IN[A-Z0-9]{10})', val)
                h['isin'] = isin_match.group(1) if isin_match else val
            elif any(k in hdr for k in ['scrip', 'company', 'security', 'name']):
                h['scrip_name'] = val
            elif any(k in hdr for k in ['qty', 'quantity', 'balance', 'holding', 'units']):
                h['quantity'] = _parse_int(val)
            elif any(k in hdr for k in ['cost', 'avg']):
                h['avg_cost'] = _parse_float(val)
            elif any(k in hdr for k in ['market value', 'current value', 'value']):
                h['market_value'] = _parse_float(val)
            elif any(k in hdr for k in ['market price', 'current price', 'price', 'cmp', 'ltp']):
                h['market_price'] = _parse_float(val)
    else:
        # Positional fallback
        if len(cols) >= 3:
            # Try to find ISIN
            for col in cols:
                if re.match(r'^IN[A-Z0-9]{10}$', col.strip()):
                    h['isin'] = col.strip()
                    break
            h['scrip_name'] = cols[0] if not h['isin'] else cols[1]
            # Last numeric columns are likely qty and value
            for col in reversed(cols):
                num = _parse_float(col)
                if num and not h.get('market_value'):
                    h['market_value'] = num
                elif num and not h.get('quantity'):
                    h['quantity'] = int(num) if num == int(num) else 0

    if not h['scrip_name'] or h['quantity'] <= 0:
        return None
    return h


def _parse_demat_transactions(text: str) -> List[Dict]:
    """Extract transaction rows from markdown tables."""
    transactions = []
    in_table = False
    header_cols = []

    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('|'):
            in_table = False
            header_cols = []
            continue

        cols = [c.strip() for c in stripped.split('|') if c.strip()]

        if all(re.match(r'^[-:]+$', c) for c in cols):
            in_table = True
            continue

        lower_line = stripped.lower()
        if any(kw in lower_line for kw in ['trade', 'transaction', 'settlement']):
            if any(kw in lower_line for kw in ['date', 'buy', 'sell', 'type']):
                header_cols = [c.lower() for c in cols]
                in_table = True
                continue

        if in_table and len(cols) >= 3:
            date = _parse_date(cols[0])
            if date:
                txn = {
                    "date": date,
                    "isin": None,
                    "scrip_name": cols[1] if len(cols) > 1 else "",
                    "type": _classify_demat_txn(stripped),
                    "quantity": _parse_int(cols[2]) if len(cols) > 2 else 0,
                    "price": _parse_float(cols[3]) if len(cols) > 3 else None,
                    "amount": _parse_float(cols[-1]) if len(cols) > 3 else None,
                    "buy_value": None,
                    "sell_value": None,
                    "gain_loss": None,
                    "holding_period": None,
                }
                # Find ISIN in any column
                for col in cols:
                    if re.match(r'^IN[A-Z0-9]{10}$', col.strip()):
                        txn['isin'] = col.strip()
                        break
                transactions.append(txn)

    return transactions


def _classify_demat_txn(line: str) -> str:
    """Classify demat transaction type."""
    lower = line.lower()
    if any(k in lower for k in ['buy', 'purchase', 'bought']):
        return "Buy"
    elif any(k in lower for k in ['sell', 'sold', 'sale']):
        return "Sell"
    elif 'bonus' in lower:
        return "Bonus"
    elif 'split' in lower:
        return "Split"
    elif 'dividend' in lower:
        return "Dividend"
    elif any(k in lower for k in ['ipo', 'allot']):
        return "IPO Allotment"
    elif 'transfer in' in lower:
        return "Transfer In"
    elif 'transfer out' in lower:
        return "Transfer Out"
    return "Buy"


def generate_journal_entries_for_demat(structured_data: Dict) -> List[Dict]:
    """Generate journal entries for demat transactions (rule-based)."""
    entries = []
    for txn in structured_data.get("transactions", []):
        amount = abs(txn.get("amount") or 0)
        if amount < 0.01:
            amount = abs((txn.get("quantity") or 0) * (txn.get("price") or 0))
        if amount < 0.01:
            continue

        scrip = txn.get("scrip_name", "Unknown")
        date = txn.get("date", "")
        txn_type = txn.get("type", "Buy")

        if txn_type == "Buy":
            entries.append({
                "date": date,
                "voucher_type": "Purchase",
                "narration": f"Purchase of {txn.get('quantity', 0)} shares of {scrip}",
                "ledger_entries": [
                    {"ledger_name": f"Investment in Equity - {scrip}", "side": "Dr", "amount": amount},
                    {"ledger_name": "Bank Account", "side": "Cr", "amount": amount},
                ]
            })
        elif txn_type == "Sell":
            entries.append({
                "date": date,
                "voucher_type": "Sales",
                "narration": f"Sale of {txn.get('quantity', 0)} shares of {scrip}",
                "ledger_entries": [
                    {"ledger_name": "Bank Account", "side": "Dr", "amount": amount},
                    {"ledger_name": f"Investment in Equity - {scrip}", "side": "Cr", "amount": amount},
                ]
            })
        elif txn_type == "Dividend":
            entries.append({
                "date": date,
                "voucher_type": "Receipt",
                "narration": f"Dividend received from {scrip}",
                "ledger_entries": [
                    {"ledger_name": "Bank Account", "side": "Dr", "amount": amount},
                    {"ledger_name": f"Dividend Income - {scrip}", "side": "Cr", "amount": amount},
                ]
            })

    return entries


# ═══════════════════════════════════════════════════════
# PMS Parser (for financial_instruments.py)
# ═══════════════════════════════════════════════════════

def parse_pms_markdown(raw_text: str) -> Dict[str, Any]:
    """Parse PMS statement from markdown."""
    result = {
        "portfolio_name": None,
        "pms_provider": None,
        "client_name": None,
        "statement_date": None,
        "portfolio_value": None,
        "invested_value": None,
        "holdings": [],
        "transactions": [],
        "fees": [],
        "capital_gains_summary": {"short_term_gain": None, "long_term_gain": None, "total_gain": None},
    }

    # Extract provider name from early text
    for line in raw_text.split('\n')[:10]:
        clean = line.strip().replace('**', '')
        if clean and len(clean) > 5:
            if not any(kw in clean.lower() for kw in ['date', 'period', 'page', 'client', 'http']):
                result["pms_provider"] = clean
                break

    # Parse tables for holdings and transactions
    result["holdings"] = _parse_generic_holdings(raw_text)
    result["transactions"] = _parse_generic_transactions(raw_text, "pms")

    # Also create 'funds' alias for dashboard
    result["funds"] = [
        {
            "fund_name": h["scrip_name"],
            "name": h["scrip_name"],
            "market_value": h.get("market_value", 0),
            "current_value": h.get("market_value", 0),
        }
        for h in result["holdings"]
    ]

    logger.info(f"PMS parser: {result['pms_provider']}, "
                f"{len(result['holdings'])} holdings, "
                f"{len(result['transactions'])} transactions")

    return result


def generate_journal_entries_for_pms(structured_data: Dict) -> List[Dict]:
    """Generate journal entries for PMS transactions (rule-based)."""
    # Reuse demat journal entry logic — same Dr/Cr patterns
    return generate_journal_entries_for_demat(structured_data)


# ═══════════════════════════════════════════════════════
# 26AS / AIS Parser
# ═══════════════════════════════════════════════════════

def parse_26as_markdown(raw_text: str) -> Dict[str, Any]:
    """Parse Form 26AS / AIS from markdown."""
    result = {
        "pan": None,
        "assessment_year": None,
        "financial_year": None,
        "tds_entries": [],
        "tcs_entries": [],
        "tax_paid": [],
        "sft_entries": [],
        "summary": {"total_tds": 0, "total_tcs": 0, "total_tax_paid": 0, "total_income_reported": 0},
    }

    # Extract PAN
    pan_match = re.search(r'\b([A-Z]{5}[0-9]{4}[A-Z])\b', raw_text)
    if pan_match:
        result["pan"] = pan_match.group(1)

    # Extract AY
    ay_match = re.search(r'(?:Assessment\s*Year|AY)\s*[:\s]*(\d{4}-\d{2,4})', raw_text, re.IGNORECASE)
    if ay_match:
        result["assessment_year"] = ay_match.group(1)

    # Extract FY
    fy_match = re.search(r'(?:Financial\s*Year|FY)\s*[:\s]*(\d{4}-\d{2,4})', raw_text, re.IGNORECASE)
    if fy_match:
        result["financial_year"] = fy_match.group(1)

    # Parse TDS entries from tables
    result["tds_entries"] = _parse_26as_tds_entries(raw_text)

    # Compute summary
    total_tds = sum(e.get("tds_deducted", 0) or 0 for e in result["tds_entries"])
    total_income = sum(e.get("amount_paid_credited", 0) or 0 for e in result["tds_entries"])
    result["summary"]["total_tds"] = total_tds
    result["summary"]["total_income_reported"] = total_income

    logger.info(f"26AS parser: PAN={result['pan']}, "
                f"{len(result['tds_entries'])} TDS entries, "
                f"Total TDS={total_tds}")

    return result


def _parse_26as_tds_entries(text: str) -> List[Dict]:
    """Parse TDS entries from 26AS markdown tables."""
    entries = []
    in_table = False
    header_cols = []
    current_section = ""

    # Detect section headers
    section_re = re.compile(r'(?:Part\s*A|Section\s*(\d{3}[A-Z]?))', re.IGNORECASE)

    for line in text.split('\n'):
        stripped = line.strip()

        # Detect section change
        sec_match = section_re.search(stripped)
        if sec_match and not stripped.startswith('|'):
            current_section = sec_match.group(1) or "194"

        if not stripped.startswith('|'):
            if in_table:
                in_table = False
            continue

        cols = [c.strip() for c in stripped.split('|') if c.strip()]

        if all(re.match(r'^[-:]+$', c) for c in cols):
            in_table = True
            continue

        # Detect header
        lower_line = stripped.lower()
        if any(kw in lower_line for kw in ['deductor', 'tan', 'name of', 'amount paid']):
            header_cols = [c.lower() for c in cols]
            in_table = True
            continue

        if in_table and len(cols) >= 3:
            entry = _map_26as_entry(cols, header_cols, current_section)
            if entry:
                entries.append(entry)

    return entries


def _map_26as_entry(cols: List[str], headers: List[str], section: str) -> Optional[Dict]:
    """Map a 26AS table row to a TDS entry dict."""
    entry = {
        "section": section,
        "section_description": _section_description(section),
        "tan_of_deductor": None,
        "deductor_name": "",
        "transaction_date": None,
        "amount_paid_credited": 0,
        "tds_deducted": 0,
        "tds_deposited": None,
    }

    if headers and len(cols) == len(headers):
        for i, hdr in enumerate(headers):
            val = cols[i]
            if any(k in hdr for k in ['tan']):
                tan_match = re.search(r'([A-Z]{4}\d{5}[A-Z])', val)
                entry['tan_of_deductor'] = tan_match.group(1) if tan_match else val
            elif any(k in hdr for k in ['deductor', 'name']):
                entry['deductor_name'] = val
            elif any(k in hdr for k in ['date']):
                entry['transaction_date'] = _parse_date(val)
            elif any(k in hdr for k in ['amount paid', 'amount credit', 'income']):
                entry['amount_paid_credited'] = _parse_float(val)
            elif any(k in hdr for k in ['tds deducted', 'tax deducted']):
                entry['tds_deducted'] = _parse_float(val)
            elif any(k in hdr for k in ['tds deposited', 'tax deposited']):
                entry['tds_deposited'] = _parse_float(val)
    else:
        # Positional: TAN | Name | Date? | Amount | TDS
        if len(cols) >= 4:
            # Check if first col is TAN
            if re.match(r'^[A-Z]{4}\d{5}[A-Z]$', cols[0].strip()):
                entry['tan_of_deductor'] = cols[0].strip()
                entry['deductor_name'] = cols[1]
                entry['amount_paid_credited'] = _parse_float(cols[-2])
                entry['tds_deducted'] = _parse_float(cols[-1])
            else:
                entry['deductor_name'] = cols[0]
                entry['amount_paid_credited'] = _parse_float(cols[-2])
                entry['tds_deducted'] = _parse_float(cols[-1])

    if not entry['deductor_name'] and not entry['amount_paid_credited']:
        return None

    return entry


def _section_description(section: str) -> str:
    """Map section code to description."""
    descriptions = {
        "194": "Dividend",
        "194A": "Interest (other than on securities)",
        "194B": "Lottery / Game Show",
        "194C": "Payment to Contractor",
        "194D": "Insurance Commission",
        "194DA": "Maturity of Life Insurance",
        "194H": "Commission / Brokerage",
        "194I": "Rent",
        "194IA": "Transfer of Immovable Property",
        "194J": "Professional / Technical Fees",
        "194K": "Income from Mutual Fund",
        "194N": "Cash Withdrawal",
        "194Q": "Purchase of Goods",
        "196D": "Income of FII",
    }
    return descriptions.get(section, f"Section {section}")


# ═══════════════════════════════════════════════════════
# Shared Utility Functions
# ═══════════════════════════════════════════════════════

def _parse_generic_holdings(text: str) -> List[Dict]:
    """Generic holdings table parser (works for PMS / portfolio)."""
    holdings = []
    in_table = False
    header_cols = []

    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('|'):
            in_table = False
            header_cols = []
            continue

        cols = [c.strip() for c in stripped.split('|') if c.strip()]

        if all(re.match(r'^[-:]+$', c) for c in cols):
            in_table = True
            continue

        lower_line = stripped.lower()
        if any(kw in lower_line for kw in ['scrip', 'security', 'stock', 'company']):
            if any(kw in lower_line for kw in ['qty', 'quantity', 'value', 'holding']):
                header_cols = [c.lower() for c in cols]
                in_table = True
                continue

        if in_table and len(cols) >= 2:
            h = _map_demat_holding(cols, header_cols)
            if h:
                holdings.append(h)

    return holdings


def _parse_generic_transactions(text: str, context: str = "") -> List[Dict]:
    """Generic transaction table parser."""
    transactions = []
    in_table = False

    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('|'):
            in_table = False
            continue

        cols = [c.strip() for c in stripped.split('|') if c.strip()]

        if all(re.match(r'^[-:]+$', c) for c in cols):
            in_table = True
            continue

        if in_table and len(cols) >= 3:
            date = _parse_date(cols[0])
            if date:
                txn = {
                    "date": date,
                    "scrip_name": cols[1] if len(cols) > 1 else "",
                    "type": _classify_demat_txn(stripped),
                    "quantity": _parse_int(cols[2]) if len(cols) > 2 else 0,
                    "price": _parse_float(cols[3]) if len(cols) > 3 else None,
                    "amount": _parse_float(cols[-1]) if len(cols) > 3 else _parse_float(cols[-1]),
                    "brokerage": None,
                    "gain_loss": None,
                }
                transactions.append(txn)

    return transactions


def _parse_date(s: str) -> Optional[str]:
    """Parse date into ISO format."""
    if not s or len(s) < 6:
        return None
    s = s.strip()
    for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%d-%b-%Y', '%d/%b/%Y',
                '%d-%m-%y', '%d/%m/%y', '%d %b %Y', '%d.%m.%Y']:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.year < 100:
                dt = dt.replace(year=dt.year + 2000)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _parse_float(s: str) -> float:
    """Parse Indian formatted number."""
    if not s:
        return 0
    try:
        cleaned = re.sub(r'[^\d.\-]', '', s.replace(",", ""))
        return round(float(cleaned), 2) if cleaned else 0
    except (ValueError, TypeError):
        return 0


def _parse_int(s: str) -> int:
    """Parse integer from string."""
    f = _parse_float(s)
    return int(f)
