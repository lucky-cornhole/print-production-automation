# Lucky Bags Factory Agent

Factory-PC component for Lucky Bags Production Management.

## Current MVP behavior
- Permanently installed on the Windows print PC.
- Polls the protected Laravel Factory API for `QUEUED` batches.
- Claims one batch at a time.
- Downloads original artwork directly from Google Drive.
- Stores artwork only in the local temporary `factory_print` workspace.
- Groups downloaded artwork by printable material.
- Reports `CLAIMED`, `DOWNLOADING`, `PREPARED`, or `FAILED` to Laravel.
- Can run once for controlled tests or continuously in the background.
- Includes Windows startup-task installer.
- Includes local version/SHA-256 integrity gate.
- Includes checksum-verified update script.
- Does **not** automatically send jobs to Epson Edge Print PRO yet. That adapter is intentionally pending the controlled factory-PC/Edge Print configuration test.

## Install on Factory PC
1. Install Python 3.11+ and enable "Add Python to PATH".
2. Extract this folder to `C:\LuckyBagsFactory`.
3. Open PowerShell as Administrator in that folder.
4. Run `.\install.ps1`.
5. Edit `.env`.
6. Put the Google service-account JSON in the path configured by `GOOGLE_SERVICE_ACCOUNT_FILE`.
7. Test with `.\run-once.ps1`.
8. After the controlled test succeeds, run `.\install-autostart.ps1`.

## Security
Never commit `.env`, `service-account.json`, `.venv`, logs, or `factory_print`.

## Updating
A release ZIP can be created with `.\make-release.ps1`.
The updater requires the expected SHA-256:
`.\update-agent.ps1 -ZipPath <zip> -ExpectedSha256 <sha256>`

Machine-specific `.env`, credentials, logs, venv and temporary artwork are preserved during updates.

## Edge Print
`EDGE_PRINT_HOT_FOLDER` exists in config but automatic RIP handoff is disabled until the actual Epson Edge Print PRO workflow/presets are verified.
