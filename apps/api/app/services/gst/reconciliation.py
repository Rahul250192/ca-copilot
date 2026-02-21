import pandas as pd
import io
import os
from typing import List, Dict, Any, Tuple
from app.models.job import JobType

def clean_header(h):
    return str(h).strip().lower()

def reconcile_gst(input_bytes_list: List[bytes], filenames: List[str] = None, job_type: str = "GST_RECON") -> bytes:
    """
    Entry point for all reconciliation jobs.
    input_bytes_list[0] is typically Source 1 (Portal/Data)
    input_bytes_list[1] is typically Source 2 (Internal/Books)
    """
    
    # Load DataFrames
    df1 = load_reconciliation_file(input_bytes_list[0], filenames[0])
    df2 = load_reconciliation_file(input_bytes_list[1], filenames[1])
    
    # Identify standard columns for both
    cols1 = identify_columns(df1)
    cols2 = identify_columns(df2)
    
    # Map to standard names for matching
    df1_std = rename_to_standard(df1, cols1)
    df2_std = rename_to_standard(df2, cols2)
    
    # Perform matching
    # Matching keys: GSTIN (if present), Invoice Number, Date (optional), Value
    result_df = match_data(df1_std, df2_std, job_type)
    
    # Generate Output Excel
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        result_df.to_excel(writer, index=False, sheet_name="Reconciliation_Summary")
        
        # Add sheets for individual sources for reference
        df1_std.to_excel(writer, index=False, sheet_name="Source_1_Data")
        df2_std.to_excel(writer, index=False, sheet_name="Source_2_Data")
        
        # Formatting
        workbook = writer.book
        summary_sheet = writer.sheets['Reconciliation_Summary']
        
        # Colors for status
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#DDEBF7', 'border': 1})
        matched_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100'})
        mismatch_fmt = workbook.add_format({'bg_color': '#FFEB9C', 'font_color': '#9C5700'})
        missing_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006'})
        money_fmt = workbook.add_format({'num_format': '#,##0.00'})
        
        # Apply conditional formatting or basic formatting
        for i, col in enumerate(result_df.columns):
            summary_sheet.write(0, i, col, header_fmt)
            width = max(len(col), 15)
            summary_sheet.set_column(i, i, width)
            
        # Highlight status column (assumed to be 'Status')
        if 'Status' in result_df.columns:
            status_idx = result_df.columns.get_loc('Status')
            for row_idx, status in enumerate(result_df['Status']):
                fmt = None
                if status == 'MATCHED': fmt = matched_fmt
                elif 'MISMATCH' in status: fmt = mismatch_fmt
                elif 'MISSING' in status: fmt = missing_fmt
                
                if fmt:
                    summary_sheet.write(row_idx + 1, status_idx, status, fmt)

    return output.getvalue()

def load_reconciliation_file(file_bytes: bytes, filename: str) -> pd.DataFrame:
    """Intelligently loads Excel or CSV, finding the header row."""
    ext = os.path.splitext(filename)[1].lower()
    
    if ext in ['.xlsx', '.xls']:
        xls = pd.ExcelFile(io.BytesIO(file_bytes))
        # Use first sheet or common names like 'B2B', 'Sheet1', 'Data'
        sheet_name = next((s for s in xls.sheet_names if s.lower() in ['b2b', 'sheet1', 'data', 'sales', 'purchases']), xls.sheet_names[0])
        
        # Scan for header
        df_scan = pd.read_excel(xls, sheet_name=sheet_name, header=None, nrows=20)
        header_row_idx = 0
        for idx, row in df_scan.iterrows():
            row_vals = [str(v).lower().strip() for v in row.values]
            if any(k in v for v in row_vals for k in ['gstin', 'invoice', 'taxable', 'date', 'supplier', 'customer']):
                header_row_idx = idx
                break
        
        return pd.read_excel(xls, sheet_name=sheet_name, header=header_row_idx)
    else:
        # Fallback to CSV
        try:
            return pd.read_csv(io.BytesIO(file_bytes))
        except:
            # Try with different encoding/separator if needed
            return pd.read_csv(io.BytesIO(file_bytes), encoding='latin1')

