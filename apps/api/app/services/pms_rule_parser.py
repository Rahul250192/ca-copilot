"""
Rule-Based PMS Statement Parsers
─────────────────────────────────
Parses PMS Transaction, Dividend, and Expense statements from
LlamaParse markdown output. No AI API calls needed.
"""

import re
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def parse_pms_statement(text: str, statement_type: str) -> Dict[str, Any]:
    """Route to appropriate PMS parser based on statement type."""
    if statement_type == "transaction":
        return parse_pms_transactions(text)
    elif statement_type == "dividend":
        return parse_pms_dividends(text)
    elif statement_type == "expenses":
        return parse_pms_expenses(text)
    else:
        return parse_pms_transactions(text)


def parse_pms_transactions(text: str) -> Dict[str, Any]:
    """Parse PMS transaction statement."""
    result = {
        "provider_name": "",
        "client_name": None,
        "period_from": None,
        "period_to": None,
        "strategies": [],
        "transactions": [],
    }

    # Extract provider from first lines
    for line in text.split('\n')[:10]:
        clean = line.strip().replace('**', '')
        if clean and len(clean) > 5:
            if not any(kw in clean.lower() for kw in ['date', 'period', 'page', 'transaction', 'http', '|']):
                result["provider_name"] = clean
                break

    # Extract period
    period_match = re.search(r'(?:Period|From)\s*[:\s]*(\d{1,2}[-/]\w{3,9}[-/]\d{2,4})\s*(?:to|[-–])\s*(\d{1,2}[-/]\w{3,9}[-/]\d{2,4})', text, re.IGNORECASE)
    if period_match:
        result["period_from"] = _parse_date(period_match.group(1))
        result["period_to"] = _parse_date(period_match.group(2))

    # Parse transaction rows from markdown tables
    result["transactions"] = _parse_pms_tx_rows(text)

    logger.info(f"PMS TX parser: {result['provider_name']}, {len(result['transactions'])} transactions")
    return result


def parse_pms_dividends(text: str) -> Dict[str, Any]:
    """Parse PMS dividend statement (e.g., Abakkus Statement of Dividend)."""
    result = {
        "provider_name": "",
        "investor_name": "",
        "pms_provider": "",
        "period_from": None,
        "period_to": None,
        "statement_period_start": None,
        "statement_period_end": None,
        "dividends": [],
    }

    # Normalize text: split <br/> tags
    normalized = text.replace("<br/>", "\n").replace("<br>", "\n")
    normalized = normalized.replace("\\*\\*", "").replace("\\*", "").replace("**", "")

    # Extract metadata
    # Period: "From 01/04/2025 to 31/03/2026"
    period_match = re.search(r'(?:From|Period)\s*[:\s]*([\d/\-\.]+\d{4})\s*(?:to|[-–])\s*([\d/\-\.]+\d{4})', normalized, re.IGNORECASE)
    if period_match:
        result["period_from"] = _parse_date(period_match.group(1))
        result["period_to"] = _parse_date(period_match.group(2))
        result["statement_period_start"] = result["period_from"]
        result["statement_period_end"] = result["period_to"]

    # Investor: "Account : 106043 ABAJF314 - Tradex India Corporation Private Limited"
    investor_match = re.search(r'Account\s*[:\s]*\S+\s+\S+\s*-\s*(.+?)(?:\n|$)', normalized, re.IGNORECASE)
    if investor_match:
        result["investor_name"] = investor_match.group(1).strip()

    # Provider: line after Account line (e.g., "Abakkus All Cap Approach")
    provider_match = re.search(r'Account[^\n]*\n\s*(.+?)(?:\n|$)', normalized, re.IGNORECASE)
    if provider_match:
        prov = provider_match.group(1).strip()
        if prov and not prov.startswith('From') and not prov.startswith('|'):
            result["pms_provider"] = prov
            result["provider_name"] = prov

    result["dividends"] = _parse_pms_div_rows(text)
    logger.info(f"PMS Div parser: {len(result['dividends'])} dividends, "
                f"investor={result['investor_name']}, period={result['period_from']} to {result['period_to']}")
    return result


