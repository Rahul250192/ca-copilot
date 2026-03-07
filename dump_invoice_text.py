
import zipfile
import pdfplumber
import os
from io import BytesIO

def main():
    zip_path = "/Users/rahulgupta/ca-copilot/uploads/INVOICES.zip"
    
    with zipfile.ZipFile(zip_path, 'r') as z:
        # List files
        files = [f for f in z.namelist() if f.lower().endswith('.pdf')]
        if not files:
            print("No PDFs found in zip")
            return
            
        # Pick one
        target_file = files[0]
        print(f"--- Dumping text for {target_file} ---")
        
        with z.open(target_file) as f:
            with pdfplumber.open(f) as pdf:
                text = pdf.pages[0].extract_text()
                print(text)

if __name__ == "__main__":
    main()
