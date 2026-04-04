from clients.drive_client import get_drive_service, get_folder_pdf_hierarchy

def main():
    try:
        # 1. Connection to google drive
        service, parent_folder_id = get_drive_service()

        # 2. 
        hierarchy = get_folder_pdf_hierarchy(service, parent_folder_id)

        # 3. 
        print_hierarchy(hierarchy)

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