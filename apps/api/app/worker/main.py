import time
import sys
import os
import io
import traceback
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.job import Job, JobStatus, JobType
from app.models.models import User
from app.services import storage 
from app.services.gst import process_zip_bytes, generate_annexure_b
from app.services.gst.extract_firc_details import process_statement3_workflow

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("worker")

# Setup Sync DB
# Convert async URL to sync (postgresql+asyncpg -> postgresql)
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL.replace("+asyncpg", "")
engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_job(db, job_id):
    return db.query(Job).filter(Job.id == job_id).first()

def run_worker():
    logger.info("Starting Worker...")
    
    while True:
        db = SessionLocal()
        try:
            # Poll for QUEUED job
            # Lock row using FOR UPDATE SKIP LOCKED if possible, but basic approach first
            job = db.query(Job).filter(Job.status == JobStatus.QUEUED).first()
            
            if not job:
                db.close()
                time.sleep(2)
                continue
            
            logger.info(f"Processing Job: {job.id} ({job.job_type})")
            
            # Update status to PROCESSING
            job.status = JobStatus.PROCESSING
            db.commit()
            
            input_files = job.input_files or []
            output_files = []
            
            try:
                # Dispatch Logic
                if job.job_type == JobType.STATEMENT3:
                    if len(input_files) < 1:
                        raise ValueError("Statement 3 requires at least 1 input file (Shipping ZIP)")
                    
                    # Intelligent File Assignment
                    ship_zip_path = None
                    brc_zip_path = None
                    
                    remaining = []
                    
                    for path in input_files:
                        lpath = path.lower()
                        if "brc" in lpath or "realisation" in lpath:
                            brc_zip_path = path
                        elif "ship" in lpath or "sb" in lpath or "bill" in lpath:
                            ship_zip_path = path
                        else:
                            remaining.append(path)
                            
                    # Fallback: Assign unclassified files
                    if not ship_zip_path and remaining:
                        ship_zip_path = remaining.pop(0) # Default first is Shipping
                    if not brc_zip_path and remaining:
                        brc_zip_path = remaining.pop(0) # Default second is BRC
                        
                    if not ship_zip_path:
                         raise ValueError("Could not identify a Shipping Bill ZIP file.")

                    # Download Input 1: Shipping Zip
                    temp_ship = storage.storage_service.download_to_temp(ship_zip_path)
                    if not temp_ship:
                        raise FileNotFoundError(f"Could not download {ship_zip_path}")
                    
                    with open(temp_ship, "rb") as f:
                        ship_bytes = f.read()
                    os.unlink(temp_ship)
                    
                    # Download Input 2: BRC Zip (Optional)
                    brc_bytes = None
                    if brc_zip_path:
                        temp_brc = storage.storage_service.download_to_temp(brc_zip_path)
                        if temp_brc:
                            with open(temp_brc, "rb") as f:
                                brc_bytes = f.read()
                            os.unlink(temp_brc)

                    # Execute
                    result_bytes = process_zip_bytes(ship_bytes, brc_bytes)
                    
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    # Upload Output - Hierarchical Structure
                    # Reports / <Firm ID> / <Client ID or 'General'> / Statement3_<Date>.xlsx
                    client_folder = job.client_id if job.client_id else "General"
                    output_key = f"Reports/{job.firm_id}/{client_folder}/Statement3_{timestamp}.xlsx"
                    
                    # storage.upload_file expects bytes
                    storage.storage_service.upload_file(
                        result_bytes, 
                        output_key, 
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    output_files.append(output_key)

                elif job.job_type == JobType.STATEMENT3_FIRC:
                    if len(input_files) < 2:
                        raise ValueError("Statement 3 (FIRC) requires 2 input files (Invoice ZIP and FIRC ZIP)")
                    
                    inv_path = None
                    firc_path = None
                    
                    # File Identification
                    # Strategy: Look for "invoice" in name, "firc" in name.
                    remaining = []
                    for p in input_files:
                        lp = p.lower()
                        if "invoice" in lp:
                            inv_path = p
                        elif "firc" in lp:
                            firc_path = p
                        else:
                            remaining.append(p)
                            
                    # Fallback: Assign remaining
                    if not inv_path and remaining: inv_path = remaining.pop(0)
                    if not firc_path and remaining: firc_path = remaining.pop(0)
                    
                    if not inv_path or not firc_path:
                        raise ValueError("Could not identify Invoice and FIRC ZIP files.")
                        
                    # Download
                    temp_inv = storage.storage_service.download_to_temp(inv_path)
                    if not temp_inv: raise FileNotFoundError(f"Missing {inv_path}")
                    with open(temp_inv, "rb") as f: inv_bytes = f.read()
                    os.unlink(temp_inv)
                    
                    temp_firc = storage.storage_service.download_to_temp(firc_path)
                    if not temp_firc: raise FileNotFoundError(f"Missing {firc_path}")
                    with open(temp_firc, "rb") as f: firc_bytes = f.read()
                    os.unlink(temp_firc)
                    
                    # Execute
                    result_bytes = process_statement3_workflow(inv_bytes, firc_bytes)
                    
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    client_folder = job.client_id if job.client_id else "General"
                    output_key = f"Reports/{job.firm_id}/{client_folder}/New_Statement_{timestamp}.xlsx"
                    
                    storage.storage_service.upload_file(
                        result_bytes, 
                        output_key, 
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    output_files.append(output_key)

                elif job.job_type == JobType.ANNEXURE_B:
                    if len(input_files) < 1:
                        raise ValueError("Annexure B requires at least 1 input file (GSTR2B Excel)")
                    
                    input_bytes_list = []
                    for path in input_files:
                        temp_path = storage.storage_service.download_to_temp(path)
                        if temp_path:
                            with open(temp_path, "rb") as f:
                                input_bytes_list.append(f.read())
                            os.unlink(temp_path)
                    
                    if not input_bytes_list:
                         raise ValueError("No valid input files downloaded")

                    import app.services.gst.annexure_b_generator as gen_mod
                    base_dir = os.path.dirname(gen_mod.__file__)
                    
                    result_bytes = generate_annexure_b(input_bytes_list, base_dir=base_dir)
                    
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    client_folder = job.client_id if job.client_id else "General"
                    output_key = f"Reports/{job.firm_id}/{client_folder}/AnnexureB_{timestamp}.xlsx"
                    
                    storage.storage_service.upload_file(
                        result_bytes, 
                        output_key, 
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    output_files.append(output_key)

                elif job.job_type == JobType.GST_VERIFY:
                    from app.services.gst import verify_gstins
                    
                    if len(input_files) < 1:
                        raise ValueError("GST Verification requires at least 1 input file (GSTR2B Excel)")
                        
                    # Download all files
                    input_bytes_list = []
                    for path in input_files:
                        temp_path = storage.storage_service.download_to_temp(path)
                        if temp_path:
                            with open(temp_path, "rb") as f:
                                input_bytes_list.append(f.read())
                            os.unlink(temp_path)
                            
                    if not input_bytes_list:
                         raise ValueError("No valid input files downloaded")
                         
                    # Execute
                    result_bytes = verify_gstins(input_bytes_list)
                    
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    client_folder = job.client_id if job.client_id else "General"
                    output_key = f"Reports/{job.firm_id}/{client_folder}/GST_Verify_{timestamp}.xlsx"
                    
                    storage.storage_service.upload_file(
                        result_bytes, 
                        output_key, 
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    output_files.append(output_key)
                
                    storage.storage_service.upload_file(
                        result_bytes, 
                        output_key, 
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    output_files.append(output_key)

                elif job.job_type == JobType.GST_RECON:
                    from app.services.gst import reconcile_gst
                    
                    if len(input_files) < 1:
                        raise ValueError("GST Reconciliation requires at least 1 input file (GSTR2B Excel)")
                        
                    input_bytes_list = []
                    for path in input_files:
                        temp_path = storage.storage_service.download_to_temp(path)
                        if temp_path:
                            with open(temp_path, "rb") as f:
                                input_bytes_list.append(f.read())
                            os.unlink(temp_path)
                            
                    if not input_bytes_list:
                         raise ValueError("No valid input files downloaded")
                         
                    result_bytes = reconcile_gst(input_bytes_list)
                    
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    client_folder = job.client_id if job.client_id else "General"
                    output_key = f"Reports/{job.firm_id}/{client_folder}/GST_Reconciliation_{timestamp}.xlsx"
                    
                    storage.storage_service.upload_file(
                        result_bytes, 
                        output_key, 
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    output_files.append(output_key)

                elif job.job_type == JobType.DOCUMENT_READER:
                    from app.services.gst.reader import process_document_reader_job
                    import asyncio
                    
                    if len(input_files) < 1:
                        raise ValueError("Document Reader requires at least 1 input file")
                        
                    # Download all files
                    input_bytes_list = []
                    filenames = []
                    for path in input_files:
                        temp_path = storage.storage_service.download_to_temp(path)
                        if temp_path:
                            filenames.append(os.path.basename(path))
                            with open(temp_path, "rb") as f:
                                input_bytes_list.append(f.read())
                            os.unlink(temp_path)
                            
                    if not input_bytes_list:
                         raise ValueError("No valid input files downloaded")
                    
                    # Get document type from metadata
                    doc_type = "invoice"
                    if job.metadata and isinstance(job.metadata, dict):
                        doc_type = job.metadata.get("document_type", "invoice")
                    
                    # Execute (Async)
                    result_bytes = asyncio.get_event_loop().run_until_complete(
                        process_document_reader_job(input_bytes_list, filenames, doc_type)
                    )
                    
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    client_folder = job.client_id if job.client_id else "General"
                    output_key = f"Reports/{job.firm_id}/{client_folder}/Extracted_{doc_type}_{timestamp}.xlsx"
                    
                    storage.storage_service.upload_file(
                        result_bytes, 
                        output_key, 
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    output_files.append(output_key)

                elif job.job_type == JobType.AI_BLOCK_CREDIT:
                    from app.services.gst.block_credit import process_block_credit_job
                    import asyncio
                    
                    if len(input_files) < 1:
                        raise ValueError("AI Block Credit requires at least 1 input file (Purchase Register)")
                        
                    # Download all files
                    input_bytes_list = []
                    filenames = []
                    for path in input_files:
                        temp_path = storage.storage_service.download_to_temp(path)
                        if temp_path:
                            filenames.append(os.path.basename(path))
                            with open(temp_path, "rb") as f:
                                input_bytes_list.append(f.read())
                            os.unlink(temp_path)
                            
                    if not input_bytes_list:
                         raise ValueError("No valid input files downloaded")
                    
                    # Execute (Async)
                    result_bytes = asyncio.get_event_loop().run_until_complete(
                        process_block_credit_job(input_bytes_list, filenames)
                    )
                    
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    client_folder = job.client_id if job.client_id else "General"
                    output_key = f"Reports/{job.firm_id}/{client_folder}/Blocked_Credit_Report_{timestamp}.xlsx"
                    
                    storage.storage_service.upload_file(
                        result_bytes, 
                        output_key, 
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    output_files.append(output_key)

                elif job.job_type == JobType.HSN_PLOTTER:
                    from app.services.gst.hsn_plotter import process_hsn_plotter_job
                    import asyncio
                    
                    if len(input_files) < 1:
                        raise ValueError("HSN Plotter requires at least 1 input file (PR or SR)")
                        
                    # Download all files
                    input_bytes_list = []
                    filenames = []
                    for path in input_files:
                        temp_path = storage.storage_service.download_to_temp(path)
                        if temp_path:
                            filenames.append(os.path.basename(path))
                            with open(temp_path, "rb") as f:
                                input_bytes_list.append(f.read())
                            os.unlink(temp_path)
                            
                    if not input_bytes_list:
                         raise ValueError("No valid input files downloaded")
                    
                    # Execute (Async)
                    result_bytes = asyncio.get_event_loop().run_until_complete(
                        process_hsn_plotter_job(input_bytes_list, filenames)
                    )
                    
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    
                    client_folder = job.client_id if job.client_id else "General"
                    output_key = f"Reports/{job.firm_id}/{client_folder}/HSN_Plotting_Report_{timestamp}.xlsx"
                    
                    storage.storage_service.upload_file(
                        result_bytes, 
                        output_key, 
                        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                    output_files.append(output_key)
                
                else:
                    raise NotImplementedError(f"Job Type {job.job_type} not implemented yet")

                # Success
                job.status = JobStatus.COMPLETED
                job.output_files = output_files
                db.commit()
                logger.info(f"Job {job.id} COMPLETED")

            except Exception as e:
                logger.error(f"Job {job.id} FAILED: {e}")
                traceback.print_exc()
                job.status = JobStatus.FAILED
                
                # Store error message in JobEvent for debugging
                from app.models.job import JobEvent
                error_event = JobEvent(
                    job_id=job.id,
                    level="ERROR",
                    message=str(e)
                )
                db.add(error_event)
                db.commit()
                
        except Exception as e:
            logger.error(f"Worker Loop Error: {e}")
            time.sleep(5)
        finally:
            db.close()

if __name__ == "__main__":
    run_worker()
