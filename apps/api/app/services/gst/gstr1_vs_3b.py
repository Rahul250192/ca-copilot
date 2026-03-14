"""
GSTR-1 vs GSTR-3B — Tax Liability Reconciliation

Simple summary-level comparison:
  1. Sum outward supply sheets from GSTR-1 (B2B, B2CL, B2CS, EXP, AT)
  2. Find Table 3.1(a) row in GSTR-3B
  3. Variance = G1 − 3B per component
"""

import pandas as pd
import numpy as np
import io, os, json, logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

COMPONENTS = ['taxable', 'igst', 'cgst', 'sgst', 'cess']

# Sheets to skip in GSTR-1 (not outward supply data)
SKIP_SHEETS = ['cdnr', 'cdnur', 'cdn', 'hsn', 'doc', 'nil', 'exempt', 'summary',
               'help', 'readme', 'atadj', 'overview']


def reconcile_gstr1_vs_3b(file_bytes_list: List[bytes], filenames: List[str] = None) -> Dict[str, Any]:
    """Main entry: parse both files, compute variance, return result."""
    fn1 = (filenames or ["gstr1.xlsx"])[0]
    fn2 = (filenames or ["", "gstr3b.xlsx"])[1]

    g1 = parse_gstr1(file_bytes_list[0], fn1)
    g3b = parse_gstr3b(file_bytes_list[1], fn2)

    variance = {c: round(g1['totals'][c] - g3b['totals'][c], 2) for c in COMPONENTS}
    tax_g1 = sum(g1['totals'][c] for c in ['igst', 'cgst', 'sgst', 'cess'])
    tax_3b = sum(g3b['totals'][c] for c in ['igst', 'cgst', 'sgst', 'cess'])
    total_var = round(tax_g1 - tax_3b, 2)
    pct = round(abs(total_var / tax_3b * 100), 1) if tax_3b else 0

    logger.info(f"G1 tax={tax_g1:,.0f}  3B tax={tax_3b:,.0f}  Var={total_var:,.0f} ({pct}%)")

    risk = _risk(total_var)
    actions = _actions(total_var, variance)
    report = _excel_report(g1, g3b, variance, risk)

    return {
        'gstr1_sections': g1['sections'],
        'gstr3b_row': g3b.get('row_label', 'Table 3.1(a)'),
        'gstr1_totals': g1['totals'],
        'gstr3b_totals': g3b['totals'],
        'variance': variance,
        'total_tax_g1': round(tax_g1, 2),
        'total_tax_3b': round(tax_3b, 2),
        'total_variance': total_var,
        'variance_pct': pct,
        'risk': risk,
        'actions': actions,
        'report_bytes': report,
    }


# ── GSTR-1: sum outward supply sheets ──────────────────────────

def parse_gstr1(fbytes: bytes, fname: str) -> Dict:
    if fname.lower().endswith('.json'):
        return _g1_json(fbytes)

    xls = pd.ExcelFile(io.BytesIO(fbytes))
    logger.info(f"GSTR-1 sheets: {xls.sheet_names}")

    sections, grand = [], {c: 0.0 for c in COMPONENTS}

    for sn in xls.sheet_names:
        if _should_skip(sn):
            logger.info(f"  skip '{sn}'")
            continue

        df = _read_sheet(xls, sn)
        if df is None or df.empty:
            continue

        tcols = _find_tax_cols(df)
        if not tcols:
            continue

        # drop total rows
        for col in df.select_dtypes('object').columns:
            df = df[~df[col].astype(str).str.strip().str.lower().isin(
                ['total', 'grand total', 'sub total'])]

        totals = {c: round(float(pd.to_numeric(df[tcols[c]], errors='coerce').fillna(0).sum()), 2)
                  if c in tcols and tcols[c] in df.columns else 0.0
                  for c in COMPONENTS}

        sections.append({'section': sn, 'rows': len(df), **totals})
        for c in COMPONENTS:
            grand[c] += totals[c]

        logger.info(f"  ✅ '{sn}': {len(df)} rows, tax={totals['igst']+totals['cgst']+totals['sgst']:,.0f}")

    grand = {c: round(v, 2) for c, v in grand.items()}
    return {'sections': sections, 'totals': grand}


def _should_skip(sheet_name: str) -> bool:
    name = sheet_name.lower().replace(' ', '').replace('-', '').replace('_', '')
    return any(kw in name for kw in SKIP_SHEETS)


