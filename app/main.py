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

def print_hierarchy(data):
    if not data:
        print("No subfolder found.")
        return
    
    for folder in data:
        print(f"\n📁 {folder['folder_name']}")

        if not folder["pdfs"]:
            print("   └── No PDF files found")
            continue
        
        for pdf in folder["pdfs"]:
            print(f"   └── {pdf['name']}")

if __name__ == "__main__":
    main()