def parse_pms_expenses(text: str) -> Dict[str, Any]:
    """Parse PMS expense statement."""
    result = {
        "provider_name": "",
        "period_from": None,
        "period_to": None,
        "expenses": [],
    }

    for line in text.split('\n')[:10]:
        clean = line.strip().replace('**', '')
        if clean and len(clean) > 5:
            if not any(kw in clean.lower() for kw in ['date', 'period', 'page', 'expense', 'http', '|']):
                result["provider_name"] = clean
                break

    result["expenses"] = _parse_pms_exp_rows(text)
    logger.info(f"PMS Exp parser: {len(result['expenses'])} expenses")
    return result


# ─── PMS Transaction Row Parser ───────────────────────

EXPENSE_TYPES = {
    "stt": "STT",
    "management fee": "Management Fee",
    "custody": "Custody Fee",
    "fund accounting": "Fund Accounting Fee",
    "stamp duty": "Stamp Duty",
    "sebi": "SEBI Charges",
    "performance fee": "Performance Fee",
    "gst": "GST",
    "exit load": "Exit Load",
    "brokerage": "Brokerage",
}


def _parse_pms_tx_rows(text: str) -> List[Dict]:
    """Extract PMS transaction rows from markdown tables."""
    transactions = []
    in_table = False
    header_cols = []
    current_strategy = ""

    for line in text.split('\n'):
        stripped = line.strip()

        # Detect strategy headers
        strat_match = re.match(r'(?:#{2,3}|(?:\*\*))?\s*(?:Strategy|Portfolio)[:\s]*(.+?)(?:\*\*)?$', stripped, re.IGNORECASE)
        if strat_match:
            current_strategy = strat_match.group(1).strip()
            continue

        if not stripped.startswith('|'):
            if in_table:
                in_table = False
                header_cols = []
            continue

        cols = [c.strip() for c in stripped.split('|') if c.strip()]

        if all(re.match(r'^[-:]+$', c) for c in cols):
            in_table = True
            continue

        lower_line = stripped.lower()
        if any(kw in lower_line for kw in ['date', 'trade date', 'settlement']):
            if any(kw in lower_line for kw in ['security', 'scrip', 'script', 'isin', 'stock', 'qty', 'quantity']):
                header_cols = [c.lower() for c in cols]
                in_table = True
                continue

        if in_table and len(cols) >= 3:
            txn = _map_pms_tx_row(cols, header_cols, current_strategy)
            if txn:
                transactions.append(txn)

    return transactions


def _map_pms_tx_row(cols: List[str], headers: List[str], strategy: str = "") -> Optional[Dict]:
    """Map a PMS transaction row."""
    txn = {
        "date": None, "security_name": "", "isin": None, "exchange": None,
        "tx_type": "BUY", "quantity": None, "unit_price": None,
        "brokerage": None, "stt": None, "stamp_duty": None,
        "settlement_amt": 0, "strategy_name": strategy or None, "narration": None,
    }

    if headers and len(cols) == len(headers):
        for i, hdr in enumerate(headers):
            val = cols[i]
            if any(k in hdr for k in ['date', 'trade']):
                txn['date'] = _parse_date(val)
            elif any(k in hdr for k in ['security', 'scrip', 'script', 'stock', 'name']):
                txn['security_name'] = val
            elif 'isin' in hdr:
                txn['isin'] = val if val and len(val) >= 10 else None
            elif any(k in hdr for k in ['exchange', 'exch']):
                txn['exchange'] = val
            elif any(k in hdr for k in ['type', 'buy/sell', 'b/s']):
                txn['tx_type'] = _classify_pms_tx(val)
            elif any(k in hdr for k in ['qty', 'quantity', 'unit']):
                txn['quantity'] = _parse_float(val)
            elif any(k in hdr for k in ['price', 'rate']):
                txn['unit_price'] = _parse_float(val)
            elif any(k in hdr for k in ['brokerage', 'brok']):
                txn['brokerage'] = _parse_float(val)
            elif 'stt' in hdr:
                txn['stt'] = _parse_float(val)
            elif any(k in hdr for k in ['settlement', 'amount', 'value', 'total']):
                txn['settlement_amt'] = _parse_float(val)
    else:
        if len(cols) >= 4:
            txn['date'] = _parse_date(cols[0])
            txn['security_name'] = cols[1]
            txn['tx_type'] = _classify_pms_tx(cols[2]) if not cols[2].replace('.', '').replace(',', '').isdigit() else "BUY"
            txn['settlement_amt'] = _parse_float(cols[-1])

    if not txn['date'] or not txn['security_name']:
        return None
    return txn


