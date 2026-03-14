"""
GST Refund Calculator — Rule 89(4), 89(5), 96, and Excess Cash Ledger

Implements the official CBIC formulas for computing maximum admissible refund:

  Rule 89(4) — Export / Deemed Export without IGST (LUT):
    Max Refund = (Turnover of Zero-Rated Supply ÷ Adjusted Total Turnover) × Net ITC

  Rule 89(5) — Inverted Duty Structure:
    Max Refund = [(Turnover of Inverted Rated Supply × Net ITC) ÷ Adjusted Total Turnover]
                 − Tax Payable on Inverted Rated Supply

  Rule 96 — Export with IGST Payment:
    Refund = IGST paid on exports (auto via shipping bill scroll)

  Excess Cash Ledger:
    Refund = Excess balance in Electronic Cash Ledger

Reference:
  - CGST Rules 2017, Rules 89 & 96
  - Circular 135/05/2020-GST (IDS formula clarification)
  - Circular 147/03/2021-GST (Net ITC definition)
"""

import logging
from typing import Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class RefundType(str, Enum):
    EXPORT_GOODS_LUT = "export_goods_lut"
    EXPORT_SERVICE_LUT = "export_service_lut"
    EXPORT_IGST = "export_igst"
    INVERTED_DUTY = "inverted_duty"
    DEEMED_EXPORT = "deemed_export"
    EXCESS_CASH = "excess_cash"


