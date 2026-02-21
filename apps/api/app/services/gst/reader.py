import io
import os
import pandas as pd
import pdfplumber
import logging
import json
import asyncio
from typing import List, Dict, Any, Optional
from app.services.llm import LLMService

# Setup Logging
logger = logging.getLogger("document_reader")

try:
    import pytesseract
    from PIL import Image
    HAS_PYTESSERACT = True
except ImportError:
    HAS_PYTESSERACT = False

def extract_text(file_bytes: bytes, filename: str) -> str:
    """
    Extract text from PDF or Image.
    """
    ext = os.path.splitext(filename)[1].lower()
    text = ""
    
    if ext == ".pdf":
        try:
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages[:3]: # Limit to first 3 pages
                    text += page.extract_text() or ""
                    text += "\n"
        except Exception as e:
            logger.error(f"Error reading PDF {filename}: {e}")
            
    elif ext in [".jpg", ".jpeg", ".png"]:
        if HAS_PYTESSERACT:
            try:
                # Basic OCR
                img = Image.open(io.BytesIO(file_bytes))
                text = pytesseract.image_to_string(img)
            except Exception as e:
                logger.warning(f"OCR Failed for {filename}: {e}")
        else:
            logger.warning(f"Skipping OCR for {filename}: pytesseract not installed.")
            
    return text

async def extract_data_with_ai(text: str, doc_type: str) -> Dict[str, Any]:
    """
    Use LLM to parse extracted text into structured JSON.
    """
    if not text.strip():
        return {"error": "No text extracted from document"}

    system_prompt = f"""
    You are an expert Indian GST Compliance Assistant. 
    Your task is to extract key data fields from the provided text of a {doc_type.upper()} document.
    Return ONLY a valid JSON object. Do not include any explanation or markdown formatting.
    
    Expected fields based on document type:
    - INVOICE: invoice_no, date, value, currency, gstin_supplier, gstin_buyer
    - FIRC/BRC: firc_no, date, amount, currency, bank_name, beneficiary_name
    - SHIPPING_BILL: sb_no, date, port_code, invoice_no, firc_no
    - CSB (Courier Shipping Bill): csb_no, date, hawb_no, value
    
    If a field is not found, use null.
    Format dates as DD/MM/YYYY.
    """
    
    user_message = f"DOCUMENT TEXT:\n{text}"
    
    response = await LLMService.generate_response(system_prompt, user_message)
    
    try:
        # Clean up possible markdown code blocks
        clean_json = response.strip()
        if clean_json.startswith("```json"):
            clean_json = clean_json[7:-3].strip()
        elif clean_json.startswith("```"):
            clean_json = clean_json[3:-3].strip()
            
        return json.loads(clean_json)
    except Exception as e:
        logger.error(f"Failed to parse AI response: {e}\nResponse: {response}")
        return {"error": "Failed to parse data", "raw_response": response[:200]}

async def process_document_reader_job(input_bytes_list: List[bytes], filenames: List[str], doc_type: str) -> bytes:
    """
    Main entry point for the document reader worker job.
    Processes all files and returns a summary Excel.
    """
    results = []
    
    for i, file_bytes in enumerate(input_bytes_list):
        fname = filenames[i] if i < len(filenames) else f"doc_{i}"
        logger.info(f"Processing {fname} as {doc_type}")
        
        # 1. Extract Text
        text = extract_text(file_bytes, fname)
        
        # 2. Extract Data via AI
        data = await extract_data_with_ai(text, doc_type)
        data["filename"] = fname
        results.append(data)
        
    # 3. Create Excel Summary
    df = pd.DataFrame(results)
    
    # Reorder columns to put filename first
    cols = ["filename"] + [c for c in df.columns if c != "filename"]
    df = df[cols]
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name="Extracted Data")
        
        # Formatting
        workbook = writer.book
        worksheet = writer.sheets["Extracted Data"]
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            worksheet.set_column(col_num, col_num, 20)

    return output.getvalue()