def _classify_pms_tx(val: str) -> str:
    """Classify PMS transaction type."""
    lower = val.lower().strip()
    if any(k in lower for k in ['buy', 'purchase', 'b']):
        return "BUY"
    elif any(k in lower for k in ['sell', 'sale', 's']):
        return "SELL"
    elif 'dividend' in lower:
        return "DIVIDEND"
    elif 'tds' in lower:
        return "TDS_TRANSFER"
    elif 'bonus' in lower:
        return "BONUS"
    elif 'split' in lower:
        return "SPLIT"
    return "BUY"


# ─── PMS Dividend Row Parser ──────────────────────────

def _parse_pms_div_rows(text: str) -> List[Dict]:
    """Extract PMS dividend rows from markdown tables.

    Key fix: uses raw split('|') to preserve empty columns.
    e.g., "| a | | c |" → ['a', '', 'c'] instead of ['a', 'c']
    """
    dividends = []
    in_table = False
    header_cols = []

    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('|'):
            in_table = False
            header_cols = []
            continue

        # Split preserving empty columns
        raw_cols = stripped.split('|')
        # Remove leading/trailing empty strings from | borders
        if raw_cols and raw_cols[0].strip() == '':
            raw_cols = raw_cols[1:]
        if raw_cols and raw_cols[-1].strip() == '':
            raw_cols = raw_cols[:-1]
        cols = [c.strip() for c in raw_cols]

        # Separator row
        if all(re.match(r'^[-:]+$', c) for c in cols if c):
            in_table = True
            continue

        # Header detection
        lower_line = stripped.lower()
        if any(kw in lower_line for kw in ['security', 'scrip', 'company']):
            if any(kw in lower_line for kw in ['amount', 'dividend', 'gross', 'tds', 'rate']):
                header_cols = [c.lower() for c in cols]
                in_table = True
                continue

        if not in_table or len(cols) < 3:
            continue

        # Map columns by header
        div = {
            "security_name": "", "scrip_name": "", "isin": None,
            "date": None, "ex_date": None, "received_date": None,
            "quantity": None, "rate_per_share": None,
            "gross_amount": 0, "amount": 0,
            "tds_deducted": None, "net_received": None,
        }

        if header_cols and len(cols) == len(header_cols):
            for i, hdr in enumerate(header_cols):
                val = cols[i]
                if not val:
                    continue
                if any(k in hdr for k in ['security', 'scrip', 'company', 'name']) and 'amount' not in hdr:
                    div['security_name'] = val
                    div['scrip_name'] = val
                elif 'isin' in hdr:
                    div['isin'] = val if len(val) >= 10 else None
                elif 'ex' in hdr and 'date' in hdr:
                    div['ex_date'] = _parse_date(val)
                    div['date'] = div['ex_date']
                elif 'received' in hdr and 'date' in hdr:
                    div['received_date'] = _parse_date(val)
                    if not div['date']:
                        div['date'] = div['received_date']
                elif any(k in hdr for k in ['qty', 'quantity']):
                    div['quantity'] = _parse_float(val)
                elif any(k in hdr for k in ['rate', 'dps', 'per share']) and 'amount' not in hdr:
                    div['rate_per_share'] = _parse_float(val)
                elif 'receivable' in hdr:
                    div['gross_amount'] = _parse_float(val)
                elif 'net' in hdr:
                    div['net_received'] = _parse_float(val)
                elif 'tds' in hdr:
                    div['tds_deducted'] = _parse_float(val)
                # Skip "receivedamount" column (same as receivable for paid rows)
        else:
            # Positional fallback
            for c in cols[:2]:
                d = _parse_date(c)
                if d:
                    div['date'] = d
                    break
            for c in cols:
                if c and not _parse_date(c) and not c.replace(',', '').replace('.', '').replace('-', '').isdigit() and len(c) > 2:
                    div['security_name'] = c
                    div['scrip_name'] = c
                    break
            div['gross_amount'] = _parse_float(cols[-1])

        # Set amount
        if div['gross_amount'] and div['gross_amount'] > 0:
            div['amount'] = div['gross_amount']
        elif div['net_received'] and div['net_received'] > 0:
            div['amount'] = (div['net_received'] or 0) + (div['tds_deducted'] or 0)

        # Skip empty/zero/reversal rows
        if not div['security_name']:
            continue
        if div['gross_amount'] <= 0 and (div['amount'] or 0) <= 0:
            continue

        dividends.append(div)

    return dividends


