from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def load_config() -> tuple[str, str]:
    """
    Loads required configuration from .env.
    Returns:
        tuple[str, str]: (parent_folder_id, service_account_file)
    """
    load_dotenv()

    parent_folder_id = os.getenv("GOOGLE_DRIVE_PARENT_FOLDER_ID", "").strip()
    service_account_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()

    if not parent_folder_id:
        raise ValueError("Missing GOOGLE_DRIVE_PARENT_FOLDER_ID in .env")
    
    if not service_account_file:
        raise ValueError("Missing GOOGLE_SERVICE_ACCOUNT_FILE in .env")
    
    if not Path(service_account_file).exists():
        raise FileNotFoundError(
            f"Service account file not found: {service_account_file}"
        )
    
    return parent_folder_id, service_account_file

def create_drive_service(service_account_file: str):
    """
    Creates an authenticated Google Drive API service.
    """
    credentials = Credentials.from_service_account_file(
        service_account_file,
        scopes=SCOPES
    )

    service = build("drive", "v3", credentials=credentials)
    return service

def get_subfolders(service, parent_folder_id: str) -> list[dict]:
    """
    Returns all immediate subfolders under the given parent folder.
    """
    query = (
        f"'{parent_folder_id}' in parents "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )

    subfolders: list[dict] = []
    page_token = None

    while True:
        response = (
            service.files()
            .list(
                q=query,
                spaces="drive",
                fields="nextPageToken, files(id, name, createdTime, modifiedTime)",
                orderBy="name",
                pageSize=100,
                pageToken=page_token,
            )
            .execute()
        )

        subfolders.extend(response.get("files", []))
        page_token = response.get("nextPageToken")

        if not page_token:
            break

    return subfolders


def print_subfolders(subfolders: list[dict]) -> None:
    """
    Prints folder details in a readable format.
    """
    if not subfolders:
        print("No subfolders found.")
        return

    print(f"Found {len(subfolders)} subfolder(s):\n")

    for index, folder in enumerate(subfolders, start=1):
        print(f"{index}. {folder.get('name', 'Unnamed Folder')}")
        print(f"   ID: {folder.get('id', '-')}")
        print(f"   Created: {folder.get('createdTime', '-')}")
        print(f"   Modified: {folder.get('modifiedTime', '-')}")
        print()


def main() -> int:
    try:
        parent_folder_id, service_account_file = load_config()
        service = create_drive_service(service_account_file)
        subfolders = get_subfolders(service, parent_folder_id)
        print_subfolders(subfolders)
        return 0

    except FileNotFoundError as exc:
        print(f"[ERROR] {exc}")
        return 1

    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    except HttpError as exc:
        print(f"[GOOGLE API ERROR] {exc}")
        return 1

    except Exception as exc:
        print(f"[UNEXPECTED ERROR] {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
