
import logging
import os
import zipfile
import glob
import tempfile
from io import BytesIO
from app.services.gst.extract_firc_details import process_statement3_workflow

# Setup logging
logging.basicConfig(level=logging.INFO)

def main():
    base_dir = "/Users/rahulgupta/ca-copilot/uploads"
    
    firc_files = [
        os.path.join(base_dir, "FIRC-ICICI.pdf"),
        os.path.join(base_dir, "FIRC-HDFC.pdf")
    ]
    
    # Create Invoice ZIP (using FIRC files as dummy inputs)
    inv_zip_path = os.path.join("/Users/rahulgupta/ca-copilot", "test_invoices.zip")
    with zipfile.ZipFile(inv_zip_path, "w") as z:
         z.write(firc_files[0], "1_Invoice.pdf")
         z.write(firc_files[1], "2_Invoice.pdf")
         
    # Create FIRC ZIP
    firc_zip_path = os.path.join("/Users/rahulgupta/ca-copilot", "test_fircs.zip")
    with zipfile.ZipFile(firc_zip_path, "w") as z:
         z.write(firc_files[0], "1_FIRC_ICICI.pdf")
         z.write(firc_files[1], "2_FIRC_HDFC.pdf")

    print(f"Created Zips: {inv_zip_path}, {firc_zip_path}")
    
    # Create Master ZIP for nested test
    master_zip_path = os.path.join("/Users/rahulgupta/ca-copilot", "master_test.zip")
    with zipfile.ZipFile(master_zip_path, "w") as z:
        z.write(inv_zip_path, "inner_invoices.zip")
        z.write(firc_zip_path, "inner_fircs.zip")
    print(f"Created Master Zip: {master_zip_path}")
    
    print("\n--- Test 1: Nested Master ZIP logic ---")
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            # Unzip master
            print(f"Unzipping master: {master_zip_path}")
            with zipfile.ZipFile(master_zip_path, 'r') as z:
                z.extractall(temp_dir)
            
            # Find inner
            inner_zips = sorted(glob.glob(os.path.join(temp_dir, "*.zip")))
            print(f"Found inner zips: {[os.path.basename(p) for p in inner_zips]}")
            
            if len(inner_zips) >= 2:
                # Identification logic
                i_path = None
                f_path = None
                rem = []
                for p in inner_zips:
                    lp = os.path.basename(p).lower()
                    if "invoice" in lp: i_path = p
                    elif "firc" in lp: f_path = p
                    else: rem.append(p)
                
                if not i_path and rem: i_path = rem.pop(0)
                if not f_path and rem: f_path = rem.pop(0)
                
                print(f"Identified: Inv={os.path.basename(i_path)}, FIRC={os.path.basename(f_path)}")
                
                with open(i_path, "rb") as f: ib = f.read()
                with open(f_path, "rb") as f: fb = f.read()
                
                excel_bytes = process_statement3_workflow(ib, fb)
                
                out_file = "Statement3_Nested_Test.xlsx"
                with open(out_file, "wb") as f: f.write(excel_bytes)
                print(f"Success! Generated {out_file}")
            else:
                print("Failed: Did not extract 2 zips")
                
    except Exception as e:
        print(f"Error in Nested Test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
