import pypdf
import sys

def extract_text(pdf_path):
    try:
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        # Use print with encoding to avoid charmap errors
        sys.stdout.reconfigure(encoding='utf-8')
        print(text)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    extract_text(sys.argv[1])
