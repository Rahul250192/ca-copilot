# gst_master.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional, Tuple

import pandas as pd


_DIGITS_ONLY = re.compile(r"^\d+$")


@dataclass(frozen=True)
class GstRate:
    cgst: float
    sgst: float
    igst: float
    cess: float
    match_level: str           # "exact" | "8" | "6" | "4" | "2" | "sac"
    matched_code: str
    source_sheet: str


def _safe_float(x) -> float:
    if x is None:
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if not s or s in {"—", "-", "NA", "N/A", "nil", "Nil"}:
        return 0.0
    s = s.replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _normalize_code(code: str) -> str:
    code = (code or "").strip()
    if not code:
        raise ValueError("code is required")
    # allow things like "0507", "050790", "9983"
    if not _DIGITS_ONLY.match(code):
        raise ValueError("code must be numeric (digits only)")
    return code


def _build_goods_maps(xlsx_path: str) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Returns:
      - gst_map: HSN/Heading -> IGST percent (total GST percent)
      - cess_map: HSN/Heading -> cess percent (if known; else 0)
    Notes:
      Your master file may have multiple goods sheets. We try common sheet names and columns.
    """
    xl = pd.ExcelFile(xlsx_path)

    # Candidate sheets in your master (adjust if you renamed)
    goods_sheets = [s for s in xl.sheet_names if "GOODS" in s.upper()]
    if not goods_sheets:
        # fallback: just try first sheet
        goods_sheets = [xl.sheet_names[0]]

    gst_map: Dict[str, float] = {}
    cess_map: Dict[str, float] = {}

    def ingest_sheet(sheet: str):
        df = xl.parse(sheet_name=sheet)
        df.columns = [str(c).strip() for c in df.columns]

        # Heuristics for columns
        # Many tables have something like "HSN" / "HSN/Code" / "HSN Code" / "Tariff item" etc.
        code_col = None
        for c in df.columns:
            cu = c.upper()
            if "HSN" in cu and ("CODE" in cu or "/" in c or cu.endswith("HSN")):
                code_col = c
                break
            if cu in {"HSN", "HSN CODE", "HSN/ CODE", "HSN/Code".upper(), "HSN/Code"}:
                code_col = c
                break
        if code_col is None:
            # fallback: first column
            code_col = df.columns[0]

        # Rate column: could be "IGST", "GST Rate", "Rate", etc.
        rate_col = None
        for c in df.columns:
            cu = c.upper()
            if cu in {"IGST", "IGST %", "IGST RATE", "GST", "GST RATE", "RATE"}:
                rate_col = c
                break
            if "IGST" in cu:
                rate_col = c
                break
            if "GST" in cu and "RATE" in cu:
                rate_col = c
                break
        if rate_col is None:
            # If the sheet is "9/2025 schedule" style, it may store CGST only.
            # Try "CGST" and double it.
            cgst_col = None
            for c in df.columns:
                if "CGST" in c.upper():
                    cgst_col = c
                    break
            if cgst_col is not None:
                # We'll treat total GST = 2 * CGST
                df["_TOTAL_GST_"] = df[cgst_col].apply(_safe_float) * 2.0
                rate_col = "_TOTAL_GST_"
            else:
                raise ValueError(f"Cannot detect GST rate column in sheet '{sheet}'")

        # Cess column optional
        cess_col = None
        for c in df.columns:
            if "CESS" in c.upper():
                cess_col = c
                break

        for _, row in df.iterrows():
            raw_code = row.get(code_col)
            if pd.isna(raw_code):
                continue
            # Many schedules have codes like "0202, 0203" or "1000–1008"
            # For API lookup we support exact digit-prefix matching; we only store digit tokens here.
            tokens = re.findall(r"\d{2,8}", str(raw_code))
            if not tokens:
                continue

            gst_rate = _safe_float(row.get(rate_col))
            cess_rate = _safe_float(row.get(cess_col)) if cess_col else 0.0

            for t in tokens:
                # Store only if numeric token
                if _DIGITS_ONLY.match(t):
                    gst_map[t] = gst_rate
                    if cess_rate:
                        cess_map[t] = cess_rate

    for s in goods_sheets:
        try:
            ingest_sheet(s)
        except Exception:
            # continue; some GOODS sheets may be metadata/history
            continue

    return gst_map, cess_map


def _build_services_map(xlsx_path: str) -> Dict[str, float]:
    """
    Returns SAC -> IGST percent (total GST percent)
    We keep it simple: SAC is typically 4-6 digits (often 4-digit group).
    """
    xl = pd.ExcelFile(xlsx_path)
    service_sheets = [s for s in xl.sheet_names if "SERVICE" in s.upper() or "SAC" in s.upper()]
    if not service_sheets:
        return {}

    sac_map: Dict[str, float] = {}

    def ingest_sheet(sheet: str):
        df = xl.parse(sheet_name=sheet)
        df.columns = [str(c).strip() for c in df.columns]

        code_col = None
        for c in df.columns:
            cu = c.upper()
            if "SAC" in cu:
                code_col = c
                break
        if code_col is None:
            return

        rate_col = None
        for c in df.columns:
            cu = c.upper()
            if "IGST" in cu:
                rate_col = c
                break
            if cu in {"GST", "GST RATE", "RATE"}:
                rate_col = c
                break
        if rate_col is None:
            # Try CGST then double
            cgst_col = None
            for c in df.columns:
                if "CGST" in c.upper():
                    cgst_col = c
                    break
            if cgst_col is not None:
                df["_TOTAL_GST_"] = df[cgst_col].apply(_safe_float) * 2.0
                rate_col = "_TOTAL_GST_"
            else:
                return

        for _, row in df.iterrows():
            raw_code = row.get(code_col)
            if pd.isna(raw_code):
                continue
            tokens = re.findall(r"\d{4,6}", str(raw_code))
            if not tokens:
                continue
            gst_rate = _safe_float(row.get(rate_col))
            for t in tokens:
                sac_map[t] = gst_rate

    for s in service_sheets:
        try:
            ingest_sheet(s)
        except Exception:
            continue

    return sac_map


@lru_cache(maxsize=1)
def load_master(xlsx_path: str) -> Dict[str, object]:
    if not os.path.exists(xlsx_path):
        raise FileNotFoundError(f"GST master file not found: {xlsx_path}")

    goods_map, cess_map = _build_goods_maps(xlsx_path)
    services_map = _build_services_map(xlsx_path)

    return {
        "goods_map": goods_map,
        "cess_map": cess_map,
        "services_map": services_map,
        "xlsx_path": xlsx_path,
    }


def get_rates(code: str, xlsx_path: str) -> GstRate:
    """
    Main lookup: supports HSN (2/4/6/8 digits) and SAC (4 digits typical).
    Strategy:
      - If length >= 2 and looks like goods: try exact then prefix fallback 8->6->4->2
      - Also try services SAC map (exact, then 4-digit prefix if longer)
    """
    code = _normalize_code(code)
    data = load_master(xlsx_path)

    goods_map: Dict[str, float] = data["goods_map"]
    cess_map: Dict[str, float] = data["cess_map"]
    services_map: Dict[str, float] = data["services_map"]

    # 1) Try services first if SAC-like (usually starts 99 or 4 digits group)
    if len(code) >= 4:
        if code in services_map:
            igst = services_map[code]
            return GstRate(
                cgst=igst / 2.0,
                sgst=igst / 2.0,
                igst=igst,
                cess=0.0,
                match_level="sac",
                matched_code=code,
                source_sheet="SERVICES",
            )
        # try 4-digit group prefix
        sac_prefix = code[:4]
        if sac_prefix in services_map:
            igst = services_map[sac_prefix]
            return GstRate(
                cgst=igst / 2.0,
                sgst=igst / 2.0,
                igst=igst,
                cess=0.0,
                match_level="sac",
                matched_code=sac_prefix,
                source_sheet="SERVICES",
            )

    # 2) Goods HSN fallback: exact then prefix
    candidates = []
    if len(code) >= 8:
        candidates.append((code[:8], "8"))
    if len(code) >= 6:
        candidates.append((code[:6], "6"))
    if len(code) >= 4:
        candidates.append((code[:4], "4"))
    if len(code) >= 2:
        candidates.append((code[:2], "2"))

    # exact full first
    if code in goods_map:
        igst = goods_map[code]
        cess = cess_map.get(code, 0.0)
        return GstRate(
            cgst=igst / 2.0,
            sgst=igst / 2.0,
            igst=igst,
            cess=cess,
            match_level="exact",
            matched_code=code,
            source_sheet="GOODS",
        )

    for c, lvl in candidates:
        if c in goods_map:
            igst = goods_map[c]
            cess = cess_map.get(c, 0.0)
            return GstRate(
                cgst=igst / 2.0,
                sgst=igst / 2.0,
                igst=igst,
                cess=cess,
                match_level=lvl,
                matched_code=c,
                source_sheet="GOODS",
            )

    raise KeyError(f"No GST rate found for code={code}")
