from app.parsers.pdf_parser import extract_text_from_pdf

pdf_path = r"D:\code\google_drive_pdf_sync\downloads\פברואר 2026\חשבון עסקה בגין ינואר\חשבון עסקה ינואר- מורן מנצור.pdf"

text = extract_text_from_pdf(pdf_path)

print(text[:1000])