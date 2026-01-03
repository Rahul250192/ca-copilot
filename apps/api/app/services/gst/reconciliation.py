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
                    row_vals = [str(v).lower().strip() for v in row.values]
                    
                    # Target: "GSTIN" and "Supplier" (standard) or "Taxable Value" (reconciliation specific)
                    has_gstin = any("gstin" in v for v in row_vals)
                    has_supplier = any("supplier" in v for v in row_vals)
                    has_taxable = any("taxable" in v and "value" in v for v in row_vals)
                    
                    if (has_gstin and has_supplier) or (has_gstin and has_taxable):
                        header_row_idx = idx
                        break
                
                if header_row_idx == -1:
                     # Fallback check
                     for idx, row in df_scan.iterrows():
                        row_vals = [str(v).lower().strip() for v in row.values]
                        if any("gstin/uin of supplier" in v for v in row_vals):
                             header_row_idx = idx
                             break

                if header_row_idx == -1:
                    print("Could not find header row in B2B sheet.")
                    continue

                # Initial read
                df = pd.read_excel(xls, sheet_name=b2b_sheet, header=header_row_idx)
                
                # Check for merged headers (Tax Amount present but sub-taxes missing)
                cols_str = " ".join([str(c).lower() for c in df.columns])
                if "tax amount" in cols_str and "integrated" not in cols_str:
                    df = pd.read_excel(xls, sheet_name=b2b_sheet, header=[header_row_idx, header_row_idx+1])
                    
                    # Flatten headers
                    new_cols = []
                    for col in df.columns:
                        # col is tuple
                        # Filter out 'Unnamed' and 'nan'
                        parts = [str(x).strip() for x in col if "unnamed" not in str(x).lower() and str(x).lower() != "nan"]
                        new_cols.append(" ".join(parts).strip())
                    
                    df.columns = new_cols
                
            except Exception as e_sheet:
                print(f"Error processing B2B sheet scan: {e_sheet}")
                continue

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
                # fallback partial match
                potential = [c for c in df.columns if "gstin" in c]
                if len(potential) == 1: col_map["gstin"] = potential[0]
            
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
                rename_dict[col_map["name"]] = "Trade/Legal Name"
                keep_cols.append("Trade/Legal Name")
            
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
    agg_rules = {c: 'sum' for c in existing_numeric}
    if "Trade/Legal Name" in full_df.columns:
        agg_rules["Trade/Legal Name"] = 'first'
        
    result_df = full_df.groupby("GSTIN", as_index=False).agg(agg_rules)
    
    # Calculate Total Tax
    result_df["Total Tax"] = 0
    for c in ["Integrated Tax", "Central Tax", "State/UT Tax", "Cess"]:
        if c in result_df.columns:
            result_df["Total Tax"] += result_df[c]
            
    # Reorder Columns strictly
    desired_order = ["GSTIN", "Trade/Legal Name", "Taxable Value", "Integrated Tax", "Central Tax", "State/UT Tax", "Cess", "Total Tax"]
    # Only keep columns that actually exist in result_df
    final_cols = [c for c in desired_order if c in result_df.columns]
    result_df = result_df[final_cols]

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
