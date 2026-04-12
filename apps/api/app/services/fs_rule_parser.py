"""
Rule-Based Financial Statement Parser
──────────────────────────────────────
Parses Trial Balance and Balance Sheet from LlamaParse markdown
using regex + the existing TALLY_GROUP_MAP for account classification.

No AI API calls needed.
"""

import re
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def parse_trial_balance(text: str) -> Dict[str, Any]:
    """Parse Trial Balance from markdown text into structured format."""
    result = {
        "company_name": "",
        "as_at_date": "",
        "accounts": [],
    }

    # Extract company name (first bold text or first non-empty line)
    for line in text.split('\n')[:10]:
        clean = line.strip().replace('**', '')
        if clean and len(clean) > 3 and 'trial balance' not in clean.lower():
            if not any(kw in clean.lower() for kw in ['as at', 'period', 'date', 'page', '|']):
                result["company_name"] = clean
                break

    # Date extraction
    date_match = re.search(r'(?:as\s*(?:at|on)|period|date)[:\s]*(.+?)(?:\n|$)', text, re.IGNORECASE)
    if date_match:
        result["as_at_date"] = date_match.group(1).strip()

    # Parse accounts from markdown tables
    result["accounts"] = _parse_tb_accounts(text)

    logger.info(f"TB Parser: {result['company_name']}, {len(result['accounts'])} accounts")
    return result


def _parse_tb_accounts(text: str) -> List[Dict]:
    """Extract TB accounts from markdown tables."""
    accounts = []
    in_table = False
    header_cols = []

    for line in text.split('\n'):
        stripped = line.strip()
        if not stripped.startswith('|'):
            if in_table:
                in_table = False
            continue

        cols = [c.strip() for c in stripped.split('|') if c.strip()]

        # Skip separator
        if all(re.match(r'^[-:]+$', c) for c in cols):
            in_table = True
            continue

        # Detect header
        lower_line = stripped.lower()
        if any(kw in lower_line for kw in ['ledger', 'account', 'particular', 'name']):
            if any(kw in lower_line for kw in ['debit', 'credit', 'dr', 'cr', 'balance', 'amount']):
                header_cols = [c.lower() for c in cols]
                in_table = True
                continue

        if in_table and len(cols) >= 2:
            account = _map_tb_account(cols, header_cols)
            if account:
                accounts.append(account)

    return accounts


def _map_tb_account(cols: List[str], headers: List[str]) -> Optional[Dict]:
    """Map a table row to a TB account dict."""
    acc = {
        "account_name": "",
        "group": "",
        "debit": 0,
        "credit": 0,
    }

    if headers and len(cols) == len(headers):
        for i, hdr in enumerate(headers):
            val = cols[i]
            if any(k in hdr for k in ['ledger', 'account', 'particular', 'name']):
                acc['account_name'] = val
            elif any(k in hdr for k in ['group', 'category', 'head']):
                acc['group'] = val
            elif any(k in hdr for k in ['debit', ' dr']):
                acc['debit'] = _parse_amount(val)
            elif any(k in hdr for k in ['credit', ' cr']):
                acc['credit'] = _parse_amount(val)
    else:
        # Positional: Name | Group? | Debit | Credit
        if len(cols) >= 3:
            acc['account_name'] = cols[0]
            if len(cols) >= 4:
                acc['group'] = cols[1]
                acc['debit'] = _parse_amount(cols[2])
                acc['credit'] = _parse_amount(cols[3])
            else:
                acc['debit'] = _parse_amount(cols[1])
                acc['credit'] = _parse_amount(cols[2])

    if not acc['account_name'] or (acc['debit'] == 0 and acc['credit'] == 0):
        return None

    return acc


def parse_balance_sheet(text: str) -> Dict[str, Any]:
    """Parse previous year Balance Sheet from markdown text."""
    result = {
        "company_name": "",
        "as_at_date": "",
        "assets": [],
        "liabilities": [],
    }

    # Simple: extract line items from tables
    current_section = "liabilities"
    in_table = False

    for line in text.split('\n'):
        stripped = line.strip()

        # Section detection
        lower = stripped.lower().replace('**', '')
        if 'asset' in lower and ('total' not in lower):
            current_section = "assets"
        elif any(k in lower for k in ['liabilit', 'equity', 'capital', 'reserve']):
            current_section = "liabilities"

        if not stripped.startswith('|'):
            continue

        cols = [c.strip() for c in stripped.split('|') if c.strip()]

        if all(re.match(r'^[-:]+$', c) for c in cols):
            in_table = True
            continue

        if in_table and len(cols) >= 2:
            name = cols[0]
            amount = _parse_amount(cols[-1])
            if name and amount > 0 and not re.match(r'^[-:]+$', name):
                item = {"name": name, "amount": amount}
                result[current_section].append(item)

    return result


