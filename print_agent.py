import io
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
BATCHES = OUTPUT / "print_batches"
FACTORY = ROOT / "factory_print"

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def drive_service():
    token_path = ROOT / "token.json"
    if not token_path.exists():
        raise RuntimeError("token.json not found. Run discover.py and authorize Google Drive first.")

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")

    if not creds.valid:
        raise RuntimeError("Google Drive credentials are not valid.")

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def newest_queued_batch():
    if not BATCHES.exists():
        return None, None

    candidates = sorted(
        BATCHES.glob("*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )

    for path in candidates:
        batch = load_json(path)
        if batch.get("status") == "QUEUED":
            return path, batch

    return None, None


def safe_name(value):
    value = str(value or "").strip()
    for ch in '<>:"/\\|?*':
        value = value.replace(ch, "_")
    return value.rstrip(". ") or "unnamed"


def download_drive_file(service, file_id, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)

    with io.FileIO(destination, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request, chunksize=1024 * 1024 * 8)
        done = False
        while not done:
            status, done = downloader.next_chunk()
            if status:
                print(f"      {int(status.progress() * 100):3d}%", end="\r")
    print("      100%")


def main():
    batch_path, batch = newest_queued_batch()
    if not batch:
        print("No QUEUED print batch found.")
        return

    batch_id = batch["batch_id"]
    print(f"Preparing batch: {batch_id}")

    expected = int(batch.get("artwork_file_count") or 0)
    target = FACTORY / safe_name(batch_id)

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    service = drive_service()
    downloaded = []
    errors = []

    batch["status"] = "DOWNLOADING"
    batch["download_started_at"] = datetime.now(timezone.utc).isoformat()
    save_json(batch_path, batch)

    try:
        for order in batch.get("orders", []):
            order_name = safe_name(order.get("order"))
            for art in order.get("artworks", []):
                material = safe_name(art.get("material"))
                filename = safe_name(art.get("filename"))
                file_id = art.get("drive_file_id")

                dest = target / material / order_name / filename

                print(f"  {order.get('order')} | {art.get('side')} | {material}")
                print(f"    {filename}")

                try:
                    download_drive_file(service, file_id, dest)
                    if not dest.exists() or dest.stat().st_size <= 0:
                        raise RuntimeError("Downloaded file is empty")

                    downloaded.append({
                        "order": order.get("order"),
                        "side": art.get("side"),
                        "material": art.get("material"),
                        "drive_file_id": file_id,
                        "filename": art.get("filename"),
                        "local_path": str(dest),
                        "bytes": dest.stat().st_size,
                    })
                except Exception as e:
                    errors.append({
                        "order": order.get("order"),
                        "filename": art.get("filename"),
                        "drive_file_id": file_id,
                        "error": str(e),
                    })

        prepared = (len(downloaded) == expected and not errors)

        manifest = dict(batch)
        manifest["prepared_at"] = datetime.now(timezone.utc).isoformat()
        manifest["expected_artwork_files"] = expected
        manifest["downloaded_artwork_files"] = len(downloaded)
        manifest["downloads"] = downloaded
        manifest["errors"] = errors
        manifest["status"] = "PREPARED" if prepared else "FAILED"

        save_json(target / "manifest.json", manifest)

        batch["status"] = manifest["status"]
        batch["prepared_at"] = manifest["prepared_at"]
        batch["downloaded_artwork_files"] = len(downloaded)
        batch["errors"] = errors
        save_json(batch_path, batch)

        print()
        print("=== Factory Print Preparation ===")
        print(f"Batch     : {batch_id}")
        print(f"Expected  : {expected}")
        print(f"Downloaded: {len(downloaded)}")
        print(f"Status    : {manifest['status']}")
        print(f"Folder    : {target}")

        if errors:
            print("\nERRORS:")
            for err in errors:
                print(f"- {err['order']} | {err['filename']} | {err['error']}")
            sys.exit(1)

    except Exception as e:
        batch["status"] = "FAILED"
        batch["error"] = str(e)
        save_json(batch_path, batch)
        raise


if __name__ == "__main__":
    main()
