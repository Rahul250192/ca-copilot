
import openpyxl

def main():
    file_path = "/Users/rahulgupta/ca-copilot/uploads/Statement3-11.xlsx"
    try:
        wb = openpyxl.load_workbook(file_path)
        ws = wb.active # Assuming first sheet is relevant
        
        print(f"--- Headers for {file_path} ---")
        # Print first few rows to find header
        for i, row in enumerate(ws.iter_rows(values_only=True), 1):
            print(f"Row {i}: {row}")
            if i >= 15: # Headers likely within first 15 rows
                break
                
    except Exception as e:
        print(f"Error reading excel: {e}")

if __name__ == "__main__":
    main()