# ─── PMS Expense Row Parser ───────────────────────────

def _parse_pms_exp_rows(text: str) -> List[Dict]:
    """Extract PMS expense rows from markdown tables."""
    expenses = []
    in_table = False
    is_paid_section = True

    for line in text.split('\n'):
        stripped = line.strip()
        lower = stripped.lower().replace('**', '')

        if 'payable' in lower:
            is_paid_section = False
        elif 'paid' in lower and 'payable' not in lower:
            is_paid_section = True

        if not stripped.startswith('|'):
            continue

        cols = [c.strip() for c in stripped.split('|') if c.strip()]

        if all(re.match(r'^[-:]+$', c) for c in cols):
            in_table = True
            continue

        if in_table and len(cols) >= 2:
            exp_type = _classify_expense_type(cols[0])
            amount = _parse_float(cols[-1])

            if exp_type and amount > 0:
                expense = {
                    "expense_type": exp_type,
                    "expense_date": None,
                    "period_from": None,
                    "period_to": None,
                    "amount": amount,
                    "gst_amount": None,
                    "tds_applicable": None,
                    "net_payable": None,
                    "is_paid": is_paid_section,
                    "is_accrual": 'accrual' in cols[0].lower(),
                    "is_stt": exp_type == "STT",
                    "narration": cols[0],
                }

                for col in cols[1:-1]:
                    date = _parse_date(col)
                    if date:
                        expense["expense_date"] = date
                        break

                if len(cols) >= 3:
                    for i, col in enumerate(cols):
                        if 'gst' in col.lower() or (i > 0 and 'gst' in cols[0].lower()):
                            expense["gst_amount"] = _parse_float(col)

                expenses.append(expense)

    return expenses


def _classify_expense_type(text: str) -> Optional[str]:
    """Classify PMS expense type from description."""
    lower = text.lower()
    for keyword, etype in EXPENSE_TYPES.items():
        if keyword in lower:
            return etype
    if any(k in lower for k in ['fee', 'charge', 'cost']):
        return "Other"
    if _parse_float(text) > 0:
        return None
    return "Other"


# ─── Utilities ────────────────────────────────────────

def _parse_date(s: str) -> Optional[str]:
    """Parse date into ISO format."""
    if not s or len(s) < 6:
        return None
    s = s.strip()
    for fmt in ['%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%d-%b-%Y', '%d/%b/%Y',
                '%d-%m-%y', '%d/%m/%y', '%d %b %Y', '%d.%m.%Y', '%d-%B-%Y']:
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
    if not s or s.strip() in ('-', '--', '', 'nil', 'Nil', 'N/A'):
        return 0
    try:
        cleaned = re.sub(r'[^\d.\-]', '', s.replace(",", ""))
        return round(float(cleaned), 2) if cleaned else 0
    except (ValueError, TypeError):
        return 0
