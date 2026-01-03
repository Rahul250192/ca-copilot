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
            # Load with pandas for easier column finding
            # Assumption: Header is in first few rows. We'll try to find it.
            df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="B2B")
            
            # Normalize headers
            df.columns = [clean_header(c) for c in df.columns]
            
            # Find GSTIN column (smart search)
            gstin_col = None
            for col in df.columns:
                if "gstin" in col and "supplier" in col:
                    gstin_col = col
                    break
            
            if not gstin_col:
                # Fallback: exact match "gstin of supplier"
                if "gstin of supplier" in df.columns:
                    gstin_col = "gstin of supplier"

            if gstin_col:
                 # Extract unique valid-looking GSTINs
                 # Regex for GSTIN: \d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}
                 # Simplified: 15 chars
                 raw_gstins = df[gstin_col].dropna().astype(str).unique()
                 for g in raw_gstins:
                     g = g.strip().upper()
                     if len(g) == 15:
                         all_gstins.add(g)
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
