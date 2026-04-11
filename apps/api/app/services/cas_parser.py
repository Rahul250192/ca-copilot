"""
Rule-Based CAS (Consolidated Account Statement) Parser
───────────────────────────────────────────────────────
Parses CAMS/KFintech CAS markdown output from LlamaParse
without any AI calls. Used as fallback when both Claude and Gemini are unavailable.

Handles:
- Portfolio Summary table
- Fund-wise folio sections
- Transaction rows (Date, Type, Amount, Units, NAV, Balance)
- Journal entry generation (Purchase/Redemption → Dr/Cr)
"""

import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def parse_cas_markdown(raw_text: str) -> Dict[str, Any]:
    """
    Parse CAS markdown text into structured data.
    Returns: { "portfolio_summary": [...], "transactions": [...], "folios": [...] }
    """
    result = {
        "portfolio_summary": [],
        "transactions": [],
        "folios": [],
        "investor_name": "",
        "statement_period": "",
    }

    lines = raw_text.split("\n")

    # Extract investor name (usually first bold line or entity name)
    for line in lines[:10]:
        clean = line.strip().replace("**", "")
        if clean and not clean.startswith("Email") and not clean.startswith("Mobile") and not clean.startswith("This") and len(clean) > 5:
            if not any(kw in clean.lower() for kw in ["email", "mobile", "consolidated", "investor", "http"]):
                result["investor_name"] = clean
                break

    # Parse portfolio summary table
    result["portfolio_summary"] = _parse_portfolio_summary(raw_text)

    # Also create 'funds' alias for dashboard compatibility
    # Dashboard reads: d.holdings || d.funds → [{market_value, name/fund_name}]
    result["funds"] = [
        {
            "fund_name": f["fund_house"],
            "name": f["fund_house"],
            "market_value": f["market_value"],
            "cost_value": f["cost_value"],
            "current_value": f["market_value"],
        }
        for f in result["portfolio_summary"]
    ]

    # Parse fund sections and transactions
    fund_sections = _split_fund_sections(raw_text)
    for fund_name, section_text in fund_sections:
        folios = _parse_folio_section(section_text, fund_name)
        result["folios"].extend(folios)
        for folio in folios:
            result["transactions"].extend(folio.get("transactions", []))

    logger.info(f"CAS Parser: {len(result['portfolio_summary'])} funds, "
                f"{len(result['folios'])} folios, "
                f"{len(result['transactions'])} transactions")

    return result


def _parse_portfolio_summary(text: str) -> List[Dict]:
    """Extract Portfolio Summary table."""
    summary = []
    in_summary = False
    header_found = False

    for line in text.split("\n"):
        stripped = line.strip()

        if "PORTFOLIO SUMMARY" in stripped.upper():
            in_summary = True
            continue

        if in_summary:
            # Skip table borders and headers
            if stripped.startswith("| --") or stripped.startswith("|--"):
                header_found = True
                continue
            if "Mutual Fund" in stripped and "Cost Value" in stripped:
                header_found = True
                continue

            if header_found and stripped.startswith("|") and "Total" not in stripped:
                cols = [c.strip() for c in stripped.split("|") if c.strip()]
                if len(cols) >= 3:
                    fund_name = cols[0].strip()
                    cost_val = _parse_amount(cols[1])
                    market_val = _parse_amount(cols[2])
                    if fund_name and cost_val > 0:
                        summary.append({
                            "fund_house": fund_name,
                            "cost_value": cost_val,
                            "market_value": market_val,
                        })

            # Stop at Total row or next section
            if header_found and ("Total" in stripped or (stripped.startswith("#") and "PORTFOLIO" not in stripped.upper())):
                break

    return summary


def _split_fund_sections(text: str) -> List[tuple]:
    """Split text into fund house sections based on ### headers."""
    sections = []
    # Match ### Fund Name headers
    pattern = re.compile(r'^###\s+(.+?)$', re.MULTILINE)
    matches = list(pattern.finditer(text))

    for i, match in enumerate(matches):
        fund_name = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end]
        sections.append((fund_name, section_text))

    return sections