def calculate_refund(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Main entry point. Routes to the correct formula based on refund_type.
    Returns a structured result with breakdown, formula, and warnings.
    """
    refund_type = data.get("refund_type", "")
    logger.info(f"Calculating refund for type: {refund_type}")

    if refund_type in (RefundType.EXPORT_GOODS_LUT, RefundType.EXPORT_SERVICE_LUT, RefundType.DEEMED_EXPORT):
        return _calculate_rule_89_4(data)
    elif refund_type == RefundType.INVERTED_DUTY:
        return _calculate_rule_89_5(data)
    elif refund_type == RefundType.EXPORT_IGST:
        return _calculate_rule_96(data)
    elif refund_type == RefundType.EXCESS_CASH:
        return _calculate_excess_cash(data)
    else:
        return {"error": f"Unknown refund type: {refund_type}", "max_refund": 0}


def _calculate_rule_89_4(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rule 89(4) — Export of Goods/Services under LUT / Deemed Exports

    Formula:
      Max Refund = (Turnover of Zero-Rated Supply of Goods + Services)
                   ÷ Adjusted Total Turnover
                   × Net ITC

    Where:
      Adjusted Total Turnover = Total Turnover − Exempt Turnover (excl. zero-rated)
      Net ITC = ITC Availed − ITC on Capital Goods − Blocked Credit u/s 17(5) − ITC on Input Services (for goods only)

    For services, Net ITC includes input services.
    """
    refund_type = data.get("refund_type", "")

    # ─── Input Values ───
    turnover_zero_rated_goods = float(data.get("turnover_zero_rated_goods", 0))
    turnover_zero_rated_services = float(data.get("turnover_zero_rated_services", 0))
    turnover_zero_rated = turnover_zero_rated_goods + turnover_zero_rated_services

    total_turnover = float(data.get("total_turnover", 0))
    exempt_turnover = float(data.get("exempt_turnover", 0))  # Excluding zero-rated

    itc_availed = float(data.get("itc_availed", 0))  # Total ITC for the period
    itc_capital_goods = float(data.get("itc_capital_goods", 0))
    blocked_credit = float(data.get("blocked_credit", 0))  # u/s 17(5)
    itc_input_services = float(data.get("itc_input_services", 0))  # For goods-only claims

    # ─── Compute ───
    adjusted_total_turnover = total_turnover - exempt_turnover
    if adjusted_total_turnover <= 0:
        return {
            "error": "Adjusted Total Turnover must be positive. Check exempt turnover.",
            "max_refund": 0,
        }

    # Net ITC calculation
    # For Export of Goods: exclude ITC on input services (per Circular 135)
    # For Export of Services / Deemed: include input services
    if refund_type == RefundType.EXPORT_GOODS_LUT:
        net_itc = itc_availed - itc_capital_goods - blocked_credit - itc_input_services
        net_itc_note = "Net ITC = ITC Availed − Capital Goods ITC − Blocked Credit − Input Services ITC"
    else:
        net_itc = itc_availed - itc_capital_goods - blocked_credit
        net_itc_note = "Net ITC = ITC Availed − Capital Goods ITC − Blocked Credit"

    if net_itc < 0:
        net_itc = 0

    # Formula
    ratio = turnover_zero_rated / adjusted_total_turnover
    max_refund = round(ratio * net_itc, 2)

    # ─── Warnings ───
    warnings = []
    if turnover_zero_rated > adjusted_total_turnover:
        warnings.append("Zero-rated turnover exceeds adjusted total turnover. Please verify.")
    if itc_capital_goods > itc_availed * 0.5:
        warnings.append("Capital goods ITC is unusually high (>50% of total ITC).")
    if ratio > 1:
        warnings.append("Ratio exceeds 1.0. Max refund capped to Net ITC.")
        max_refund = min(max_refund, net_itc)
    if blocked_credit > 0:
        warnings.append(f"₹{blocked_credit:,.2f} of blocked credit u/s 17(5) has been excluded.")

    type_label = {
        RefundType.EXPORT_GOODS_LUT: "Export of Goods (LUT)",
        RefundType.EXPORT_SERVICE_LUT: "Export of Services (LUT)",
        RefundType.DEEMED_EXPORT: "Deemed Exports",
    }.get(refund_type, "Export/Deemed")

    return {
        "refund_type": refund_type,
        "type_label": type_label,
        "rule": "Rule 89(4)",
        "max_refund": max_refund,
        "formula": f"({turnover_zero_rated:,.2f} ÷ {adjusted_total_turnover:,.2f}) × {net_itc:,.2f} = ₹{max_refund:,.2f}",
        "formula_display": "(Zero-Rated Turnover ÷ Adjusted Total Turnover) × Net ITC",
        "breakdown": {
            "turnover_zero_rated_goods": turnover_zero_rated_goods,
            "turnover_zero_rated_services": turnover_zero_rated_services,
            "turnover_zero_rated": turnover_zero_rated,
            "total_turnover": total_turnover,
            "exempt_turnover": exempt_turnover,
            "adjusted_total_turnover": adjusted_total_turnover,
            "itc_availed": itc_availed,
            "itc_capital_goods": itc_capital_goods,
            "blocked_credit": blocked_credit,
            "itc_input_services": itc_input_services,
            "net_itc": net_itc,
            "net_itc_note": net_itc_note,
            "ratio": round(ratio, 6),
        },
        "warnings": warnings,
    }


def _calculate_rule_89_5(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rule 89(5) — Inverted Duty Structure

    Formula (post Circular 135):
      Max Refund = [(Turnover of Inverted Rated Supply × Net ITC)
                    ÷ Adjusted Total Turnover]
                   − Tax Payable on Inverted Rated Supply

    Where:
      Net ITC = ITC availed on inputs and input services
                − ITC on Capital Goods
                − Blocked ITC u/s 17(5)
      Tax Payable = Output tax on inverted rated supplies
      Adjusted Total Turnover = Total turnover − exempt turnover

    Important:
      - Only goods eligible (services excluded from IDS refund per Section 54(3) proviso)
      - Tobacco, pan masala, etc. excluded by notification
    """
    turnover_inverted = float(data.get("turnover_inverted", 0))
    total_turnover = float(data.get("total_turnover", 0))
    exempt_turnover = float(data.get("exempt_turnover", 0))

    itc_availed = float(data.get("itc_availed", 0))
    itc_capital_goods = float(data.get("itc_capital_goods", 0))
    blocked_credit = float(data.get("blocked_credit", 0))

    tax_payable_inverted = float(data.get("tax_payable_inverted", 0))  # Output tax on inverted supply

    # ─── Compute ───
    adjusted_total_turnover = total_turnover - exempt_turnover
    if adjusted_total_turnover <= 0:
        return {
            "error": "Adjusted Total Turnover must be positive.",
            "max_refund": 0,
        }

    net_itc = itc_availed - itc_capital_goods - blocked_credit
    if net_itc < 0:
        net_itc = 0

    part_a = (turnover_inverted * net_itc) / adjusted_total_turnover
    max_refund = round(part_a - tax_payable_inverted, 2)

    if max_refund < 0:
        max_refund = 0

    # ─── Warnings ───
    warnings = []
    if part_a <= tax_payable_inverted:
        warnings.append("No refund arises — tax on output exceeds proportional ITC.")
    if turnover_inverted > adjusted_total_turnover:
        warnings.append("Inverted turnover exceeds adjusted total turnover. Please verify.")
    if blocked_credit > 0:
        warnings.append(f"₹{blocked_credit:,.2f} of blocked credit u/s 17(5) excluded from Net ITC.")

    return {
        "refund_type": RefundType.INVERTED_DUTY,
        "type_label": "Inverted Duty Structure",
        "rule": "Rule 89(5)",
        "max_refund": max_refund,
        "formula": f"[({turnover_inverted:,.2f} × {net_itc:,.2f}) ÷ {adjusted_total_turnover:,.2f}] − {tax_payable_inverted:,.2f} = ₹{max_refund:,.2f}",
        "formula_display": "[(Inverted Turnover × Net ITC) ÷ Adjusted Total Turnover] − Tax Payable on Inverted Supply",
        "breakdown": {
            "turnover_inverted": turnover_inverted,
            "total_turnover": total_turnover,
            "exempt_turnover": exempt_turnover,
            "adjusted_total_turnover": adjusted_total_turnover,
            "itc_availed": itc_availed,
            "itc_capital_goods": itc_capital_goods,
            "blocked_credit": blocked_credit,
            "net_itc": net_itc,
            "part_a": round(part_a, 2),
            "tax_payable_inverted": tax_payable_inverted,
        },
        "warnings": warnings,
    }


def _calculate_rule_96(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Rule 96 — Export with IGST Payment

    IGST refund on exports is auto-processed via ICEGATE shipping bill matching.
    This calculator shows the total IGST paid and expected refund.
    """
    igst_paid_on_exports = float(data.get("igst_paid_on_exports", 0))
    igst_paid_on_services = float(data.get("igst_paid_on_services", 0))
    total_igst = igst_paid_on_exports + igst_paid_on_services

    shipping_bills_matched = int(data.get("shipping_bills_matched", 0))
    shipping_bills_total = int(data.get("shipping_bills_total", 0))
    withheld_amount = float(data.get("withheld_amount", 0))  # If risky exporter flag

    expected_refund = round(total_igst - withheld_amount, 2)
    if expected_refund < 0:
        expected_refund = 0

    warnings = []
    if shipping_bills_total > 0 and shipping_bills_matched < shipping_bills_total:
        unmatched = shipping_bills_total - shipping_bills_matched
        warnings.append(f"{unmatched} shipping bill(s) not matched on ICEGATE. These will be withheld.")
    if withheld_amount > 0:
        warnings.append(f"₹{withheld_amount:,.2f} withheld (risky exporter / mismatch).")

    return {
        "refund_type": RefundType.EXPORT_IGST,
        "type_label": "Export with IGST Payment",
        "rule": "Rule 96",
        "max_refund": expected_refund,
        "formula": f"IGST ₹{total_igst:,.2f} − Withheld ₹{withheld_amount:,.2f} = ₹{expected_refund:,.2f}",
        "formula_display": "IGST Paid on Exports − Withheld Amount",
        "breakdown": {
            "igst_paid_on_exports": igst_paid_on_exports,
            "igst_paid_on_services": igst_paid_on_services,
            "total_igst": total_igst,
            "shipping_bills_matched": shipping_bills_matched,
            "shipping_bills_total": shipping_bills_total,
            "withheld_amount": withheld_amount,
        },
        "note": "IGST refund on exports is auto-processed by Customs via ICEGATE. No RFD-01 needed.",
        "warnings": warnings,
    }


def _calculate_excess_cash(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Excess Balance in Electronic Cash Ledger — Direct refund.
    """
    cash_ledger_balance = float(data.get("cash_ledger_balance", 0))
    amount_earmarked = float(data.get("amount_earmarked", 0))  # Against demands
    refund_amount = float(data.get("refund_amount", 0))  # Amount user wants to claim

    available = round(cash_ledger_balance - amount_earmarked, 2)
    if available < 0:
        available = 0

    if refund_amount <= 0 or refund_amount > available:
        refund_amount = available

    warnings = []
    if amount_earmarked > 0:
        warnings.append(f"₹{amount_earmarked:,.2f} is earmarked against demand/recovery — not refundable.")

    return {
        "refund_type": RefundType.EXCESS_CASH,
        "type_label": "Excess Cash Ledger Balance",
        "rule": "Direct Refund",
        "max_refund": round(refund_amount, 2),
        "formula": f"Balance ₹{cash_ledger_balance:,.2f} − Earmarked ₹{amount_earmarked:,.2f} = Available ₹{available:,.2f}",
        "formula_display": "Cash Ledger Balance − Earmarked Amount",
        "breakdown": {
            "cash_ledger_balance": cash_ledger_balance,
            "amount_earmarked": amount_earmarked,
            "available_for_refund": available,
            "claim_amount": refund_amount,
        },
        "note": "Fastest refund type — usually processed within 2 weeks with no officer adjudication.",
        "warnings": warnings,
    }