def map_tb_to_schedule_iii(tb_data: Dict, prev_bs: Optional[Dict] = None) -> Dict:
    """
    Map Trial Balance accounts to Schedule III Balance Sheet / P&L heads.
    Uses the same TALLY_GROUP_MAP pattern that already works for Tally-sourced data.
    """
    # Expanded mapping: account name keywords → (category, schedule_iii_head)
    ACCOUNT_MAP = {
        # Equity
        'capital': ('Equity', 'Share Capital'),
        'share capital': ('Equity', 'Share Capital'),
        'reserves': ('Equity', 'Reserves & Surplus'),
        'surplus': ('Equity', 'Reserves & Surplus'),
        'retained earnings': ('Equity', 'Reserves & Surplus'),
        'profit & loss': ('Equity', 'Reserves & Surplus'),
        'profit and loss': ('Equity', 'Reserves & Surplus'),

        # Non-current liabilities
        'long term': ('Non-Current Liabilities', 'Long Term Borrowings'),
        'term loan': ('Non-Current Liabilities', 'Long Term Borrowings'),
        'secured loan': ('Non-Current Liabilities', 'Long Term Borrowings'),
        'unsecured loan': ('Non-Current Liabilities', 'Long Term Borrowings'),
        'deferred tax': ('Non-Current Liabilities', 'Deferred Tax Liabilities'),

        # Current liabilities
        'sundry creditor': ('Current Liabilities', 'Trade Payables'),
        'trade payable': ('Current Liabilities', 'Trade Payables'),
        'creditor': ('Current Liabilities', 'Trade Payables'),
        'duties & taxes': ('Current Liabilities', 'Other Current Liabilities'),
        'gst payable': ('Current Liabilities', 'Other Current Liabilities'),
        'tds payable': ('Current Liabilities', 'Other Current Liabilities'),
        'provision': ('Current Liabilities', 'Short Term Provisions'),
        'outstanding': ('Current Liabilities', 'Other Current Liabilities'),
        'advance from customer': ('Current Liabilities', 'Other Current Liabilities'),
        'short term borrow': ('Current Liabilities', 'Short Term Borrowings'),
        'bank od': ('Current Liabilities', 'Short Term Borrowings'),
        'overdraft': ('Current Liabilities', 'Short Term Borrowings'),

        # Non-current assets
        'fixed asset': ('Non-Current Assets', 'Fixed Assets (Tangible)'),
        'building': ('Non-Current Assets', 'Fixed Assets (Tangible)'),
        'furniture': ('Non-Current Assets', 'Fixed Assets (Tangible)'),
        'vehicle': ('Non-Current Assets', 'Fixed Assets (Tangible)'),
        'machinery': ('Non-Current Assets', 'Fixed Assets (Tangible)'),
        'computer': ('Non-Current Assets', 'Fixed Assets (Tangible)'),
        'plant': ('Non-Current Assets', 'Fixed Assets (Tangible)'),
        'land': ('Non-Current Assets', 'Fixed Assets (Tangible)'),
        'intangible': ('Non-Current Assets', 'Fixed Assets (Intangible)'),
        'goodwill': ('Non-Current Assets', 'Fixed Assets (Intangible)'),
        'software': ('Non-Current Assets', 'Fixed Assets (Intangible)'),
        'patent': ('Non-Current Assets', 'Fixed Assets (Intangible)'),
        'investment': ('Non-Current Assets', 'Non-Current Investments'),
        'depreciation': ('Non-Current Assets', 'Accumulated Depreciation'),

        # Current assets
        'sundry debtor': ('Current Assets', 'Trade Receivables'),
        'trade receivable': ('Current Assets', 'Trade Receivables'),
        'debtor': ('Current Assets', 'Trade Receivables'),
        'receivable': ('Current Assets', 'Trade Receivables'),
        'cash': ('Current Assets', 'Cash & Bank Balances'),
        'bank': ('Current Assets', 'Cash & Bank Balances'),
        'deposit': ('Current Assets', 'Short Term Loans & Advances'),
        'advance': ('Current Assets', 'Short Term Loans & Advances'),
        'prepaid': ('Current Assets', 'Short Term Loans & Advances'),
        'tds receivable': ('Current Assets', 'Short Term Loans & Advances'),
        'input credit': ('Current Assets', 'Short Term Loans & Advances'),
        'gst input': ('Current Assets', 'Short Term Loans & Advances'),
        'inventory': ('Current Assets', 'Inventories'),
        'stock': ('Current Assets', 'Inventories'),
        'closing stock': ('Current Assets', 'Inventories'),

        # Income (P&L)
        'sales': ('Income', 'Revenue from Operations'),
        'revenue': ('Income', 'Revenue from Operations'),
        'income': ('Income', 'Other Income'),
        'interest income': ('Income', 'Other Income'),
        'dividend income': ('Income', 'Other Income'),
        'rent income': ('Income', 'Other Income'),
        'commission income': ('Income', 'Other Income'),
        'discount received': ('Income', 'Other Income'),
        'profit on sale': ('Income', 'Other Income'),

        # Expenses (P&L)
        'purchase': ('Expenses', 'Purchases'),
        'opening stock': ('Expenses', 'Changes in Inventories'),
        'salary': ('Expenses', 'Employee Benefit Expenses'),
        'wages': ('Expenses', 'Employee Benefit Expenses'),
        'employee': ('Expenses', 'Employee Benefit Expenses'),
        'rent': ('Expenses', 'Other Expenses'),
        'electricity': ('Expenses', 'Other Expenses'),
        'telephone': ('Expenses', 'Other Expenses'),
        'repair': ('Expenses', 'Other Expenses'),
        'maintenance': ('Expenses', 'Other Expenses'),
        'insurance': ('Expenses', 'Other Expenses'),
        'professional fee': ('Expenses', 'Other Expenses'),
        'legal fee': ('Expenses', 'Other Expenses'),
        'audit fee': ('Expenses', 'Other Expenses'),
        'advertising': ('Expenses', 'Other Expenses'),
        'travel': ('Expenses', 'Other Expenses'),
        'printing': ('Expenses', 'Other Expenses'),
        'interest expense': ('Expenses', 'Finance Costs'),
        'interest paid': ('Expenses', 'Finance Costs'),
        'bank charge': ('Expenses', 'Finance Costs'),
        'depreciation': ('Expenses', 'Depreciation & Amortization'),
    }

    accounts = tb_data.get("accounts", [])
    mapped = []

    for acc in accounts:
        name = acc.get("account_name", "").strip()
        group = acc.get("group", "")
        debit = acc.get("debit", 0) or 0
        credit = acc.get("credit", 0) or 0

        # Try to classify
        category, head = _classify_account(name, group, ACCOUNT_MAP)

        mapped.append({
            "account_name": name,
            "group": group,
            "debit": debit,
            "credit": credit,
            "bs_category": category,
            "bs_head": head,
        })

    # Build BS structure
    bs = _build_balance_sheet(mapped, prev_bs)
    pl = _build_profit_loss(mapped)

    return {
        "balance_sheet": bs,
        "profit_and_loss": pl,
        "mapped_accounts": mapped,
        "unmapped_count": sum(1 for m in mapped if m["bs_head"] == "Unclassified"),
    }