def _parse_folio_section(section_text: str, fund_name: str) -> List[Dict]:
    """Parse folio details and transactions from a fund section."""
    folios = []
    current_folio = None
    current_scheme = None

    for line in section_text.split("\n"):
        stripped = line.strip()

        # Look for folio info in table cells or standalone text
        folio_match = re.search(r'Folio\s+No[:\s]*(\d[\d/\s]*\d)', stripped, re.IGNORECASE)
        if folio_match:
            folio_no = folio_match.group(1).strip()
            # Extract scheme name and ISIN
            scheme_match = re.search(r'(\w{3,}[\w\s-]+)\s*-\s*ISIN:\s*(\w+)', stripped)
            scheme_name = scheme_match.group(1).strip() if scheme_match else ""
            isin = scheme_match.group(2).strip() if scheme_match else ""

            # Also try to get scheme from format like "128MCDGG-Scheme Name - Direct Growth"
            if not scheme_name:
                scheme_match2 = re.search(r'\w+-(.+?)(?:\s*-\s*ISIN|\s*$)', stripped)
                if scheme_match2:
                    scheme_name = scheme_match2.group(1).strip()

            current_folio = {
                "folio_no": folio_no,
                "fund_house": fund_name,
                "scheme_name": scheme_name,
                "isin": isin,
                "transactions": [],
            }
            current_scheme = scheme_name
            folios.append(current_folio)
            continue

        # Parse transaction rows: | Date | Transaction | Amount | Units | Price | Balance |
        if stripped.startswith("|") and current_folio is not None:
            cols = [c.strip() for c in stripped.split("|") if c.strip()]
            if len(cols) >= 4:
                # Try to parse date
                date = _parse_date(cols[0])
                if date:
                    txn = {
                        "date": date,
                        "description": cols[1] if len(cols) > 1 else "",
                        "amount": _parse_amount(cols[2]) if len(cols) > 2 else 0,
                        "units": _parse_float(cols[3]) if len(cols) > 3 else 0,
                        "nav": _parse_float(cols[4]) if len(cols) > 4 else 0,
                        "balance": _parse_float(cols[5]) if len(cols) > 5 else 0,
                        "fund_house": fund_name,
                        "scheme_name": current_scheme or "",
                        "folio_no": current_folio.get("folio_no", ""),
                    }

                    # Determine transaction type
                    desc_lower = txn["description"].lower()
                    # Normalize spaces: "S T P" → "stp", "S I P" → "sip"
                    desc_normalized = re.sub(r'(?<=\b\w)\s(?=\w\b)', '', desc_lower)
                    if any(kw in desc_lower for kw in ["purchase", "sip", "systematic investment", "additional"]) or "s i p" in desc_lower:
                        txn["type"] = "Purchase"
                    elif any(kw in desc_lower for kw in ["redemption", "redeem", "withdrawal"]):
                        txn["type"] = "Redemption"
                    elif any(kw in desc_lower for kw in ["switch in", "switchin", "s t p in", "stp in"]) or "stpin" in desc_normalized:
                        txn["type"] = "Switch In"
                    elif any(kw in desc_lower for kw in ["switch out", "switchout", "s t p out", "stp out"]) or "stpout" in desc_normalized:
                        txn["type"] = "Switch Out"
                    elif any(kw in desc_lower for kw in ["dividend", "idcw", "payout"]):
                        txn["type"] = "Dividend"
                    elif any(kw in desc_lower for kw in ["stamp duty"]):
                        txn["type"] = "Stamp Duty"
                    else:
                        txn["type"] = "Purchase"  # Default to Purchase for unrecognized

                    current_folio["transactions"].append(txn)

    return folios


