import os
from clients.drive_client import get_drive_service, get_folder_pdf_hierarchy

# TEMP: set to True to download all discovered PDFs locally for validation.
# Point DOWNLOAD_DIR at any writable path; folder_path structure is recreated there.
_DOWNLOAD_FOR_VALIDATION = True #False
_DOWNLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "downloads")


def main():
    try:
        # 1. Authenticate and connect
        service, parent_folder_id = get_drive_service()

        # 2. Recursively discover all PDFs under the configured root folder
        hierarchy = get_folder_pdf_hierarchy(service, parent_folder_id)

        # 3. Display discovered files
        print_hierarchy(hierarchy)

        # TEMP: optional local download for validation
        if _DOWNLOAD_FOR_VALIDATION:
            from utils.pdf_downloader import download_pdfs
            download_pdfs(service, hierarchy, _DOWNLOAD_DIR)

    except Exception as e:
        print(f"[ERROR] {e}")

def print_hierarchy(records):
    if not records:
        print("No PDF files found.")
        return

    for pdf in records:
        location = pdf["folder_path"] or "(root)"
        print(f"   [{location}] {pdf['name']}")

if __name__ == "__main__":
    main()