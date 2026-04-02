import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from config import GOOGLE_DRIVE_PARENT_FOLDER_ID, GOOGLE_SERVICE_ACCOUNT_FILE

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def get_drive_service():

    parent_folder_id = GOOGLE_DRIVE_PARENT_FOLDER_ID
    service_account_file = GOOGLE_SERVICE_ACCOUNT_FILE

    if not parent_folder_id or parent_folder_id == "your_parent_folder_id_here":
        raise ValueError("GOOGLE_DRIVE_PARENT_FOLDER_ID is missing or still set to placeholder value")

    if not service_account_file:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_FILE is missing")

    if not os.path.isabs(service_account_file):
        service_account_file = os.path.join(BASE_DIR, service_account_file)

    if not os.path.exists(service_account_file):
        raise FileNotFoundError(f"Service account file not found: {service_account_file}")

    credentials = service_account.Credentials.from_service_account_file(
        service_account_file,
        scopes=SCOPES
    )

    service = build("drive", "v3", credentials=credentials)
    return service, parent_folder_id


def list_subfolders(service, parent_folder_id):
    folders = []
    page_token = None

    while True:
        response = service.files().list(
            q=(
                f"'{parent_folder_id}' in parents "
                f"and mimeType = 'application/vnd.google-apps.folder' "
                f"and trashed = false"
            ),
            spaces="drive",
            fields="nextPageToken, files(id, name, createdTime, modifiedTime)",
            orderBy="name",
            pageSize=100,
            pageToken=page_token
        ).execute()

        folders.extend(response.get("files", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return folders


def list_pdfs_in_folder(service, folder_id):
    pdfs = []
    page_token = None

    while True:
        response = service.files().list(
            q=(
                f"'{folder_id}' in parents "
                f"and mimeType = 'application/pdf' "
                f"and trashed = false"
            ),
            spaces="drive",
            fields="nextPageToken, files(id, name, createdTime, modifiedTime)",
            orderBy="name",
            pageSize=100,
            pageToken=page_token
        ).execute()

        pdfs.extend(response.get("files", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return pdfs


def get_folder_pdf_hierarchy(service, parent_folder_id):
    result = []

    subfolders = list_subfolders(service, parent_folder_id)

    for folder in subfolders:
        folder_id = folder["id"]
        folder_name = folder["name"]

        pdfs = list_pdfs_in_folder(service, folder_id)

        result.append({
            "folder_id": folder_id,
            "folder_name": folder_name,
            "pdfs": [
                {
                    "id": pdf["id"],
                    "name": pdf["name"],
                    "createdTime": pdf.get("createdTime"),
                    "modifiedTime": pdf.get("modifiedTime"),
                }
                for pdf in pdfs
            ]
        })

    return result


def print_hierarchy(data):
    if not data:
        print("No subfolders found.")
        return

    for folder in data:
        print(f"\n📁 {folder['folder_name']} ({folder['folder_id']})")

        if not folder["pdfs"]:
            print("   └── No PDF files found")
            continue

        for pdf in folder["pdfs"]:
            print(f"   └── {pdf['name']} ({pdf['id']})")


def main():
    try:
        service, parent_folder_id = get_drive_service()
        hierarchy = get_folder_pdf_hierarchy(service, parent_folder_id)
        print_hierarchy(hierarchy)

    except HttpError as e:
        print(f"[GOOGLE API ERROR] {e}")
    except Exception as e:
        print(f"[ERROR] {e}")


if __name__ == "__main__":
    main()