def _g1_json(fbytes: bytes) -> Dict:
    data = json.loads(fbytes.decode('utf-8'))
    grand = {c: 0.0 for c in COMPONENTS}
    sections = []

    for key in ['b2b', 'b2cl', 'b2cs', 'exp', 'at']:
        entries = data.get(key, [])
        if not entries:
            continue
        tot = {c: 0.0 for c in COMPONENTS}
        _walk_json_tax(entries, tot)
        if any(tot[c] for c in tot):
            sections.append({'section': key.upper(), 'rows': 0, **{c: round(v, 2) for c, v in tot.items()}})
            for c in COMPONENTS:
                grand[c] += tot[c]

    return {'sections': sections, 'totals': {c: round(v, 2) for c, v in grand.items()}}


# ── GSTR-3B: find the 3.1(a) row ──────────────────────────────

def parse_gstr3b(fbytes: bytes, fname: str) -> Dict:
    if fname.lower().endswith('.json'):
        return _3b_json(fbytes)

    xls = pd.ExcelFile(io.BytesIO(fbytes))
    logger.info(f"GSTR-3B sheets: {xls.sheet_names}")

    for sn in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=sn, header=None)

        for idx, row in df.iterrows():
            # find first cell that's a string
            text = ''
            for v in row.values:
                if isinstance(v, str) and len(v.strip()) > 5:
                    text = v.strip().lower()
                    break
            if not text:
                continue

            # Must contain "other than zero" to be 3.1(a), not 3.1(b)
            if 'other than zero' not in text and '3.1(a)' not in text and '3.1 (a)' not in text:
                continue

            # This is the 3.1(a) row — grab all numbers
            nums = [float(v) for v in row.values if _is_number(v)]
            if len(nums) < 3:
                continue

            totals = {
                'taxable': nums[0] if len(nums) > 0 else 0,
                'igst':    nums[1] if len(nums) > 1 else 0,
                'cgst':    nums[2] if len(nums) > 2 else 0,
                'sgst':    nums[3] if len(nums) > 3 else 0,
                'cess':    nums[4] if len(nums) > 4 else 0,
            }
            totals = {c: round(v, 2) for c, v in totals.items()}
            logger.info(f"  ✅ 3.1(a) found in '{sn}' row {idx}: {totals}")
            return {'totals': totals, 'row_label': text[:80]}

    logger.error("  ❌ Table 3.1(a) not found in GSTR-3B!")
    return {'totals': {c: 0.0 for c in COMPONENTS}, 'row_label': 'Not found'}


def _3b_json(fbytes: bytes) -> Dict:
    data = json.loads(fbytes.decode('utf-8'))
    osup = (data.get('sup_details', data)).get('osup_det', {})
    totals = {
        'taxable': float(osup.get('txval', 0) or 0),
        'igst': float(osup.get('iamt', 0) or 0),
        'cgst': float(osup.get('camt', 0) or 0),
        'sgst': float(osup.get('samt', 0) or 0),
        'cess': float(osup.get('csamt', 0) or 0),
    }
    return {'totals': {c: round(v, 2) for c, v in totals.items()}, 'row_label': '3.1(a)'}


# ── Shared helpers ─────────────────────────────────────────────

def _read_sheet(xls, sn) -> Optional[pd.DataFrame]:
    try:
        scan = pd.read_excel(xls, sheet_name=sn, header=None, nrows=15)
        hdr = _find_header(scan)
        df = pd.read_excel(xls, sheet_name=sn, header=hdr)
        df.columns = [str(c).strip() for c in df.columns]
        return df.dropna(how='all').reset_index(drop=True)
    except Exception:
        return None


def _find_header(scan: pd.DataFrame) -> int:
    kw = ['igst', 'cgst', 'sgst', 'cess', 'taxable value', 'integrated tax',
          'central tax', 'state tax', 'gstin', 'invoice no', 'invoice number']
    best, best_s = 0, 0
    for i, row in scan.iterrows():
        s = sum(1 for v in row.values if pd.notna(v) and any(k in str(v).lower() for k in kw))
        if s >= best_s:  # >= so later rows win ties (headers come after summary rows)
            best_s, best = s, i
    return best


def _find_tax_cols(df: pd.DataFrame) -> Dict[str, str]:
    mapping = {
        'taxable': ['taxable value', 'taxable amount', 'taxable_value'],
        'igst': ['igst', 'integrated tax', 'iamt'],
        'cgst': ['cgst', 'central tax', 'camt'],
        'sgst': ['sgst', 'state tax', 'samt', 'sgst/utgst', 'utgst'],
        'cess': ['cess', 'csamt'],
    }
    result = {}
    for col in df.columns:
        cl = str(col).lower().strip()
        for comp, keywords in mapping.items():
            if comp not in result and any(kw in cl for kw in keywords):
                if comp == 'sgst' and 'igst' in cl:
                    continue
                result[comp] = col
                break
    return result


