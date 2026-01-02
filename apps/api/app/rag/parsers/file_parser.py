import os
import pdfplumber
import pandas as pd

class FileParser:
    def parse(self, file_path: str, content_type: str = "text/plain") -> str:
        """Parse file content to text."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".pdf":
            return self._parse_pdf(file_path)
        elif ext in [".xlsx", ".xls"]:
            return self._parse_excel(file_path)
        else:
            return self._parse_text(file_path)

    def _parse_pdf(self, path: str) -> str:
        text_parts = []
        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text_parts.append(page.extract_text() or "")
            return "\n".join(text_parts)
        except Exception as e:
            print(f"Error parsing PDF: {e}")
            return ""

    def _parse_excel(self, path: str) -> str:
        try:
            # Read all sheets
            df_dict = pd.read_excel(path, sheet_name=None)
            text_parts = []
            for sheet_name, df in df_dict.items():
                text_parts.append(f"Sheet: {sheet_name}")
                text_parts.append(df.to_string(index=False))
            return "\n".join(text_parts)
        except Exception as e:
            print(f"Error parsing Excel: {e}")
            return ""

    def _parse_text(self, path: str) -> str:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

