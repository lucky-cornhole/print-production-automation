<?php

return [

    'shopify' => [
        'store' => env('SHOPIFY_STORE'),
        'client_id' => env('SHOPIFY_CLIENT_ID'),
        'client_secret' => env('SHOPIFY_CLIENT_SECRET'),
        'api_version' => env('SHOPIFY_API_VERSION', '2026-07'),
    ],

    'google_drive' => [
        'service_account_file' => base_path(
            env(
                'GOOGLE_SERVICE_ACCOUNT_FILE',
                'service-account.json'
            )
        ),

        'artwork_root_id' => env(
            'GOOGLE_DRIVE_ARTWORK_ROOT_ID'
        ),

        'allowed_root_folders' => [
            '(GROUP A) Non Carpet',
            'GROUP B (Carpet)',
        ],
    ],

];