def _is_number(v) -> bool:
    if pd.isna(v):
        return False
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False


def _walk_json_tax(obj, totals):
    if isinstance(obj, list):
        for item in obj:
            _walk_json_tax(item, totals)
    elif isinstance(obj, dict):
        for comp, keys in [('taxable', ['txval']), ('igst', ['iamt']),
                           ('cgst', ['camt']), ('sgst', ['samt']), ('cess', ['csamt'])]:
            for k in keys:
                if k in obj:
                    totals[comp] += float(obj[k] or 0)
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _walk_json_tax(v, totals)


# ── Risk & Actions ─────────────────────────────────────────────

def _risk(var: float) -> Dict:
    a = abs(var)
    if a <= 1:
        return {'level': 'perfect', 'icon': '✅',
                'heading': 'Perfect Match!',
                'description': 'GSTR-1 and GSTR-3B match. No action needed.'}
    if var > 0:  # under-declared in 3B
        if a > 10000:
            return {'level': 'high', 'icon': '🔴',
                    'heading': f'HIGH RISK — Under-declared by ₹{a:,.0f}',
                    'description': f'GSTR-1 shows ₹{a:,.0f} more tax. ASMT-10 risk. Pay via DRC-03 with 18% interest.'}
        return {'level': 'medium', 'icon': '🟡',
                'heading': f'MEDIUM RISK — Shortfall of ₹{a:,.0f}',
                'description': f'₹{a:,.0f} less declared in 3B. Review and pay via DRC-03.'}
    else:  # over-declared in 3B
        if a > 10000:
            return {'level': 'neutral', 'icon': '💸',
                    'heading': f'Over-declared by ₹{a:,.0f}',
                    'description': f'Excess ₹{a:,.0f} paid in 3B. Adjust in next 3B or GSTR-9.'}
        return {'level': 'low', 'icon': '🟢',
                'heading': f'Minor excess of ₹{a:,.0f}',
                'description': f'Small excess paid. Adjust in next return.'}


def _actions(var: float, comp_var: Dict) -> List[Dict]:
    acts = []
    a = abs(var)
    if var > 1:
        acts.append({'icon': '⚠️', 'color': 'red',
                     'title': f'Pay ₹{a:,.0f} via DRC-03',
                     'description': 'File DRC-03 with 18% interest from due date.'})
        acts.append({'icon': '📋', 'color': 'yellow',
                     'title': 'Verify missing invoices in 3B',
                     'description': 'Check if sales invoices were missed in 3B computation.'})
    elif var < -1:
        acts.append({'icon': '💰', 'color': 'blue',
                     'title': f'Claim excess ₹{a:,.0f}',
                     'description': 'Reduce next month 3B liability or adjust in GSTR-9.'})
    else:
        acts.append({'icon': '✅', 'color': 'green',
                     'title': 'No action needed', 'description': 'Perfectly matched.'})
    acts.append({'icon': '📝', 'color': 'purple',
                 'title': 'Prepare GSTR-9 Table 9',
                 'description': 'This reconciliation feeds into Table 9 of annual return.'})
    return acts


# ── Excel Report ───────────────────────────────────────────────

def _excel_report(g1, g3b, variance, risk) -> bytes:
    buf = io.BytesIO()
    labels = {'taxable': 'Taxable Value', 'igst': 'IGST', 'cgst': 'CGST', 'sgst': 'SGST/UTGST', 'cess': 'Cess'}

    with pd.ExcelWriter(buf, engine='xlsxwriter') as w:
        rows = [{'Component': labels[c],
                 'GSTR-1': g1['totals'][c], 'GSTR-3B 3.1(a)': g3b['totals'][c],
                 'Variance (G1−3B)': variance[c],
                 'Status': 'Match' if abs(variance[c]) <= 1 else
                           ('Under-declared' if variance[c] > 0 else 'Over-declared')}
                for c in COMPONENTS]
        pd.DataFrame(rows).to_excel(w, index=False, sheet_name='Comparison')

        if g1['sections']:
            pd.DataFrame(g1['sections']).to_excel(w, index=False, sheet_name='GSTR-1 Breakup')

        for ws in w.sheets.values():
            for i in range(10):
                ws.set_column(i, i, 20)

    return buf.getvalue()
