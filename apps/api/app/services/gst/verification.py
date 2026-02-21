import time
import requests
import re
import pandas as pd
import io
from typing import List
from app.core.config import settings

# 200ms delay between calls to stay safe within rate limits if needed
# Plus retries/backoff
RATE_LIMIT_DELAY = 0.2 

def clean_header(h):
    return str(h).strip().lower()

def get_gstin_details(gstin: str) -> dict:
    """
    Call Appyflow API for a single GSTIN and return parsed details.
    """
    if not settings.APPYFLOW_API_KEY:
        raise ValueError("APPYFLOW_API_KEY is not configured.")
        
    gstin = gstin.strip().upper()
    status = "Unknown"
    error_msg = ""
    legal_name = ""
    state = ""
    
    try:
        url = f"https://appyflow.in/api/verifyGST?gstNo={gstin}&key_secret={settings.APPYFLOW_API_KEY}"
        resp = requests.get(url, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            if "taxpayerInfo" in data:
                info = data["taxpayerInfo"]
                status = info.get("sts", "Active")
                legal_name = info.get("lgnm", "") or info.get("tradeNam", "")
                state = info.get("pradr", {}).get("addr", {}).get("stcd", "") or info.get("stj", "")
            elif "error" in data:
                status = "Failed"
                error_msg = str(data["error"])
            else:
                status = "Verified"
        else:
            status = "Error"
            error_msg = f"HTTP {resp.status_code}"
            
    except Exception as e:
        status = "Error"
        error_msg = str(e)
        
    return {
        "gstin": gstin,
        "status": status,
        "legal_name": legal_name,
        "state": state,
        "error": error_msg
    }

def verify_gstins(input_bytes_list: List[bytes]) -> bytes:
    """
    1. Read GSTR-2B Excel(s).
    2. Extract unique GSTINs from 'GSTIN of supplier' column.
    3. Call Appyflow API for each.
    4. Return Excel with [GSTIN, Status, Legal Name, Error].
    """
    all_gstins = set()
    
    # 1. Extract GSTINs
    for file_bytes in input_bytes_list:
        try:
            xls = pd.ExcelFile(io.BytesIO(file_bytes))
            b2b_sheet = next((s for s in xls.sheet_names if s.lower() == "b2b"), None)
            
            if not b2b_sheet: continue

            try:
                df_scan = pd.read_excel(xls, sheet_name=b2b_sheet, header=None, nrows=20)
                header_row_idx = -1
                for idx, row in df_scan.iterrows():
                    row_vals = [str(v).lower().strip() for v in row.values]
                    if any("gstin" in v for v in row_vals) and any("supplier" in v for v in row_vals):
                        header_row_idx = idx
                        break
                
                if header_row_idx != -1:
                    df = pd.read_excel(xls, sheet_name=b2b_sheet, header=header_row_idx)
                    df.columns = [clean_header(c) for c in df.columns]
                    
                    gstin_col = None
                    for col in df.columns:
                        if "gstin" in col and "supplier" in col:
                            gstin_col = col
                            break
                    
                    if not gstin_col:
                         potential = [c for c in df.columns if "gstin" in c]
                         if len(potential) == 1: gstin_col = potential[0]

                    if gstin_col:
                        raw_gstins = df[gstin_col].dropna().astype(str).unique()
                        for g in raw_gstins:
                            g = g.strip().upper()
                            if len(g) == 15 and g.isalnum():
                                all_gstins.add(g)
            except Exception: continue
        except Exception: continue

    if not all_gstins:
        raise ValueError("No valid GSTINs found in input files.")

    # 2. Verify against Appyflow
    results = []
    print(f"Verifying {len(all_gstins)} GSTINs...")
    
    for gstin in all_gstins:
        details = get_gstin_details(gstin)
        results.append({
            "GSTIN": details["gstin"],
            "Status": details["status"],
            "Legal Name": details["legal_name"],
            "State": details["state"],
            "Error Message": details["error"],
            "Verified At": pd.Timestamp.now()
        })
        time.sleep(RATE_LIMIT_DELAY)

    return output.getvalue()
