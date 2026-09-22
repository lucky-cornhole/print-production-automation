from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import shutil
import signal
import sys
import time

from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


HERE = Path(__file__).resolve().parent

load_dotenv(HERE / ".env")

VERSION = (HERE / "VERSION").read_text().strip()

BASE = os.getenv(
    "PRODUCTION_API",
    "http://127.0.0.1:8000/api",
).rstrip("/")

KEY = os.getenv("FACTORY_API_KEY", "").strip()

CREDS = Path(
    os.getenv(
        "GOOGLE_SERVICE_ACCOUNT_FILE",
        str(HERE / "service-account.json"),
    )
)

OUT = Path(
    os.getenv(
        "FACTORY_PRINT_DIR",
        str(HERE / "factory_print"),
    )
)

HOT = os.getenv(
    "EDGE_PRINT_HOT_FOLDER",
    "",
).strip()

POLL = max(
    10,
    int(os.getenv("POLL_SECONDS", "30")),
)

RETENTION = max(
    1,
    int(os.getenv("LOCAL_RETENTION_HOURS", "72")),
)

REQ_VER = os.getenv(
    "REQUIRED_AGENT_VERSION",
    "",
).strip()

REQ_SHA = os.getenv(
    "REQUIRED_AGENT_SHA256",
    "",
).strip().lower()

HEAD = {
    "Authorization": f"Bearer {KEY}",
    "Accept": "application/json",
}

STOP = False


(HERE / "logs").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(
            HERE / "logs/factory-agent.log",
            encoding="utf-8",
        ),
        logging.StreamHandler(),
    ],
)

log = logging.getLogger("factory-agent")


def sig(*_):
    global STOP
    STOP = True


signal.signal(signal.SIGINT, sig)
signal.signal(signal.SIGTERM, sig)


def sha(path):
    h = hashlib.sha256()

    with open(path, "rb") as f:
        for chunk in iter(
            lambda: f.read(1048576),
            b"",
        ):
            h.update(chunk)

    return h.hexdigest()


def integrity():
    if not KEY:
        raise RuntimeError(
            "FACTORY_API_KEY is not configured"
        )

    if not CREDS.exists():
        raise RuntimeError(
            f"Service account missing: {CREDS}"
        )

    if REQ_VER and VERSION != REQ_VER:
        raise RuntimeError(
            "AGENT UPDATE REQUIRED: "
            f"installed={VERSION}, required={REQ_VER}"
        )

    if REQ_SHA and sha(__file__) != REQ_SHA:
        raise RuntimeError(
            "AGENT UPDATE REQUIRED: checksum mismatch"
        )


def api(method, path, **kwargs):
    response = requests.request(
        method,
        BASE + path,
        headers=HEAD,
        timeout=60,
        **kwargs,
    )

    response.raise_for_status()

    return (
        response.json()
        if response.content
        else {}
    )


def status(batch_id, new_status):
    log.info(
        "Batch %s -> %s",
        batch_id,
        new_status,
    )

    api(
        "POST",
        f"/factory/batches/{batch_id}/status",
        json={"status": new_status},
    )


def next_batch():
    return api(
        "GET",
        "/factory/batches/next",
    ).get("batch")


def drive():
    credentials = (
        service_account
        .Credentials
        .from_service_account_file(
            str(CREDS),
            scopes=[
                "https://www.googleapis.com/auth/drive.readonly"
            ],
        )
    )

    return build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def safe(value):
    value = str(value or "")

    for char in '<>:"/\\|?*':
        value = value.replace(char, "_")

    return (
        value.strip().rstrip(".")
        or "artwork"
    )


def download(service, file_id, destination):
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    request = service.files().get_media(
        fileId=file_id
    )

    with io.FileIO(
        destination,
        "wb",
    ) as handle:

        downloader = MediaIoBaseDownload(
            handle,
            request,
        )

        done = False

        while not done:
            _, done = downloader.next_chunk()


def batch_folder(batch):
    return OUT / safe(batch["batch_id"])


def prepare(batch):
    database_id = batch["id"]
    batch_id = batch["batch_id"]
    payload = batch["payload"]

    folder = batch_folder(batch)

    status(database_id, "CLAIMED")
    status(database_id, "DOWNLOADING")

    service = drive()

    expected = sum(
        len(order.get("artworks", []))
        for order in payload.get("orders", [])
    )

    count = 0

    try:
        for order in payload.get("orders", []):
            for artwork in order.get(
                "artworks",
                [],
            ):
                material = safe(
                    artwork.get("material")
                    or "Unassigned"
                )

                name = safe(
                    f"{str(order.get('order', '')).replace('#', '')}_"
                    f"{order.get('series_code', '')}_"
                    f"{artwork.get('side', 'PRINT')}_"
                    f"{artwork.get('filename', 'artwork')}"
                )

                log.info(
                    "Downloading %s | %s | %s",
                    order.get("order"),
                    material,
                    artwork.get("side"),
                )

                destination = (
                    folder
                    / material
                    / name
                )

                download(
                    service,
                    artwork["drive_file_id"],
                    destination,
                )

                count += 1

        folder.mkdir(
            parents=True,
            exist_ok=True,
        )

        manifest = {
            "agent_version": VERSION,
            "prepared_at": (
                datetime.now(timezone.utc)
                .isoformat()
            ),
            "expected_artwork_files": expected,
            "downloaded_artwork_files": count,
            "batch": payload,
        }

        (
            folder / "batch.json"
        ).write_text(
            json.dumps(
                manifest,
                indent=2,
            ),
            encoding="utf-8",
        )

        if count != expected:
            raise RuntimeError(
                f"Artwork mismatch "
                f"{count}/{expected}"
            )

        status(
            database_id,
            "PREPARED",
        )

        log.info(
            "PREPARED %s: %d/%d files",
            batch_id,
            count,
            expected,
        )

    except Exception:
        try:
            status(
                database_id,
                "FAILED",
            )
        except Exception:
            pass

        raise


