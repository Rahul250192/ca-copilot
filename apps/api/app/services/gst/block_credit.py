import io
import os
import pandas as pd
import logging
import json
import asyncio
from typing import List, Dict, Any, Optional
from app.services.llm import LLMService

# Setup Logging
logger = logging.getLogger("block_credit")

async def analyze_items_with_ai(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Use LLM to identify blocked credits in a batch of items.
    """
    if not items:
        return []

    system_prompt = """
    You are an expert Indian GST Compliance Auditor.
    Your task is to analyze a list of purchase items and determine if the Input Tax Credit (ITC) is 'BLOCKED' or 'ELIGIBLE' under Section 17(5) of the CGST Act.
    
    Section 17(5) Blocks ITC on:
    1. Motor vehicles (except if used for transport of goods, or further supply of vehicles, or training).
    2. Food and beverages, outdoor catering, beauty treatment, health services, cosmetic and plastic surgery.
    3. Membership of a club, health and fitness centre.
    4. Rent-a-cab, life insurance and health insurance.
    5. Travel benefits to employees (LTC/Home Travel).
    6. Works contract services for construction of immovable property (except plant and machinery).
    7. Goods/services for personal consumption.
    8. Goods lost, stolen, destroyed, written off or given as gifts/samples.
    
    For each item, return:
    - status: "BLOCKED" or "ELIGIBLE"
    - reason: A short explanation (e.g., "Food & Beverages", "Personal Consumption", "Standard Business Input")
    
    Return a JSON array of objects with these keys. Do not include any other text.
    """
    
    formatted_items = "\n".join([f"- {i.get('description', '')} (HSN: {i.get('hsn', '')})" for i in items])
    user_message = f"ITEMS TO ANALYZE:\n{formatted_items}"
    
    response = await LLMService.generate_response(system_prompt, user_message)
    
    try:
        clean_json = response.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:-3].strip()
        elif clean_json.startswith("```"):
            clean_json = clean_json[3:-3].strip()
            
        classifications = json.loads(clean_json)
        
        # Merge back
        for i, cls in enumerate(classifications):
            if i < len(items):
                items[i]["itc_status"] = cls.get("status", "UNKNOWN")
                items[i]["blocking_reason"] = cls.get("reason", "Analysis failed")
        
        return items
    except Exception as e:
        logger.error(f"Failed to parse AI response: {e}\nResponse: {response}")
        for item in items:
            item["itc_status"] = "ERROR"
            item["blocking_reason"] = "AI Parsing Failed"
        return items

async def process_block_credit_job(input_bytes_list: List[bytes], filenames: List[str]) -> bytes:
    """
    Main entry point for AI Block Credit job.
    1. Identify PR (Purchase Register) from files.
    2. Parse Excel/CSV.
    3. Extract item descriptions and HSNs.
    4. Batch process with AI.
    5. Generate a report.
    """
    pr_df = None
    
    # 1. Find the Purchase Register
    for i, file_bytes in enumerate(input_bytes_list):
        fname = filenames[i].lower()
        if "purchase" in fname or "pr" in fname or len(input_bytes_list) == 1:
            try:
                if fname.endswith('.csv'):
                    pr_df = pd.read_csv(io.BytesIO(file_bytes))
                else:
                    pr_df = pd.read_excel(io.BytesIO(file_bytes))
                break
            except Exception as e:
                logger.error(f"Error reading file {filenames[i]}: {e}")

    if pr_df is None:
        raise ValueError("Could not identify or read a valid Purchase Register file.")

    # 2. Normalize Headers (Simple heuristic)
    pr_df.columns = [str(c).strip().lower() for c in pr_df.columns]
    
    desc_col = next((c for c in pr_df.columns if "desc" in c or "item" in c or "particular" in c), None)
    hsn_col = next((c for c in pr_df.columns if "hsn" in c or "sac" in c), None)
    amount_col = next((c for c in pr_df.columns if "val" in c or "amt" in c or "taxable" in c), None)

    if not desc_col:
        raise ValueError("Could not find an 'Item Description' column in the Purchase Register.")

    # 3. Prepare Batch for AI
    # Limit to top 50 items for demonstration/speed if needed, or process all in batches
    items_to_process = []
    # Drop duplicates to save tokens
    unique_items = pr_df[[desc_col, hsn_col] if hsn_col else [desc_col]].drop_duplicates().head(100).to_dict('records')
    
    for row in unique_items:
        items_to_process.append({
            "description": row.get(desc_col),
            "hsn": row.get(hsn_col) if hsn_col else None
        })

    # 4. Execute AI Analysis
    # Process in chunks of 20
    chunk_size = 20
    all_classified = []
    for i in range(0, len(items_to_process), chunk_size):
        chunk = items_to_process[i:i + chunk_size]
        classified_chunk = await analyze_items_with_ai(chunk)
        all_classified.extend(classified_chunk)

    # 5. Map back to original dataframe
    class_map = { (item["description"], item["hsn"]): (item["itc_status"], item["blocking_reason"]) for item in all_classified }
    
    def get_status(row):
        d = row.get(desc_col)
        h = row.get(hsn_col) if hsn_col else None
        return class_map.get((d, h), ("ELIGIBLE", "General Input"))[0]
        
    def get_reason(row):
        d = row.get(desc_col)
        h = row.get(hsn_col) if hsn_col else None
        return class_map.get((d, h), ("ELIGIBLE", "General Input"))[1]

    pr_df["itc_status"] = pr_df.apply(get_status, axis=1)
    pr_df["blocking_reason"] = pr_df.apply(get_reason, axis=1)

    # 6. Generate Excel Report
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        pr_df.to_excel(writer, index=False, sheet_name="Blocked Credit Report")
        
        workbook = writer.book
        worksheet = writer.sheets["Blocked Credit Report"]
        
        # Formats
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#1E3A8A', 'font_color': 'white', 'border': 1})
        blocked_fmt = workbook.add_format({'bg_color': '#FEE2E2', 'font_color': '#991B1B'})
        eligible_fmt = workbook.add_format({'bg_color': '#DCFCE7', 'font_color': '#166534'})

        # Apply header format
        for col_num, value in enumerate(pr_df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            worksheet.set_column(col_num, col_num, 15)

        # Highlight Blocked Rows
        status_idx = list(pr_df.columns).index("itc_status")
        for row_num in range(len(pr_df)):
            status = pr_df.iloc[row_num, status_idx]
            fmt = blocked_fmt if status == "BLOCKED" else eligible_fmt
            worksheet.set_row(row_num + 1, None, fmt)

    return output.getvalue()
