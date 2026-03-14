"""
═══════════════════════════════════════════════════════════════════════════
GST Reconciliation Engine — Firm-Agnostic
═══════════════════════════════════════════════════════════════════════════

Designed to work with ANY CA firm's data, regardless of:
  • Sheet names   (B2B, B2B_Data, B2B Data, Purchases, Sheet1...)
  • Column names  (Invoice No, Inv No., Invoice Number, Bill No, ...)
  • Header position (row 0, 1, 3, 5... — auto-detected)
  • Total rows    (footer sums, grand totals — auto-stripped)
  • Blocked ITC   (ITC Eligible = No rows — separated out)
  • Invoice number formats (HCL/2024/7712, HCL-2024-7712, HCL20247712)
"""

import pandas as pd
import numpy as np
import io
import os
import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from app.models.job import JobType

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# CONSTANTS — Fuzzy matching dictionaries
# ═══════════════════════════════════════════════════════════════

# Sheet names that likely contain invoice data (substring, case-insensitive)
SHEET_POSITIVE = [
    'b2b', 'purchase', 'sales', 'data', 'invoice', 'register',
    'pr', 'sr', 'detail', 'transaction', 'voucher', 'b2ba', 'cdnr',
    'sheet1', 'report',
]

# Sheet names that are definitely NOT invoice data
SHEET_NEGATIVE = [
    'summary', 'overview', 'help', 'readme', 'instruction',
    'cover', 'index', 'metadata', 'info', 'statistic', 'dashboard',
    'template', 'master', 'setting', 'config', 'about',
]

# Column synonyms → standard name mapping
# Each standard name has a list of (keyword_patterns, priority)
# Higher priority wins when multiple columns match the same standard name
COLUMN_SYNONYMS = {
    'gstin': {
        'patterns': [
            ('gstin of supplier', 10),
            ('gstin of buyer', 10),
            ('supplier gstin', 10),
            ('party gstin', 10),
            ('gstin/uin', 10),
            ('gstin', 9),
            ('gst no', 8),
            ('gst_no', 8),
            ('gst number', 8),
            ('uin', 5),
        ],
    },
    'inv_num': {
        'patterns': [
            # HIGH priority — explicit "invoice" keyword
            ('supplier invoice no', 20),
            ('supplier invoice number', 20),
            ('invoice number', 15),
            ('invoice no.', 15),
            ('invoice no', 15),
            ('invoice num', 15),
            ('inv number', 12),
            ('inv no.', 12),
            ('inv no', 12),
            ('document number', 10),
            ('document no', 10),
            ('doc no', 8),
            # LOW priority — fallback only (voucher/bill/ref)
            ('voucher number', 3),
            ('voucher no.', 3),
            ('voucher no', 3),
            ('bill number', 3),
            ('bill no.', 3),
            ('bill no', 3),
            ('ref no', 2),
            ('reference no', 2),
        ],
    },
    'date': {
        'patterns': [
            ('invoice date', 10),
            ('inv date', 10),
            ('document date', 8),
            ('bill date', 7),
            ('voucher date', 6),
            ('date', 3),
        ],
    },
    'taxable': {
        'patterns': [
            ('taxable value', 10),
            ('taxable amount', 10),
            ('taxable amt', 10),
            ('taxable val', 10),
            ('assessable value', 8),
            ('net amount', 5),
            ('base amount', 5),
        ],
    },
    'igst': {
        'patterns': [
            ('integrated tax', 10),
            ('igst amount', 10),
            ('igst amt', 10),
            ('igst', 8),
        ],
    },
    'cgst': {
        'patterns': [
            ('central tax', 10),
            ('cgst amount', 10),
            ('cgst amt', 10),
            ('cgst', 8),
        ],
    },
    'sgst': {
        'patterns': [
            ('state tax', 10),
            ('sgst/utgst', 10),
            ('sgst amount', 10),
            ('sgst amt', 10),
            ('sgst', 8),
            ('utgst', 7),
        ],
    },
    'cess': {
        'patterns': [
            ('cess amount', 10),
            ('cess amt', 10),
            ('cess', 8),
        ],
    },
    'total_tax': {
        'patterns': [
            ('total tax', 10),
            ('tax amount', 8),
            ('total gst', 8),
        ],
    },
    'total_value': {
        'patterns': [
            ('total invoice value', 10),
            ('invoice value', 9),
            ('total value', 8),
            ('gross amount', 7),
            ('gross value', 7),
        ],
    },
    'irn': {
        'patterns': [
            ('irn', 8),
        ],
    },
    'itc_eligible': {
        'patterns': [
            ('itc eligibility', 10),
            ('itc eligible', 10),
            ('eligibility', 8),
            ('itc availability', 8),
            ('itc availed', 7),
            ('block', 5),
        ],
    },
    'supplier_name': {
        'patterns': [
            ('trade name', 10),
            ('supplier name', 10),
            ('party name', 9),
            ('vendor name', 9),
            ('name of supplier', 9),
            ('ledger name', 7),
            ('party', 5),
        ],
    },
}