def _classify_account(name: str, group: str, account_map: Dict) -> tuple:
    """Classify an account name into BS/PL category and head."""
    search_text = (name + " " + group).lower()

    # Try exact group mapping first (from Tally)
    for keyword, (category, head) in account_map.items():
        if keyword in search_text:
            return (category, head)

    # Default: put in Unclassified
    return ("Unclassified", "Unclassified")


def _build_balance_sheet(mapped: List[Dict], prev_bs: Optional[Dict] = None) -> Dict:
    """Build Schedule III Balance Sheet from mapped accounts."""
    bs = {
        "equity_and_liabilities": {},
        "assets": {},
    }

    # Aggregate by BS head
    for acc in mapped:
        cat = acc["bs_category"]
        head = acc["bs_head"]
        amount = acc["credit"] - acc["debit"]  # Credit balance = positive for liabilities/equity

        if cat in ("Equity", "Non-Current Liabilities", "Current Liabilities"):
            if head not in bs["equity_and_liabilities"]:
                bs["equity_and_liabilities"][head] = 0
            bs["equity_and_liabilities"][head] += amount
        elif cat in ("Non-Current Assets", "Current Assets"):
            debit_balance = acc["debit"] - acc["credit"]  # Debit balance = positive for assets
            if head not in bs["assets"]:
                bs["assets"][head] = 0
            bs["assets"][head] += debit_balance

    return bs


def _build_profit_loss(mapped: List[Dict]) -> Dict:
    """Build Profit & Loss statement from mapped accounts."""
    pl = {
        "income": {},
        "expenses": {},
    }

    for acc in mapped:
        cat = acc["bs_category"]
        head = acc["bs_head"]

        if cat == "Income":
            amount = acc["credit"] - acc["debit"]
            if head not in pl["income"]:
                pl["income"][head] = 0
            pl["income"][head] += amount
        elif cat == "Expenses":
            amount = acc["debit"] - acc["credit"]
            if head not in pl["expenses"]:
                pl["expenses"][head] = 0
            pl["expenses"][head] += amount

    total_income = sum(pl["income"].values())
    total_expenses = sum(pl["expenses"].values())
    pl["net_profit"] = total_income - total_expenses

    return pl


def _parse_amount(s: str) -> float:
    """Parse Indian formatted amount."""
    if not s:
        return 0
    try:
        cleaned = re.sub(r'[^\d.\-]', '', s.replace(",", ""))
        return round(float(cleaned), 2) if cleaned else 0
    except (ValueError, TypeError):
        return 0
