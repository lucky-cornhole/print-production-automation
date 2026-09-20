# Lucky Bags Production Management — Laravel MVP

A local-first Laravel MVP that consolidates the proven Lucky Bags production workflow into a normal authenticated application. It is intended to become the functional reference for the later production-grade rebuild.

## Included

- Branded login with two seeded users
- Dashboard and production summaries
- Shopify-vs-Drive artwork verification UI
- Correct / Wrong directly inside the app (no GitHub Issues)
- Exact Google Drive file-ID safety gate
- Single / Double / Custom filters
- Ready for Print page
- Material matrix and 0.143 yd per side/set calculations
- `PRINT ALL APPROVED` confirmation and locked DB batch
- Print-batch history/detail screens
- Protected Factory API
- Python factory agent that claims a queued batch and downloads exact Drive originals
- SQLite for local testing; MySQL-ready for HostGator
- Seeded copy of the current 40 matched production candidates

## Theme

The UI follows the same design language as the supplied Frontline AI admin source: Instrument Sans, light neutral surfaces, compact cards, left admin sidebar, restrained borders, rounded controls and status badges. The supplied source clearly uses Instrument Sans and a Laravel-style app bundle/data-page structure.

## Local setup

Requirements: PHP 8.2+, Composer, SQLite PHP extension.

```powershell
cd lucky-bags-production-laravel
copy .env.example .env
composer install
php artisan key:generate
php artisan migrate --seed
php artisan serve
```

Open: `http://127.0.0.1:8000`

### Seeded users

- `admin@luckybags.local` / `LuckyBags123!`
- `operator@luckybags.local` / `LuckyBags123!`

Change these passwords before any shared/hosted deployment.

## Local workflow test

1. Login.
2. Open **Verification**.
3. Approve one known-correct Single and one known-correct Double order.
4. Open **Ready for Print**.
5. Confirm material summary and FRONT/BACK pairing.
6. Click **PRINT ALL APPROVED** and confirm.
7. Open **Print Batches** and inspect the generated batch.
8. Configure and run the factory agent.

## Factory agent

```powershell
cd automation
py -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
$env:PRODUCTION_API="http://127.0.0.1:8000/api"
$env:FACTORY_API_KEY="change-this-factory-key"
$env:GOOGLE_SERVICE_ACCOUNT_FILE="C:\\secure\\service-account.json"
python factory_agent.py
```

The agent changes `QUEUED → CLAIMED → DOWNLOADING → PREPARED`, downloads the exact approved Drive originals, and writes `batch.json` beside the artwork. Automatic Edge Print hot-folder submission is intentionally left disabled until the controlled Epson test confirms the correct hot-folder/preset behavior.

## MySQL / HostGator later

Change `.env`:

```env
DB_CONNECTION=mysql
DB_HOST=localhost
DB_PORT=3306
DB_DATABASE=...
DB_USERNAME=...
DB_PASSWORD=...
```

Then run `php artisan migrate --seed`.

## Production data refresh

This package is seeded from the current `artwork_matches.json` so the UI is immediately testable. The next integration step is to make the existing GitHub/Python `discover.py + matcher.py` publish/import the refreshed JSON into this application. The core verification, Ready-for-Print, batching and factory API do not depend on GitHub Pages.

## Important safety behavior

Approval stores the exact Drive file IDs that were visible at approval time. If the current matched file IDs change, the item no longer qualifies as Ready for Print and must be re-verified.
