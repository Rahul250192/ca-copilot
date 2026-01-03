import io
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import os

from extract_batch import process_zip_bytes
from annexure_b_generator import generate_annexure_b
from gst_master import get_rates

app = FastAPI(
    title="PDF to Excel Converter",
    description="Takes a ZIP of PDFs and returns a filled Statement-3 Excel.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten later if you want
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/convert-zip")
async def convert_zip(
    shipping_bills: UploadFile = File(...),
    brc_file: UploadFile = File(...)
):
    if not shipping_bills.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Shipping bills must be a .zip file")
    
    if not brc_file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="BRC must be a .zip file")

    shipping_bills_bytes = await shipping_bills.read()
    brc_bytes = await brc_file.read()

    try:
        # Update your process function to handle both files
        excel_bytes = process_zip_bytes(shipping_bills_bytes, brc_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="Statement_3_output.xlsx"'
        },
    )

from typing import List
from fastapi import UploadFile, File, HTTPException
from starlette.responses import StreamingResponse
import io
import os

@app.post("/generate-annexure-b")
async def generate_annexure_b_api(
    gstr2b_files: List[UploadFile] = File(...),
):
    # validate extensions
    for f in gstr2b_files:
        if not f.filename.lower().endswith((".xlsx", ".xlsm")):
            raise HTTPException(status_code=400, detail="All files must be .xlsx/.xlsm")

    # read all files into bytes list
    gstr_files_bytes = [await f.read() for f in gstr2b_files]

    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        # unified generator accepts list[bytes]
        out_bytes = generate_annexure_b(gstr2b_excel=gstr_files_bytes, base_dir=base_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Annexure B generation failed: {e}")

    return StreamingResponse(
        io.BytesIO(out_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="Annexure_b.xlsx"'},
    )

# NEW: master file path (keep the file in repo)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GST_MASTER_XLSX = os.getenv(
    "GST_MASTER_XLSX",
    os.path.join(BASE_DIR, "data", "HSN_GST_Master_Goods_Services_2025.xlsx"),
)


@app.get("/gst/rates")
def gst_rates(code: str = Query(..., description="HSN (2/4/6/8 digits) or SAC code")):
    """
    Example:
      /gst/rates?code=050790
      /gst/rates?code=0507
      /gst/rates?code=9983
    Returns: CGST, SGST, IGST, Cess + match metadata.
    """
    try:
        r = get_rates(code=code, xlsx_path="HSN_GST_Master_Goods_Services_2025.xlsx")
        return {
            "code": code,
            "matched_code": r.matched_code,
            "match_level": r.match_level,
            "source_sheet": r.source_sheet,
            "rates": {
                "cgst": r.cgst,
                "sgst": r.sgst,
                "igst": r.igst,
                "cess": r.cess,
            },
        }
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lookup failed: {e}")
