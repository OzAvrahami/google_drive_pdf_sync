from app.parsers.pdf_parser import extract_text_from_pdf

pdf_path = r"D:\code\google_drive_pdf_sync\downloads\ינואר 2026\חשבוניות מס\חשונית מס סטודנט גרופ חודש ינואר_11813.pdf"

text = extract_text_from_pdf(pdf_path)

print(text[:1000])