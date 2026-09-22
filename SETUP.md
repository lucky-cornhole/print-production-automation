# Lucky Bags Production - Quick Setup

1. Copy `.env.example` to `.env` and add the real Shopify credentials, production URL/database path, and a strong `FACTORY_API_KEY`.
2. Put `service-account.json` in the project root locally/server-side. Never commit it.
3. Run:

```bash
composer install --no-interaction
php artisan key:generate
php artisan optimize:clear
php artisan migrate --force
php artisan db:seed --force
php artisan serve
```

For an existing production `.env` with a valid APP_KEY, do **not** run `key:generate`; preserve the existing key.

## Manual backlog refresh
Log in to the dashboard and click **GET CURRENT PRINT BACKLOG**. It pulls current eligible Lucky Bags stock-bag line items from Shopify, indexes the approved Google Drive manufacturing branches, matches new artwork conservatively, and preserves existing human verification decisions.

## Factory agent
The Factory Agent remains under `automation/`. Configure `automation/.env` on the Factory PC from `automation/config.example.env`, then use the supplied install/autostart scripts. Version is in `automation/VERSION`.
