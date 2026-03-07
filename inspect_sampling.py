
import openpyxl
import os

def main():
    file_path = "apps/api/app/services/gst/Statement_sampling.xlsx"
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found")
        return
        
    try:
        wb = openpyxl.load_workbook(file_path)
        ws = wb["Statement 3"]
        
        print(f"--- Headers for {file_path} ---")
        for i, row in enumerate(ws.iter_rows(values_only=True), 1):
            print(f"Row {i}: {row}")
            if i >= 15:
                break
                
    except Exception as e:
        print(f"Error reading excel: {e}")

if __name__ == "__main__":
    main()
