import pypdf


def extract_pdf_text(pdf_path):
    """Extracts all plain text from a PDF file."""
    try:
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        print(f"❌ Error reading PDF {pdf_path}: {e}")
        return None