def verify_prepared_batch(batch):
    folder = batch_folder(batch)
    manifest_path = folder / "batch.json"

    if not folder.exists():
        raise RuntimeError(
            "Prepared batch folder is missing: "
            f"{folder}"
        )

    if not manifest_path.exists():
        raise RuntimeError(
            "Prepared batch manifest is missing: "
            f"{manifest_path}"
        )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    expected = int(
        manifest.get(
            "expected_artwork_files",
            0,
        )
    )

    artwork_files = [
        path
        for path in folder.rglob("*")
        if (
            path.is_file()
            and path.name != "batch.json"
            and not path.name.startswith(".")
        )
    ]

    if len(artwork_files) != expected:
        raise RuntimeError(
            "Prepared artwork mismatch: "
            f"{len(artwork_files)}/{expected}"
        )

    return folder, artwork_files


def handoff(batch):
    database_id = batch["id"]
    batch_id = batch["batch_id"]

    if not HOT:
        raise RuntimeError(
            "EDGE_PRINT_HOT_FOLDER "
            "is not configured"
        )

    hot_folder = Path(HOT)

    hot_folder.mkdir(
        parents=True,
        exist_ok=True,
    )

    try:
        folder, artwork_files = (
            verify_prepared_batch(batch)
        )

        handoff_manifest = []

        for source in artwork_files:
            relative = source.relative_to(
                folder
            )

            material = (
                relative.parts[0]
                if len(relative.parts) > 1
                else "Unassigned"
            )

            destination_name = safe(
                f"{batch_id}_"
                f"{material}_"
                f"{source.name}"
            )

            destination = (
                hot_folder
                / destination_name
            )

            if destination.exists():
                if sha(source) == sha(destination):
                    log.info(
                        "Already handed off: %s",
                        destination.name,
                    )
                else:
                    raise RuntimeError(
                        "Edge Print destination "
                        "already exists with "
                        "different content: "
                        f"{destination}"
                    )
            else:
                temp_destination = (
                    hot_folder
                    / (
                        destination.name
                        + ".lbtmp"
                    )
                )

                shutil.copy2(
                    source,
                    temp_destination,
                )

                if sha(source) != sha(
                    temp_destination
                ):
                    temp_destination.unlink(
                        missing_ok=True
                    )

                    raise RuntimeError(
                        "Checksum mismatch while "
                        "copying to Edge Print: "
                        f"{source.name}"
                    )

                temp_destination.replace(
                    destination
                )

                log.info(
                    "Edge Print handoff: %s",
                    destination.name,
                )

            handoff_manifest.append({
                "source": str(source),
                "destination": str(destination),
                "sha256": sha(source),
            })

        (
            folder
            / "edgeprint-handoff.json"
        ).write_text(
            json.dumps(
                {
                    "agent_version": VERSION,
                    "batch_id": batch_id,
                    "sent_at": (
                        datetime.now(timezone.utc)
                        .isoformat()
                    ),
                    "hot_folder": str(
                        hot_folder
                    ),
                    "files": handoff_manifest,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        status(
            database_id,
            "SENT_TO_RIP",
        )

        log.info(
            "SENT_TO_RIP %s: %d files",
            batch_id,
            len(artwork_files),
        )

    except Exception:
        try:
            status(
                database_id,
                "FAILED",
            )
        except Exception:
            pass

        raise


def cleanup():
    if not OUT.exists():
        return

    cutoff = (
        datetime.now(timezone.utc)
        - timedelta(hours=RETENTION)
    )

    for directory in OUT.iterdir():
        marker = directory / ".printed"

        if (
            directory.is_dir()
            and marker.exists()
            and datetime.fromtimestamp(
                marker.stat().st_mtime,
                timezone.utc,
            ) <= cutoff
        ):
            shutil.rmtree(
                directory,
                ignore_errors=True,
            )


def process_batch(batch):
    current_status = batch.get(
        "status",
        "",
    )

    log.info(
        "Found %s [%s]",
        batch["batch_id"],
        current_status,
    )

    if current_status == "QUEUED":
        prepare(batch)
        return True

    if current_status == "HANDOFF_REQUESTED":
        handoff(batch)
        return True

    log.warning(
        "Ignoring unsupported batch status: %s",
        current_status,
    )

    return False


def once():
    integrity()
    cleanup()

    batch = next_batch()

    if not batch:
        log.info(
            "No QUEUED or "
            "HANDOFF_REQUESTED batch."
        )
        return False

    return process_batch(batch)


def main():
    one = "--once" in sys.argv

    log.info(
        "Lucky Bags Factory Agent v%s",
        VERSION,
    )

    while not STOP:
        try:
            did_work = once()

        except Exception as exc:
            log.exception(
                "Agent error: %s",
                exc,
            )

            if one:
                raise

            time.sleep(POLL)
            continue

        if one:
            break

        time.sleep(
            2
            if did_work
            else POLL
        )


if __name__ == "__main__":
    main()