def identify_columns(df: pd.DataFrame) -> Dict[str, str]:
    """Identify key columns using fuzzy mapping."""
    col_map = {}
    cols = [str(c).lower() for c in df.columns]
    
    for real_col in df.columns:
        c = str(real_col).lower()
        if 'gstin' in c or 'uin' in c: col_map['gstin'] = real_col
        elif 'invoice' in c and 'number' in c: col_map['inv_num'] = real_col
        elif 'invoice' in c and 'no' in c: col_map['inv_num'] = real_col
        elif 'voucher' in c and 'no' in c: col_map['inv_num'] = real_col # Books often use Voucher No
        elif 'date' in c: col_map['date'] = real_col
        elif 'taxable' in c and 'value' in c: col_map['taxable'] = real_col
        elif 'taxable' in c and 'amount' in c: col_map['taxable'] = real_col
        elif 'igst' in c or 'integrated' in c: col_map['igst'] = real_col
        elif 'cgst' in c or 'central' in c: col_map['cgst'] = real_col
        elif 'sgst' in c or 'state' in c: col_map['sgst'] = real_col
        elif 'cess' in c: col_map['cess'] = real_col
        elif 'total' in c and 'tax' in c: col_map['total_tax'] = real_col
        elif 'total' in c and 'invoice' in c: col_map['total_value'] = real_col
        elif 'irn' in c: col_map['irn'] = real_col
    
    return col_map

def rename_to_standard(df: pd.DataFrame, col_map: Dict[str, str]) -> pd.DataFrame:
    """Renames and cleans data for matching."""
    reverse_map = {v: k for k, v in col_map.items()}
    std_df = df[list(col_map.values())].rename(columns=reverse_map)
    
    # Force Numeric
    num_cols = ['taxable', 'igst', 'cgst', 'sgst', 'cess', 'total_tax', 'total_value']
    for col in num_cols:
        if col in std_df.columns:
            std_df[col] = pd.to_numeric(std_df[col], errors='coerce').fillna(0)
            
    # Clean String Keys
    if 'gstin' in std_df.columns:
        std_df['gstin'] = std_df['gstin'].astype(str).str.strip().str.upper()
    if 'inv_num' in std_df.columns:
        std_df['inv_num'] = std_df['inv_num'].astype(str).str.strip().str.upper()
        
    return std_df

def match_data(df1: pd.DataFrame, df2: pd.DataFrame, job_type: str) -> pd.DataFrame:
    """Performs the matching logic based on the job type."""
    
    # Define matching keys
    keys = []
    
    # Priority 1: IRN (for E-Invoice related jobs)
    if job_type in [JobType.EINV_VS_SR, JobType.GSTR1_VS_EINV]:
        if 'irn' in df1.columns and 'irn' in df2.columns:
            # Drop rows where IRN might be missing before attempting IRN matching
            # or just add it to keys. 
            keys.append('irn')

    # Priority 2: GSTIN + Invoice Number
    if not keys:
        if 'gstin' in df1.columns and 'gstin' in df2.columns: keys.append('gstin')
        if 'inv_num' in df1.columns and 'inv_num' in df2.columns: keys.append('inv_num')
    
    if not keys:
        # Fallback to Invoice Number only
        if 'inv_num' in df1.columns and 'inv_num' in df2.columns: keys.append('inv_num')
        else:
            raise ValueError("Could not find common matching keys (GSTIN or Invoice Number)")

    # Perform Outer Merge with indicator
    merged = pd.merge(df1, df2, on=keys, how='outer', suffixes=('_src1', '_src2'), indicator=True)
    
    # Calculate Differences for numeric columns
    num_cols = ['taxable', 'igst', 'cgst', 'sgst', 'total_tax', 'total_value']
    for col in num_cols:
        col1, col2 = f"{col}_src1", f"{col}_src2"
        if col1 in merged.columns and col2 in merged.columns:
            merged[f'Diff_{col.capitalize()}'] = merged[col1] - merged[col2]
    
    def determine_status(row):
        if row['_merge'] == 'both':
            # Check for significant value mismatches
            # Use taxable value as primary indicator
            t1 = row.get('taxable_src1', 0)
            t2 = row.get('taxable_src2', 0)
            diff = abs(t1 - t2)
            
            if diff < 1.0: # 1 Rupee threshold
                return 'MATCHED'
            else:
                return f'MISMATCH (Value Diff: {diff:.2f})'
                
        elif row['_merge'] == 'left_only':
            return 'MISSING IN SOURCE 2'
        else:
            return 'MISSING IN SOURCE 1'
            
    merged['Status'] = merged.apply(determine_status, axis=1)
    
    # Move Status to prominent position
    cols = list(merged.columns)
    cols.remove('Status')
    cols.insert(0, 'Status')
    merged = merged[cols]
    
    # Clean up internal columns
    if '_merge' in merged.columns:
        merged = merged.drop(columns=['_merge'])
    
    return merged