# Values that indicate a total/summary row (case-insensitive)
TOTAL_ROW_INDICATORS = [
    'total', 'grand total', 'sub total', 'sub-total', 'subtotal',
    'sum', 'net total', 'overall', 'aggregate',
]

# Values that indicate ITC is NOT eligible / blocked
ITC_BLOCKED_VALUES = [
    'no', 'n', 'blocked', 'not eligible', 'ineligible',
    'not available', 'not availed', 'section 17(5)',
]


# ═══════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def reconcile_gst(input_bytes_list: List[bytes], filenames: List[str] = None, job_type: str = "GST_RECON") -> bytes:
    """
    Entry point for all reconciliation jobs.
    input_bytes_list[0] = Source 1 (Portal data: GSTR-2B, IMS, GSTR-1, E-Invoice)
    input_bytes_list[1] = Source 2 (Books data: Purchase Register, Sales Register)
    """
    fn1 = filenames[0] if filenames else "file1.xlsx"
    fn2 = filenames[1] if filenames else "file2.xlsx"
    
    # Load
    df1 = load_reconciliation_file(input_bytes_list[0], fn1)
    df2 = load_reconciliation_file(input_bytes_list[1], fn2)
    
    logger.info(f"━━━ Source 1 ({fn1}): {len(df1)} rows, cols: {list(df1.columns)[:10]}...")
    logger.info(f"━━━ Source 2 ({fn2}): {len(df2)} rows, cols: {list(df2.columns)[:10]}...")
    
    # Identify columns
    cols1 = identify_columns(df1)
    cols2 = identify_columns(df2)
    
    # Standardize
    df1_std = rename_to_standard(df1, cols1)
    df2_std = rename_to_standard(df2, cols2)
    
    # Clean — drop total/summary rows
    df1_std = drop_total_rows(df1_std, "Source 1")
    df2_std = drop_total_rows(df2_std, "Source 2")
    
    # Separate blocked ITC rows (if applicable)
    df1_std, df1_blocked = separate_blocked_itc(df1_std, "Source 1")
    df2_std, df2_blocked = separate_blocked_itc(df2_std, "Source 2")
    
    logger.info(f"━━━ After cleaning → Source 1: {len(df1_std)} rows, Source 2: {len(df2_std)} rows")
    if len(df1_blocked): logger.info(f"    Blocked ITC (Source 1): {len(df1_blocked)} rows")
    if len(df2_blocked): logger.info(f"    Blocked ITC (Source 2): {len(df2_blocked)} rows")
    
    # Match
    result_df = match_data(df1_std, df2_std, job_type)
    
    # Build Excel output
    src1_label, src2_label = get_source_labels(job_type)
    output = generate_excel_report(result_df, df1_std, df2_std, df1_blocked, df2_blocked, src1_label, src2_label)
    return output


def get_source_labels(job_type: str) -> Tuple[str, str]:
    """Return (source1_label, source2_label) based on job type."""
    labels = {
        'gstr2b_vs_pr': ('GSTR-2B', 'Purchase Register'),
        'ims_vs_pr': ('IMS', 'Purchase Register'),
        'einv_vs_sr': ('E-Invoice', 'Sales Register'),
        'gstr1_vs_einv': ('GSTR-1', 'E-Invoice'),
        JobType.GSTR2B_VS_PR: ('GSTR-2B', 'Purchase Register'),
        JobType.IMS_VS_PR: ('IMS', 'Purchase Register'),
        JobType.EINV_VS_SR: ('E-Invoice', 'Sales Register'),
        JobType.GSTR1_VS_EINV: ('GSTR-1', 'E-Invoice'),
    }
    return labels.get(job_type, ('Source 1', 'Source 2'))