def generate_journal_entries_from_parsed(parsed_data: Dict) -> List[Dict]:
    """
    Generate Tally-ready journal entries from parsed CAS data.
    No AI needed — pure rule-based accounting logic.
    """
    entries = []

    for txn in parsed_data.get("transactions", []):
        amount = abs(txn.get("amount", 0))
        if amount < 0.01:
            continue

        scheme = txn.get("scheme_name", "Unknown Fund")
        fund_house = txn.get("fund_house", "")
        date = txn.get("date", "")
        txn_type = txn.get("type", "Other")
        desc = txn.get("description", "")
        units = txn.get("units", 0)
        nav = txn.get("nav", 0)

        narration = f"{desc} | {scheme} | {units} units @ ₹{nav}" if units else desc

        if txn_type == "Purchase":
            entries.append({
                "date": date,
                "voucher_type": "Purchase",
                "narration": narration,
                "ledger_entries": [
                    {"ledger": f"{scheme} - {fund_house}", "side": "Dr", "amount": amount},
                    {"ledger": "Bank Account", "side": "Cr", "amount": amount},
                ]
            })
        elif txn_type == "Redemption":
            entries.append({
                "date": date,
                "voucher_type": "Receipt",
                "narration": narration,
                "ledger_entries": [
                    {"ledger": "Bank Account", "side": "Dr", "amount": amount},
                    {"ledger": f"{scheme} - {fund_house}", "side": "Cr", "amount": amount},
                ]
            })
        elif txn_type == "Dividend":
            entries.append({
                "date": date,
                "voucher_type": "Receipt",
                "narration": narration,
                "ledger_entries": [
                    {"ledger": "Bank Account", "side": "Dr", "amount": amount},
                    {"ledger": f"Dividend Income - {scheme}", "side": "Cr", "amount": amount},
                ]
            })
        elif txn_type in ("Switch In", "Switch Out"):
            # Switch doesn't involve bank — it's fund-to-fund
            entries.append({
                "date": date,
                "voucher_type": "Journal",
                "narration": narration,
                "ledger_entries": [
                    {"ledger": f"{scheme} - {fund_house}", "side": "Dr" if txn_type == "Switch In" else "Cr", "amount": amount},
                    {"ledger": f"Mutual Fund Switch A/c", "side": "Cr" if txn_type == "Switch In" else "Dr", "amount": amount},
                ]
            })
        elif txn_type == "Stamp Duty":
            entries.append({
                "date": date,
                "voucher_type": "Payment",
                "narration": narration,
                "ledger_entries": [
                    {"ledger": "Stamp Duty Expense", "side": "Dr", "amount": amount},
                    {"ledger": "Bank Account", "side": "Cr", "amount": amount},
                ]
            })
        else:
            # Default: treat as Purchase
            entries.append({
                "date": date,
                "voucher_type": "Journal",
                "narration": narration,
                "ledger_entries": [
                    {"ledger": f"{scheme} - {fund_house}", "side": "Dr", "amount": amount},
                    {"ledger": "Bank Account", "side": "Cr", "amount": amount},
                ]
            })

    logger.info(f"CAS Parser: Generated {len(entries)} journal entries (rule-based)")
    return entries


# ─── Utility functions ────────────────────────────────

def _parse_amount(s: str) -> float:
    """Parse Indian formatted amount: 11,998,855.80 → 11998855.80"""
    if not s:
        return 0
    try:
        cleaned = re.sub(r'[^\d.\-]', '', s.replace(",", ""))
        return round(float(cleaned), 2) if cleaned else 0
    except (ValueError, TypeError):
        return 0


def _parse_float(s: str) -> float:
    """Parse a float from string."""
    if not s:
        return 0
    try:
        cleaned = re.sub(r'[^\d.\-]', '', s.replace(",", ""))
        return round(float(cleaned), 4) if cleaned else 0
    except (ValueError, TypeError):
        return 0


def _parse_date(s: str) -> Optional[str]:
    """Parse various date formats into DD-MMM-YYYY."""
    if not s or len(s) < 6:
        return None

    s = s.strip()

    # Try common CAS date formats
    for fmt in ["%d-%b-%Y", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d-%B-%Y"]:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%d-%b-%Y")
        except ValueError:
            continue

    return None
