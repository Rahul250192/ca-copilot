import io
import os
import pandas as pd
import logging
import json
import asyncio
from typing import List, Dict, Any, Optional
from app.services.llm import LLMService

# Setup Logging
logger = logging.getLogger("hsn_plotter")

async def map_items_to_hsn_with_ai(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Use LLM to map item descriptions to HSN codes.
    """
    if not items:
        return []

    system_prompt = """
    You are an expert Indian GST Consultant.
    Your task is to map product/service descriptions to their most accurate 4-digit or 6-digit HSN/SAC codes.
    
    Rules:
    - Return the most specific HSN code possible.
    - If the item is a service, return the SAC code (typically starting with 99).
    - Provide a short description of the HSN category.
    
    Return a JSON array of objects with these keys:
    - description: (the input description)
    - hsn_code: (the 4, 6, or 8 digit code)
    - hsn_description: (category name)
    
    Do not include any other text or explanation. Only return the JSON array.
    """
    
    formatted_items = "\n".join([f"- {i.get('description', '')} (Current HSN: {i.get('hsn', 'None')})" for i in items])
    user_message = f"ITEMS TO MAP:\n{formatted_items}"
    
    response = await LLMService.generate_response(system_prompt, user_message)
    
    try:
        clean_json = response.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:-3].strip()
        elif clean_json.startswith("```"):
            clean_json = clean_json[3:-3].strip()
            
        mappings = json.loads(clean_json)
        
        # Merge back
        results = []
        mapping_dict = { m.get("description"): m for m in mappings }
        
        for item in items:
            desc = item.get("description")
            m = mapping_dict.get(desc, {})
            results.append({
                "description": desc,
                "original_hsn": item.get("hsn"),
                "suggested_hsn": str(m.get("hsn_code", "UNKNOWN")),
                "hsn_category": m.get("hsn_description", "Unknown Category")
            })
            
        return results
    except Exception as e:
        logger.error(f"Failed to parse HSN AI response: {e}\nResponse: {response}")
        return [{**item, "suggested_hsn": "ERROR", "hsn_category": "AI Parsing Failed"} for item in items]

async def process_hsn_plotter_job(input_bytes_list: List[bytes], filenames: List[str]) -> bytes:
    """
    Main entry point for HSN Plotter job.
    1. Read all PR/SR files.
    2. Extract unique item descriptions and their tax values.
    3. Use AI to map descriptions to HSN.
    4. Generate HSN-wise summary report.
    """
    all_dfs = []
    
    for i, file_bytes in enumerate(input_bytes_list):
        fname = filenames[i].lower()
        try:
            if fname.endswith('.csv'):
                df = pd.read_csv(io.BytesIO(file_bytes))
            else:
                df = pd.read_excel(io.BytesIO(file_bytes))
            
            # Normalize Headers
            df.columns = [str(c).strip().lower() for c in df.columns]
            all_dfs.append(df)
        except Exception as e:
            logger.error(f"Error reading file {filenames[i]} for HSN plotting: {e}")

    if not all_dfs:
        raise ValueError("No valid input files could be read.")

    # Combine all data
    # We need: Description, HSN (if exists), Taxable Value, Tax Rates
    combined_data = []
    for df in all_dfs:
        desc_col = next((c for c in df.columns if "desc" in c or "item" in c or "particular" in c), None)
        hsn_col = next((c for c in df.columns if "hsn" in c or "sac" in c), None)
        taxable_col = next((c for c in df.columns if "taxable" in c or "val" in c or "amount" in c), None)
        igst_col = next((c for c in df.columns if "igst" in c), None)
        cgst_col = next((c for c in df.columns if "cgst" in c), None)
        sgst_col = next((c for c in df.columns if "sgst" in c or "utgst" in c), None)

        if not desc_col or not taxable_col:
            continue

        for _, row in df.iterrows():
            combined_data.append({
                "description": str(row.get(desc_col, "")).strip(),
                "hsn": str(row.get(hsn_col, "None")).strip() if hsn_col else "None",
                "taxable_value": float(pd.to_numeric(row.get(taxable_col, 0), errors='coerce') or 0),
                "igst": float(pd.to_numeric(row.get(igst_col, 0), errors='coerce') or 0) if igst_col else 0,
                "cgst": float(pd.to_numeric(row.get(cgst_col, 0), errors='coerce') or 0) if cgst_col else 0,
                "sgst": float(pd.to_numeric(row.get(sgst_col, 0), errors='coerce') or 0) if sgst_col else 0,
            })

    if not combined_data:
        raise ValueError("Could not find required columns (Description, Taxable Value) in files.")

    full_df = pd.DataFrame(combined_data)
    
    # 2. Extract unique descriptions for AI mapping
    unique_items = full_df[["description", "hsn"]].drop_duplicates().to_dict('records')
    
    # Process in chunks
    chunk_size = 20
    all_mappings = []
    for i in range(0, len(unique_items), chunk_size):
        chunk = unique_items[i:i + chunk_size]
        mapped_chunk = await map_items_to_hsn_with_ai(chunk)
        all_mappings.extend(mapped_chunk)

    # 3. Apply mappings back
    mapping_lookup = { m["description"]: m for m in all_mappings }
    full_df["plotted_hsn"] = full_df["description"].map(lambda x: mapping_lookup.get(x, {}).get("suggested_hsn", "UNKNOWN"))
    full_df["hsn_description"] = full_df["description"].map(lambda x: mapping_lookup.get(x, {}).get("hsn_category", "Unknown"))

    # 4. Generate HSN Summary
    hsn_summary = full_df.groupby(["plotted_hsn", "hsn_description"]).agg({
        "taxable_value": "sum",
        "igst": "sum",
        "cgst": "sum",
        "sgst": "sum"
    }).reset_index()
    
    hsn_summary["total_tax"] = hsn_summary["igst"] + hsn_summary["cgst"] + hsn_summary["sgst"]

    # 5. Create Excel Report
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        hsn_summary.to_excel(writer, index=False, sheet_name="HSN Summary")
        full_df.to_excel(writer, index=False, sheet_name="Detailed Plotting")
        
        workbook = writer.book
        summary_sheet = writer.sheets["HSN Summary"]
        
        # Formats
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#059669', 'font_color': 'white', 'border': 1})
        num_fmt = workbook.add_format({'num_format': '#,##0.00'})

        for col_num, value in enumerate(hsn_summary.columns.values):
            summary_sheet.write(0, col_num, value, header_fmt)
            width = 25 if "description" in value.lower() else 15
            summary_sheet.set_column(col_num, col_num, width, num_fmt if col_num > 1 else None)

    return output.getvalue()