# ═══════════════════════════════════════════════════════════════
# SHEET SELECTION — Score-based, scans headers
# ═══════════════════════════════════════════════════════════════

def pick_best_sheet(xls: pd.ExcelFile) -> str:
    """Score each sheet and pick the one most likely to contain invoice data."""
    names = xls.sheet_names
    if len(names) == 1:
        return names[0]
    
    best_name, best_score = names[0], -100
    
    for name in names:
        score = 0
        nl = name.lower().replace(' ', '').replace('-', '').replace('_', '')
        
        # Positive keyword matches (substring)
        for kw in SHEET_POSITIVE:
            if kw.replace('_', '') in nl:
                score += 10
        
        # Negative keyword matches
        for kw in SHEET_NEGATIVE:
            if kw in nl:
                score -= 50
        
        # Bonus: scan first 10 rows of the sheet for invoice-like content
        try:
            df_peek = pd.read_excel(xls, sheet_name=name, header=None, nrows=10)
            header_text = ' '.join(str(v).lower() for row in df_peek.values for v in row if pd.notna(v))
            invoice_keywords = ['gstin', 'invoice', 'taxable', 'igst', 'cgst', 'sgst', 'supplier']
            hits = sum(1 for k in invoice_keywords if k in header_text)
            score += hits * 5
        except Exception:
            pass
        
        if score > best_score:
            best_score = score
            best_name = name
    
    logger.info(f"  Sheet selected: '{best_name}' (score: {best_score}) from {names}")
    return best_name


# ═══════════════════════════════════════════════════════════════
# FILE LOADING — Auto-detect header row
# ═══════════════════════════════════════════════════════════════

