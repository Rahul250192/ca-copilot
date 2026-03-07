
import pdfplumber
import logging

logging.basicConfig(level=logging.ERROR)

def dump_text(path):
    print(f"\n--- DUMPING RAW TEXT: {path} ---")
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text()
            print(f"[Page {i+1}]")
            print(text)
            print("-" * 50)

def main():
    files = [
        "/Users/rahulgupta/ca-copilot/uploads/FIRC-ICICI.pdf",
        "/Users/rahulgupta/ca-copilot/uploads/FIRC-HDFC.pdf"
    ]
    for f in files:
        try:
            dump_text(f)
        except Exception as e:
            print(f"Error reading {f}: {e}")

if __name__ == "__main__":
    main()
