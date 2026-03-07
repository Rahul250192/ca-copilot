
import logging
import os
from app.services.gst.extract_firc_details import process_statement3_workflow

# Setup logging
logging.basicConfig(level=logging.INFO)

def main():
    base_dir = "/Users/rahulgupta/ca-copilot/uploads"
    inv_zip = os.path.join(base_dir, "INVOICES.zip")
    firc_zip = os.path.join(base_dir, "FIRC-Q3.zip")
    
    if not os.path.exists(inv_zip) or not os.path.exists(firc_zip):
        print("Error: Missing ZIP files. Please ensure INVOICES.zip and FIRC-Q3.zip are in uploads/")
        return
        
    print(f"Processing Real Data:\nInvoices: {inv_zip}\nFIRCs: {firc_zip}")
    
    with open(inv_zip, "rb") as f:
        inv_bytes = f.read()
    with open(firc_zip, "rb") as f:
        firc_bytes = f.read()
        
    try:
        excel_bytes = process_statement3_workflow(inv_bytes, firc_bytes)
        
        # FINAL FILENAME: Statement3.xlsx
        out_file = "Statement3.xlsx" 
        with open(out_file, "wb") as f:
            f.write(excel_bytes)
            
        print(f"Success! Generated {os.path.abspath(out_file)}")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