def load_reconciliation_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Loads Excel/CSV, finds the best sheet and header row automatically."""
    ext = os.path.splitext(filename)[1].lower()
    
    if ext in ['.xlsx', '.xls']:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        sheet_name = pick_best_sheet(xls)
        logger.info(f"📄 '{filename}' → sheet '{sheet_name}' (all: {xls.sheet_names})")
        
        # Auto-detect header row by scanning up to 30 rows
        df_scan = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=30)
        header_row = find_header_row(df_scan)
        logger.info(f"  Header detected at row {header_row}")
        
        df = pd.read_excel(xls, sheet_name=sheet_name, header=header_row)
        
        # Strip whitespace from column names
        df.columns = [str(c).strip() for c in df.columns]
        
        # Drop completely empty rows
        df = df.dropna(how='all').reset_index(drop=True)
        
        return df
    else:
        # CSV — try common encodings
        for enc in ['utf-8', 'latin1', 'cp1252']:
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding=enc)
                df.columns = [str(c).strip() for c in df.columns]
                return df.dropna(how='all').reset_index(drop=True)
            except Exception:
                continue
        raise ValueError(f"Could not parse CSV file: {filename}")


def find_header_row(df_scan: pd.DataFrame) -> int:
    """
    Finds the header row by scoring each row for "column-name-like" content.
    A good header row has multiple string values that look like column names.
    """
    header_keywords = [
        'gstin', 'invoice', 'date', 'taxable', 'igst', 'cgst', 'sgst', 'cess',
        'supplier', 'customer', 'party', 'voucher', 'bill', 'amount', 'value',
        'number', 'name', 'trade', 'total', 'tax', 'place', 'type', 'no.',
    ]
    
    best_row, best_score = 0, 0
    
    for idx, row in df_scan.iterrows():
        score = 0
        for val in row.values:
            if pd.isna(val):
                continue
            s = str(val).lower().strip()
            # Score: how many header keywords appear in this cell?
            for kw in header_keywords:
                if kw in s:
                    score += 1
            # Bonus for string cells that look like column headers (not numbers, not dates)
            if isinstance(val, str) and len(val) > 2 and not val.replace('.', '').replace(',', '').isdigit():
                score += 0.5
        
        if score > best_score:
            best_score = score
            best_row = idx
    
    return best_row


# ═══════════════════════════════════════════════════════════════
# COLUMN IDENTIFICATION — Priority-scored fuzzy matching
# ═══════════════════════════════════════════════════════════════

def identify_columns(df: pd.DataFrame) -> Dict[str, str]:
    """
    Maps DataFrame columns to standard names using fuzzy matching with priorities.
    
    Each standard column has multiple synonym patterns with a priority score.
    When a DataFrame column matches multiple standard names, the highest-priority match wins.
    When multiple DataFrame columns match the same standard name, the highest-priority one wins.
    """
    # For each standard name, find the best matching DataFrame column
    matches: Dict[str, Tuple[str, int]] = {}  # std_name -> (df_col, priority)
    
    for real_col in df.columns:
        col_lower = str(real_col).lower().strip()
        # Special: skip columns that are clearly row indices
        if col_lower in ['sl no', 'sl no.', 'sr no', 'sr no.', 's.no', 's no', 'sno', '#', 'unnamed: 0']:
            continue
        
        for std_name, config in COLUMN_SYNONYMS.items():
            for pattern, priority in config['patterns']:
                # Check if pattern matches (substring or exact)
                if pattern in col_lower or col_lower == pattern:
                    # For 'sgst': make sure we don't match 'igst' columns
                    if std_name == 'sgst' and 'igst' in col_lower:
                        continue
                    
                    # Keep the highest-priority match per standard name
                    current = matches.get(std_name)
                    if current is None or priority > current[1]:
                        matches[std_name] = (real_col, priority)
                    break  # This pattern matched; move to next std_name
    
    col_map = {std: df_col for std, (df_col, _) in matches.items()}
    
    logger.info(f"  Column mapping: {col_map}")
    
    # Warn if critical columns are missing
    for critical in ['inv_num', 'gstin']:
        if critical not in col_map:
            logger.warning(f"  ⚠️ Could not find '{critical}' column. Available: {list(df.columns)}")
    
    return col_map


# ═══════════════════════════════════════════════════════════════
# INVOICE NUMBER NORMALIZATION
# ═══════════════════════════════════════════════════════════════

def normalize_inv_num(s: str) -> str:
    """
    Normalize an invoice number for matching.
    Strips whitespace, uppercases, removes separators (/ - _ space)
    so 'HCL/2024/7712' and 'HCL20247712' will match.
    """
    s = str(s).strip().upper()
    s = re.sub(r'[\s/\-_\.]+', '', s)
    # Remove leading zeros in numeric-only parts
    return s


# ═══════════════════════════════════════════════════════════════
# DATA NORMALIZATION
# ═══════════════════════════════════════════════════════════════

def rename_to_standard(df: pd.DataFrame, col_map: Dict[str, str]) -> pd.DataFrame:
    """Renames columns to standard names, cleans and normalizes data."""
    if not col_map:
        raise ValueError(
            "Could not identify any standard columns in the file. "
            f"Columns found: {list(df.columns)}\n"
            "Expected columns like: GSTIN, Invoice Number, Taxable Value, IGST, CGST, SGST"
        )
    
    reverse_map = {v: k for k, v in col_map.items()}
    valid_cols = [v for v in col_map.values() if v in df.columns]
    std_df = df[valid_cols].rename(columns=reverse_map).copy()
    
    # Force numeric for value columns
    num_cols = ['taxable', 'igst', 'cgst', 'sgst', 'cess', 'total_tax', 'total_value']
    for col in num_cols:
        if col in std_df.columns:
            std_df[col] = pd.to_numeric(std_df[col], errors='coerce').fillna(0)
    
    # Clean GSTIN
    if 'gstin' in std_df.columns:
        std_df['gstin'] = (
            std_df['gstin'].astype(str).str.strip().str.upper()
            .replace({'NAN': '', 'NONE': '', 'NA': '', 'NULL': '', 'NIL': '', '-': ''})
        )
    
    # Clean invoice number — keep display version, normalize for matching
    if 'inv_num' in std_df.columns:
        std_df['inv_num_display'] = std_df['inv_num'].astype(str).str.strip()
        std_df['inv_num'] = std_df['inv_num'].apply(normalize_inv_num)
    
    return std_df


# ═══════════════════════════════════════════════════════════════
# TOTAL / SUMMARY ROW REMOVAL
# ═══════════════════════════════════════════════════════════════

def drop_total_rows(df: pd.DataFrame, source_name: str) -> pd.DataFrame:
    """
    Removes footer/total/summary rows that contaminate matching.
    Detects by:
      1. inv_num is NaN, blank, or literally "NAN"
      2. Any text column contains "Total", "Grand Total", etc.
      3. gstin is blank BUT taxable value is large (likely a sum row)
    """
    before = len(df)
    mask_keep = pd.Series(True, index=df.index)
    
    # Rule 1: inv_num is NaN/blank/NAN
    if 'inv_num' in df.columns:
        inv = df['inv_num'].astype(str).str.strip().str.upper()
        mask_bad_inv = inv.isin(['', 'NAN', 'NONE', 'NULL', 'NA', 'NIL', '-', 'TOTAL', 'GRANDTOTAL'])
        mask_keep &= ~mask_bad_inv
    
    # Rule 2: Any string column contains total-like keywords
    str_cols = df.select_dtypes(include=['object']).columns
    for col in str_cols:
        vals = df[col].astype(str).str.strip().str.lower()
        for indicator in TOTAL_ROW_INDICATORS:
            mask_keep &= ~(vals == indicator)
    
    # Rule 3: gstin is blank AND inv_num is blank → almost certainly a total row
    if 'gstin' in df.columns and 'inv_num' in df.columns:
        gstin_blank = df['gstin'].astype(str).str.strip().str.upper().isin(['', 'NAN', 'NONE', 'NA'])
        inv_blank = df['inv_num'].astype(str).str.strip().str.upper().isin(['', 'NAN', 'NONE', 'NA'])
        mask_keep &= ~(gstin_blank & inv_blank)
    
    result = df[mask_keep].reset_index(drop=True)
    dropped = before - len(result)
    if dropped > 0:
        logger.info(f"  🗑️ {source_name}: Dropped {dropped} total/summary row(s)")
    
    return result


# ═══════════════════════════════════════════════════════════════
# BLOCKED ITC SEPARATION
# ═══════════════════════════════════════════════════════════════

def separate_blocked_itc(df: pd.DataFrame, source_name: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    If an 'itc_eligible' column exists, separates rows where ITC is blocked.
    Returns (eligible_df, blocked_df).
    """
    if 'itc_eligible' not in df.columns:
        return df, pd.DataFrame()
    
    itc_vals = df['itc_eligible'].astype(str).str.strip().str.lower()
    
    blocked_mask = itc_vals.isin(ITC_BLOCKED_VALUES)
    
    eligible = df[~blocked_mask].reset_index(drop=True)
    blocked = df[blocked_mask].reset_index(drop=True)
    
    if len(blocked) > 0:
        blocked_tax = 0
        for col in ['igst', 'cgst', 'sgst', 'cess']:
            if col in blocked.columns:
                blocked_tax += blocked[col].sum()
        logger.info(f"  🚫 {source_name}: Separated {len(blocked)} blocked ITC row(s) "
                     f"(₹{blocked_tax:,.0f} total tax excluded from comparison)")
    
    return eligible, blocked


