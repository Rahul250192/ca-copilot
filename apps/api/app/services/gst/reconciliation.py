import pandas as pd
import io
from typing import List, Dict, Any

def clean_header(h):
    return str(h).strip().lower()

def reconcile_gst(input_bytes_list: List[bytes]) -> bytes:
    """
    1. Read multiple GSTR-2B Excel files (Sheet 'B2B').
    2. Extract relevant columns: GSTIN, Trade Name, Taxable Value, IGST, CGST, SGST, Cess.
    3. Aggregate (Sum) values by GSTIN.
    4. Return consolidated Excel.
    """
    
    # Target columns mapping (Normalized -> Display Name)
    # We want to keep: GSTIN, Name, and Numeric values
    
    dfs = []
    
    for file_bytes in input_bytes_list:
        try:
            # Read 'B2B' sheet
            df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="B2B")
            
            # Normalize headers
            df.columns = [clean_header(c) for c in df.columns]
            
            # Identify columns dynamically
            col_map = {}
            for col in df.columns:
                if "gstin" in col and "supplier" in col:
                    col_map["gstin"] = col
                elif "trade" in col or "legal" in col:
                    col_map["name"] = col
                elif "taxable" in col and "value" in col:
                    col_map["taxable_value"] = col
                elif "integrated" in col and "tax" in col:
                    col_map["igst"] = col
                elif "central" in col and "tax" in col:
                    col_map["cgst"] = col
                elif "state" in col and "tax" in col:
                    col_map["sgst"] = col
                elif "cess" in col:
                    col_map["cess"] = col
            
            if not col_map.get("gstin"):
                # specific fallback for standard format
                if "gstin of supplier" in df.columns: col_map["gstin"] = "gstin of supplier"
            
            if not col_map.get("gstin"):
                 print(f"Skipping file: Could not find GSTIN column in headers: {df.columns}")
                 continue

            # Rename columns to standard names for concatenation
            rename_dict = {}
            keep_cols = []
            
            if "gstin" in col_map: 
                rename_dict[col_map["gstin"]] = "GSTIN"
                keep_cols.append("GSTIN")
            if "name" in col_map: 
                rename_dict[col_map["name"]] = "Trade Name"
                keep_cols.append("Trade Name")
            
            # Numeric columns
            numeric_cols_map = {
                "taxable_value": "Taxable Value",
                "igst": "Integrated Tax",
                "cgst": "Central Tax",
                "sgst": "State/UT Tax",
                "cess": "Cess"
            }
            
            for key, display_name in numeric_cols_map.items():
                if key in col_map:
                    rename_dict[col_map[key]] = display_name
                    keep_cols.append(display_name)
                else:
                    # If missing, we will create it with 0 later? 
                    # Better to just not include if not present, but for aggregation consistency we might need it.
                    pass

            # Filter and Rename
            temp_df = df[list(rename_dict.keys())].rename(columns=rename_dict)
            
            # Ensure 15 char valid GSTINs (basic cleanup)
            temp_df = temp_df.dropna(subset=["GSTIN"])
            temp_df["GSTIN"] = temp_df["GSTIN"].astype(str).str.strip().str.upper()
            temp_df = temp_df[temp_df["GSTIN"].str.len() >= 15] 

            dfs.append(temp_df)
            
        except Exception as e:
            print(f"Error reading reconciliation input file: {e}")
            continue
            
    if not dfs:
        raise ValueError("No valid data found in input files.")
        
    # Concatenate all dataframes
    full_df = pd.concat(dfs, ignore_index=True)
    
    # Fill missing numeric cols with 0 before summing
    numeric_cols = ["Taxable Value", "Integrated Tax", "Central Tax", "State/UT Tax", "Cess"]
    existing_numeric = [c for c in numeric_cols if c in full_df.columns]
    
    for c in existing_numeric:
        full_df[c] = pd.to_numeric(full_df[c], errors='coerce').fillna(0)
        
    # Aggregate
    # Group by GSTIN. For Trade Name, we trigger 'first' (assuming consistent naming for same GSTIN)
    agg_rules = {c: 'sum' for c in existing_numeric}
    if "Trade Name" in full_df.columns:
        agg_rules["Trade Name"] = 'first'
        
    result_df = full_df.groupby("GSTIN", as_index=False).agg(agg_rules)
    
    # Calculate Total Tax
    result_df["Total Tax"] = 0
    for c in ["Integrated Tax", "Central Tax", "State/UT Tax", "Cess"]:
        if c in result_df.columns:
            result_df["Total Tax"] += result_df[c]
            
    # Format Output
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        result_df.to_excel(writer, index=False, sheet_name="Reconciliation")
        
        # Add simple formatting
        workbook = writer.book
        worksheet = writer.sheets['Reconciliation']
        money_fmt = workbook.add_format({'num_format': '#,##0.00'})
        
        # Apply formatting to numeric columns
        for i, col in enumerate(result_df.columns):
            if col in numeric_cols or col == "Total Tax":
                worksheet.set_column(i, i, 15, money_fmt)
            else:
                worksheet.set_column(i, i, 20)
                
    return output.getvalue()
