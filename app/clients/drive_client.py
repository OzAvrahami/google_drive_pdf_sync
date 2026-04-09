import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from app.config import GOOGLE_DRIVE_PARENT_FOLDER_ID, GOOGLE_SERVICE_ACCOUNT_FILE

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def get_drive_service():

    parent_folder_id = GOOGLE_DRIVE_PARENT_FOLDER_ID
    service_account_file = GOOGLE_SERVICE_ACCOUNT_FILE

    if not parent_folder_id or parent_folder_id == "your_parent_folder_id_here":
        raise ValueError("GOOGLE_DRIVE_PARENT_FOLDER_ID is missing or still set to placeholder value")

    if not service_account_file:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_FILE is missing")

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


def _collect_pdfs_recursive(service, folder_id, folder_path, visited):
    """
    Recursively collect all PDF records under folder_id at any depth.

    folder_path is the slash-joined path from the traversal root to the
    current folder (empty string for the root folder itself).
    visited guards against traversal loops caused by Drive shortcuts.

    Returns a flat list of PDF record dicts.
    """
    if folder_id in visited:
        return []
    visited.add(folder_id)

    records = []

    for pdf in list_pdfs_in_folder(service, folder_id):
        records.append({
            "id": pdf["id"],
            "name": pdf["name"],
            "folder_id": folder_id,
            "folder_path": folder_path,
            "createdTime": pdf.get("createdTime"),
            "modifiedTime": pdf.get("modifiedTime"),
        })

    for subfolder in list_subfolders(service, folder_id):
        child_path = (
            f"{folder_path}/{subfolder['name']}" if folder_path else subfolder["name"]
        )
        records.extend(
            _collect_pdfs_recursive(service, subfolder["id"], child_path, visited)
        )

    return records


def get_folder_pdf_hierarchy(service, parent_folder_id):
    """
    Return a flat list of all PDF records found under parent_folder_id,
    at any nesting depth.

    Each record contains:
        id, name, folder_id, folder_path, createdTime, modifiedTime

    folder_path is relative to parent_folder_id (empty string means the
    PDF lives directly inside the root folder).
    """
    return _collect_pdfs_recursive(service, parent_folder_id, "", set())


def print_hierarchy(records):
    if not records:
        print("No PDF files found.")
        return

    for pdf in records:
        location = pdf["folder_path"] or "(root)"
        print(f"   [{location}] {pdf['name']} ({pdf['id']})")


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