# ═══════════════════════════════════════════════════════════════
# MATCHING ENGINE
# ═══════════════════════════════════════════════════════════════

def match_data(df1: pd.DataFrame, df2: pd.DataFrame, job_type: str) -> pd.DataFrame:
    """Matches invoices from two sources using GSTIN + Invoice Number."""
    
    # Determine keys
    keys = []
    
    # IRN for E-Invoice jobs
    if job_type in [JobType.EINV_VS_SR, JobType.GSTR1_VS_EINV, 'einv_vs_sr', 'gstr1_vs_einv']:
        if 'irn' in df1.columns and 'irn' in df2.columns:
            keys.append('irn')
    
    # GSTIN + Invoice Number (primary)
    if not keys:
        if 'gstin' in df1.columns and 'gstin' in df2.columns:
            keys.append('gstin')
        if 'inv_num' in df1.columns and 'inv_num' in df2.columns:
            keys.append('inv_num')
    
    # Fallback
    if not keys:
        if 'inv_num' in df1.columns and 'inv_num' in df2.columns:
            keys.append('inv_num')
        else:
            raise ValueError(
                f"Cannot match: no common key columns found.\n"
                f"  File 1 cols: {list(df1.columns)}\n"
                f"  File 2 cols: {list(df2.columns)}"
            )
    
    logger.info(f"  🔗 Matching on: {keys}")
    
    # Merge
    merged = pd.merge(df1, df2, on=keys, how='outer', suffixes=('_src1', '_src2'), indicator=True)
    
    # Calculate differences
    num_cols = ['taxable', 'igst', 'cgst', 'sgst', 'cess', 'total_tax', 'total_value']
    for col in num_cols:
        c1, c2 = f"{col}_src1", f"{col}_src2"
        if c1 in merged.columns and c2 in merged.columns:
            merged[f'Diff_{col.capitalize()}'] = merged[c1].fillna(0) - merged[c2].fillna(0)
    
    # Status
    src1_label, src2_label = get_source_labels(job_type)
    
    def status(row):
        if row['_merge'] == 'both':
            t1 = row.get('taxable_src1', 0) or 0
            t2 = row.get('taxable_src2', 0) or 0
            diff = abs(t1 - t2)
            if diff < 1.0:
                return 'MATCHED'
            else:
                return f'MISMATCH (₹{diff:,.0f} diff)'
        elif row['_merge'] == 'left_only':
            return f'MISSING IN {src2_label.upper()}'
        else:
            return f'MISSING IN {src1_label.upper()}'
    
    merged['Status'] = merged.apply(status, axis=1)
    
    # Reorder: Status first, drop _merge
    cols = ['Status'] + [c for c in merged.columns if c not in ('Status', '_merge')]
    merged = merged[cols]
    
    # Stats
    matched = (merged.Status == 'MATCHED').sum()
    mismatch = merged.Status.str.contains('MISMATCH', na=False).sum()
    missing_s2 = merged.Status.str.contains(f'MISSING IN {src2_label.upper()}', na=False).sum()
    missing_s1 = merged.Status.str.contains(f'MISSING IN {src1_label.upper()}', na=False).sum()
    logger.info(f"  📊 Results: {len(merged)} total | ✅ {matched} matched | "
                f"⚠️ {mismatch} mismatch | 🔴 {missing_s2} only in {src1_label} | "
                f"🟡 {missing_s1} only in {src2_label}")
    
    return merged


