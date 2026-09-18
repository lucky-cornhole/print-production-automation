# Lucky Bags Production Discovery

Read-only audit for the Lucky Bags production automation MVP.

## Install on Windows

```powershell
cd D:\LuckyBags\Automation\Production-Automation
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` and enter the same Lucky Bags Shopify `LB_CLIENT_ID` and `LB_CLIENT_SECRET` used by the existing report. Your existing report already uses client-credentials authentication, so no permanent access token needs to be stored.

## Google Drive read-only OAuth

1. In Google Cloud Console create/select a project.
2. Enable **Google Drive API**.
3. Configure OAuth consent screen if requested.
4. Create **OAuth Client ID -> Desktop app**.
5. Download the JSON.
6. Rename it to `credentials.json`.
7. Put it beside `discover.py`.

Do NOT commit `credentials.json`, `token.json`, or `.env`.

## Run

```powershell
.\.venv\Scripts\activate
python discover.py
```

The first Drive run opens Google login. Sign in with the Google account that can view the Lucky Bags production folder and approve read-only Drive access.

## Output

`output/AUDIT_REPORT.md`
`output/shopify_orders_raw.json`
`output/shopify_line_items.json`
`output/drive_files.json`

Send the audit report and JSON files back for review. No Shopify/Drive records are modified and nothing is sent to print.
