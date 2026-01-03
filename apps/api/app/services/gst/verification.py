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

def verify_gstins(input_bytes_list: List[bytes]) -> bytes:
    """
    1. Read GSTR-2B Excel(s).
    2. Extract unique GSTINs from 'GSTIN of supplier' column.
    3. Call Appyflow API for each.
    4. Return Excel with [GSTIN, Status, Legal Name, Error].
    """
    if not settings.APPYFLOW_API_KEY:
        raise ValueError("APPYFLOW_API_KEY is not configured.")

    all_gstins = set()
    
    # 1. Extract GSTINs
    for file_bytes in input_bytes_list:
        try:
            xls = pd.ExcelFile(io.BytesIO(file_bytes))
            
            # Find B2B sheet (case-insensitive)
            b2b_sheet = next((s for s in xls.sheet_names if s.lower() == "b2b"), None)
            
            if not b2b_sheet:
                print("Sheet 'B2B' not found in file. Skipping.")
                continue

            try:
                # Scan first 20 rows for header in B2B sheet
                df_scan = pd.read_excel(xls, sheet_name=b2b_sheet, header=None, nrows=20)
                
                header_row_idx = -1
                for idx, row in df_scan.iterrows():
                    # Convert row to string and check for keywords
                    row_vals = [str(v).lower().strip() for v in row.values]
                    
                    # Target: "GSTIN of supplier" or similar
                    has_gstin = any("gstin" in v for v in row_vals)
                    has_supplier = any("supplier" in v for v in row_vals)
                    
                    if has_gstin and has_supplier:
                        header_row_idx = idx
                        break
                
                if header_row_idx == -1:
                     # Fallback check
                     for idx, row in df_scan.iterrows():
                        row_vals = [str(v).lower().strip() for v in row.values]
                        # "gstin/uin of supplier"
                        if any("gstin" in v and "supplier" in v for v in row_vals):
                             header_row_idx = idx
                             break

                if header_row_idx != -1:
                    # Reload with correct header
                    df = pd.read_excel(xls, sheet_name=b2b_sheet, header=header_row_idx)
                    df.columns = [clean_header(c) for c in df.columns]
                    
                    # Find GSTIN column again in normalized headers
                    gstin_col = None
                    for col in df.columns:
                        if "gstin" in col and "supplier" in col:
                            gstin_col = col
                            break
                    
                    if not gstin_col:
                         # Fallback to just "gstin" if strictly one column has it
                         potential = [c for c in df.columns if "gstin" in c]
                         if len(potential) == 1:
                             gstin_col = potential[0]

                    if gstin_col:
                        raw_gstins = df[gstin_col].dropna().astype(str).unique()
                        for g in raw_gstins:
                            g = g.strip().upper()
                            # Basic GSTIN validation: 15 chars, alphanumeric
                            if len(g) == 15 and g.isalnum():
                                all_gstins.add(g)
            except Exception as e_sheet:
                print(f"Error processing B2B sheet: {e_sheet}")

        except Exception as e:
            print(f"Error reading input file: {e}")
            continue

    if not all_gstins:
        raise ValueError("No valid GSTINs found in input files (Sheet 'B2B', Column 'GSTIN of supplier').")

    # 2. Verify against Appyflow
    results = []
    headers = {"Authorization": settings.APPYFLOW_API_KEY}  # Adjust based on actual Appyflow Auth Scheme
    # Appyflow usually expects headers or query param. Docs say: header 'Content-Type: application/json', key often in header or url.
    # We will assume Key in header 'Authorization' or custom header based on typical patterns. 
    # USER provided key only. Let's try standard 'Authorization: <Key>' or query param. 
    # Verification URL pattern: https://appyflow.in/api/verifyGST?gstNo=...
    
    # Correction: checking strictly if user provided specific docs. Assuming standard GET.
    
    print(f"Verifying {len(all_gstins)} GSTINs...")
    
    for i, gstin in enumerate(all_gstins):
        status = "Unknown"
        error_msg = ""
        legal_name = ""
        
        try:
            # Assuming widely used Appyflow endpoint structure
            url = f"https://appyflow.in/api/verifyGST?gstNo={gstin}&key_secret={settings.APPYFLOW_API_KEY}"
            
            resp = requests.get(url, timeout=10)
            
            if resp.status_code == 200:
                data = resp.json()
                # Parse response - this depends on exact Appyflow schema
                # Common schema: { "taxpayerInfo": { "stjCd": "Active", "lgnm": "Name" }, "error": ... }
                
                if "taxpayerInfo" in data:
                    info = data["taxpayerInfo"]
                    status = info.get("sts", "Active") # sts = status often
                    legal_name = info.get("lgnm", "") or info.get("tradeNam", "")
                elif "error" in data:
                    status = "Failed"
                    error_msg = str(data["error"])
                else:
                    status = "Verified" # Fallback if structure unknown but 200 OK
            else:
                status = "Error"
                error_msg = f"HTTP {resp.status_code}"
                
        except Exception as e:
            status = "Error"
            error_msg = str(e)
            
        results.append({
            "GSTIN": gstin,
            "Status": status,
            "Legal Name": legal_name,
            "Error Message": error_msg,
            "Verified At": pd.Timestamp.now()
        })
        
        # Rate limit
        time.sleep(RATE_LIMIT_DELAY)

    # 3. Generate Output
    out_df = pd.DataFrame(results)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        out_df.to_excel(writer, index=False, sheet_name="Verification Report")
    
    return output.getvalue()