# ═══════════════════════════════════════════════════════════════
# EXCEL REPORT GENERATION
# ═══════════════════════════════════════════════════════════════

def generate_excel_report(
    result_df: pd.DataFrame,
    df1: pd.DataFrame, df2: pd.DataFrame,
    df1_blocked: pd.DataFrame, df2_blocked: pd.DataFrame,
    src1_label: str, src2_label: str
) -> bytes:
    """Generates a formatted Excel report with multiple sheets."""
    output = io.BytesIO()
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        result_df.to_excel(writer, index=False, sheet_name="Reconciliation")
        df1.to_excel(writer, index=False, sheet_name=src1_label[:31])
        df2.to_excel(writer, index=False, sheet_name=src2_label[:31])
        
        if len(df1_blocked) > 0:
            df1_blocked.to_excel(writer, index=False, sheet_name="Blocked ITC")
        
        workbook = writer.book
        ws = writer.sheets['Reconciliation']
        
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#DDEBF7', 'border': 1})
        matched_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        mismatch_fmt = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C5700'})
        missing_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        
        for i, col in enumerate(result_df.columns):
            ws.write(0, i, col, header_fmt)
            ws.set_column(i, i, max(len(str(col)), 15))
        
        if 'Status' in result_df.columns:
            si = result_df.columns.get_loc('Status')
            for ri, s in enumerate(result_df['Status']):
                fmt = None
                if s == 'MATCHED': fmt = matched_fmt
                elif 'MISMATCH' in str(s): fmt = mismatch_fmt
                elif 'MISSING' in str(s): fmt = missing_fmt
                if fmt: ws.write(ri + 1, si, s, fmt)
    
    return output.getvalue()
