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
    You are an expert Indian GST Compliance Auditor with deep knowledge of Section 17(5) of the CGST Act.
    Your task is to classify each purchase item's Input Tax Credit (ITC) eligibility.

    CLASSIFICATION:
    Use exactly one of these three statuses:
    - "BLOCKED"       — ITC is clearly blocked under Section 17(5). No ambiguity.
    - "ELIGIBLE"      — ITC is clearly eligible. Standard business input with no restrictions.
    - "NEEDS_REVIEW"  — ITC eligibility depends on conditions that cannot be determined from the description alone. Requires human verification.

    SECTION 17(5) — ITC IS BLOCKED ON:
    1. Motor vehicles and conveyances — BLOCKED, except when used for:
       (a) further supply of such vehicles, (b) transportation of passengers, (c) imparting training on driving/flying/navigating.
       → If vehicle purpose is ambiguous, mark NEEDS_REVIEW.
    2. Food, beverages, outdoor catering, beauty treatment, health services, cosmetic/plastic surgery
       — Always BLOCKED (unless provided as an output service by the taxpayer).
    3. Membership of club, health and fitness centre — Always BLOCKED.
    4. Rent-a-cab, life insurance, health insurance
       — BLOCKED, unless the employer is obligated under law to provide them to employees.
       → Mark as NEEDS_REVIEW with reason "Verify if statutory obligation exists".
    5. Travel benefits for employees on vacation (LTC/Home Travel) — Always BLOCKED.
       Travel for business purposes — ELIGIBLE but mark NEEDS_REVIEW with reason "Business Travel — verify employee purpose".
    6. Works contract for construction of immovable property — BLOCKED (except plant & machinery).
    7. Goods/services received for personal consumption — BLOCKED.
    8. Goods lost, stolen, destroyed, written off, or disposed as gift/samples — BLOCKED.

    IMPORTANT EDGE CASES (always follow these):
    - GTA (Goods Transport Agency) / Transport services (HSN 9965/9966):
      → If GST is charged by GTA on invoice (forward charge), ITC is ELIGIBLE.
      → If under RCM, ITC is eligible but mark NEEDS_REVIEW: "Transport of Goods — subject to RCM compliance verification".
      → Never mark simply as "Transport of Goods" without qualification.
    - Air tickets / Business travel (HSN 9964):
      → Mark NEEDS_REVIEW: "Business Travel — verify employee purpose & not personal/vacation".
    - Repairs to motor vehicles:
      → BLOCKED if for passenger vehicles, but ELIGIBLE if for goods vehicles.
      → Mark NEEDS_REVIEW: "Vehicle Repair — verify if goods carrier or passenger vehicle".
    - Insurance (HSN 9971):
      → Health/life insurance: BLOCKED unless statutory obligation. Mark NEEDS_REVIEW.
      → Property/cargo insurance: ELIGIBLE.
    - Gifts, samples, freebies:
      → Always BLOCKED: "Gifts/Samples — Section 17(5)(h)".
    - Construction / Renovation:
      → BLOCKED for immovable property. ELIGIBLE for plant & machinery.
      → Mark NEEDS_REVIEW: "Construction — verify if immovable property or plant & machinery".

    REASONING GUIDELINES:
    - NEVER use generic reasons like "Standard Business Input". Always be specific.
    - Good reasons: "Manufacturing Raw Material", "Office Supplies — operational input",
      "IT Services — business operations", "Professional Fees — compliance services".
    - For NEEDS_REVIEW, always explain WHAT needs to be verified.

    Return a JSON array of objects with keys: "status", "reason".
    Do not include any other text outside the JSON array.
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
        review_fmt = workbook.add_format({'bg_color': '#FEF3C7', 'font_color': '#92400E'})

        # Apply header format
        for col_num, value in enumerate(pr_df.columns.values):
            worksheet.write(0, col_num, value, header_fmt)
            worksheet.set_column(col_num, col_num, 18)

        # Highlight rows by status
        status_idx = list(pr_df.columns).index("itc_status")
        for row_num in range(len(pr_df)):
            status = str(pr_df.iloc[row_num, status_idx]).upper()
            if status == "BLOCKED":
                fmt = blocked_fmt
            elif status == "NEEDS_REVIEW":
                fmt = review_fmt
            else:
                fmt = eligible_fmt
            worksheet.set_row(row_num + 1, None, fmt)

        # ── Summary Sheet ──
        total = len(pr_df)
        blocked_count = len(pr_df[pr_df["itc_status"].str.upper() == "BLOCKED"])
        review_count = len(pr_df[pr_df["itc_status"].str.upper() == "NEEDS_REVIEW"])
        eligible_count = total - blocked_count - review_count

        summary_ws = workbook.add_worksheet("Summary")
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'font_color': '#1E3A8A'})
        label_fmt = workbook.add_format({'bold': True, 'font_size': 11, 'border': 1})
        val_fmt = workbook.add_format({'font_size': 11, 'border': 1, 'align': 'center'})

        summary_ws.set_column(0, 0, 30)
        summary_ws.set_column(1, 1, 15)
        summary_ws.write(0, 0, "AI Block Credit — Summary", title_fmt)
        summary_ws.write(2, 0, "Status", header_fmt)
        summary_ws.write(2, 1, "Count", header_fmt)
        summary_ws.write(3, 0, "✅ ELIGIBLE", label_fmt)
        summary_ws.write(3, 1, eligible_count, val_fmt)
        summary_ws.write(4, 0, "🔴 BLOCKED", label_fmt)
        summary_ws.write(4, 1, blocked_count, val_fmt)
        summary_ws.write(5, 0, "⚠️ NEEDS REVIEW", label_fmt)
        summary_ws.write(5, 1, review_count, val_fmt)
        summary_ws.write(6, 0, "Total Items", label_fmt)
        summary_ws.write(6, 1, total, val_fmt)

        # List items that need review
        if review_count > 0:
            summary_ws.write(8, 0, "Items Needing Review", title_fmt)
            summary_ws.write(9, 0, "Item", header_fmt)
            summary_ws.write(9, 1, "Reason", header_fmt)
            summary_ws.set_column(1, 1, 50)
            review_rows = pr_df[pr_df["itc_status"].str.upper() == "NEEDS_REVIEW"]
            for idx, (_, row) in enumerate(review_rows.iterrows()):
                summary_ws.write(10 + idx, 0, str(row.get(desc_col, "")), review_fmt)
                summary_ws.write(10 + idx, 1, str(row.get("blocking_reason", "")), review_fmt)

    return output.getvalue()
