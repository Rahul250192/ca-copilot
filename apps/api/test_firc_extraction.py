
import logging
import os
from app.services.gst.extract_firc_details import extract_firc_data, process_firc_pdfs_to_excel

# Setup logging
logging.basicConfig(level=logging.INFO)

def main():
    base_dir = "/Users/rahulgupta/ca-copilot/uploads"
    files = ["FIRC-ICICI.pdf", "FIRC-HDFC.pdf"]
    pdf_paths = []
    
    for fname in files:
        fpath = os.path.join(base_dir, fname)
        if not os.path.exists(fpath):
            print(f"File not found: {fpath}")
            continue
        pdf_paths.append(fpath)
            
        print(f"--- Testing Extraction for {fname} ---")
        try:
            data = extract_firc_data(fpath)
            print("Extracted Data:")
            print(data)
        except Exception as e:
            print(f"Error: {e}")
        print("\n")
        
    if pdf_paths:
        output_excel = "New_Statement.xlsx"  # Changed from Statement_FIRC_Test.xlsx
        print(f"--- Generating Excel: {output_excel} ---")
        try:
            process_firc_pdfs_to_excel(pdf_paths, output_excel)
            print(f"Excel generation successful! Check {os.path.abspath(output_excel)}")
        except Exception as e:
            print(f"Error generating Excel: {e}")

if __name__ == "__main__":
    main()
