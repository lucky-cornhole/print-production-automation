<?php

namespace App\Services;

use Illuminate\Support\Facades\Http;
use RuntimeException;

class ShopifyService
{
    private string $store;
    private string $clientId;
    private string $clientSecret;
    private string $apiVersion;

    private ?string $accessToken = null;

    public function __construct()
    {
        $this->store = trim(
            (string) config('services.shopify.store')
        );

        $this->clientId = trim(
            (string) config('services.shopify.client_id')
        );

        $this->clientSecret = trim(
            (string) config('services.shopify.client_secret')
        );

        $this->apiVersion = trim(
            (string) config(
                'services.shopify.api_version',
                '2026-07'
            )
        );

        if (
            $this->store === '' ||
            $this->clientId === '' ||
            $this->clientSecret === ''
        ) {
            throw new RuntimeException(
                'Shopify production integration is not configured.'
            );
        }
    }

    /**
     * Get a Shopify access token using the
     * client credentials flow.
     */
    private function getAccessToken(): string
    {
        if ($this->accessToken !== null) {
            return $this->accessToken;
        }

        $url = sprintf(
            'https://%s/admin/oauth/access_token',
            $this->store
        );

        $response = Http::asForm()
            ->timeout(30)
            ->post($url, [
                'grant_type' => 'client_credentials',
                'client_id' => $this->clientId,
                'client_secret' => $this->clientSecret,
            ]);

        if ($response->failed()) {
            throw new RuntimeException(
                'Unable to obtain Shopify access token. HTTP ' .
                $response->status() .
                ': ' .
                $response->body()
            );
        }

        $token = $response->json('access_token');

        if (!$token) {
            throw new RuntimeException(
                'Shopify did not return an access token.'
            );
        }

        $this->accessToken = $token;

        return $token;
    }

    /**
     * Execute a Shopify Admin GraphQL query.
     */
    public function graphql(
        string $query,
        array $variables = []
    ): array {
        $url = sprintf(
            'https://%s/admin/api/%s/graphql.json',
            $this->store,
            $this->apiVersion
        );

        $payload = [
            'query' => $query,
        ];

        /*
         * Do not send an empty variables parameter.
         * Shopify rejects it for some requests.
         */
        if (!empty($variables)) {
            $payload['variables'] = $variables;
        }

        $response = Http::withHeaders([
            'X-Shopify-Access-Token' => $this->getAccessToken(),
            'Accept' => 'application/json',
            'Content-Type' => 'application/json',
        ])
            ->timeout(60)
            ->post($url, $payload);

        if ($response->failed()) {
            throw new RuntimeException(
                'Shopify GraphQL request failed. HTTP ' .
                $response->status() .
                ': ' .
                $response->body()
            );
        }

        $json = $response->json();

        if (!empty($json['errors'])) {
            throw new RuntimeException(
                'Shopify GraphQL error: ' .
                json_encode($json['errors'])
            );
        }

        return $json['data'] ?? [];
    }

    /**
     * Read-only Shopify connection test.
     */
    public function testConnection(): array
    {
        $query = <<<'GRAPHQL'
query ProductionShopTest {
    shop {
        name
        myshopifyDomain
    }
}
GRAPHQL;

        return $this->graphql($query);
    }

    /**
     * Read the current Lucky Bags manufacturing backlog.
     *
     * This method is READ-ONLY.
     * It does not modify Shopify or the local database.
     */
    public function getProductionBacklog(int $first = 50): array
    {
        $query = <<<'GRAPHQL'
query ProductionBacklog($first: Int!) {
    orders(
        first: $first
        sortKey: CREATED_AT
        reverse: true
        query: "fulfillment_status:unfulfilled OR fulfillment_status:partial"
    ) {
        nodes {
            id
            name
            createdAt
            cancelledAt
            displayFinancialStatus
            displayFulfillmentStatus

            customer {
                displayName
            }

            lineItems(first: 100) {
                nodes {
                    id
                    name
                    quantity
                    unfulfilledQuantity
                    sku
                    variantTitle

                    product {
                        id
                        title
                        productType
                    }

                    image {
                        url
                    }
                }
            }
        }

        pageInfo {
            hasNextPage
            endCursor
        }
    }
}
GRAPHQL;

        $data = $this->graphql(
            $query,
            [
                'first' => $first,
            ]
        );

        $items = [];

        foreach (
            $data['orders']['nodes'] ?? []
            as $order
        ) {
            /*
             * Ignore cancelled orders.
             */
            if (!empty($order['cancelledAt'])) {
                continue;
            }

            /*
             * Ignore fully refunded orders.
             */
            if (
                ($order['displayFinancialStatus'] ?? '')
                === 'REFUNDED'
            ) {
                continue;
            }

            foreach (
                $order['lineItems']['nodes'] ?? []
                as $line
            ) {
                $productTitle = trim(
                    (string) (
                        $line['product']['title']
                        ?? ''
                    )
                );

                if ($productTitle === '') {
                    continue;
                }

                /*
                 * Bag manufacturing only.
                 *
                 * Do not allow apparel, accessories,
                 * fees, patches, coolers, etc. into
                 * the bag production workflow.
                 */
                $productType = trim(
                    (string) (
                        $line['product']['productType']
                        ?? ''
                    )
                );

                if (!in_array(
                    $productType,
                    [
                        'ACL Pro Stamped 2026',
                        'ACL Pro Stamped 2027',
                    ],
                    true
                )) {
                    continue;
                }

                /*
                 * Custom bags follow their own
                 * artwork approval workflow.
                 *
                 * For now, exclude them from this
                 * stock-print backlog.
                 */
                if (
                    stripos(
                        $productTitle,
                        'Custom'
                    ) !== false
                ) {
                    continue;
                }

                /*
                 * Only actual outstanding quantity
                 * belongs in the manufacturing backlog.
                 */
                $unfulfilledQuantity = (int) (
                    $line['unfulfilledQuantity']
                    ?? 0
                );

                if ($unfulfilledQuantity <= 0) {
                    continue;
                }

                $items[] = [
                    'line_item_id' =>
                        $line['id'],

                    'order_id' =>
                        $order['id'],

                    'order_number' =>
                        $order['name'],

                    'order_date' =>
                        $order['createdAt'],

                    'customer' =>
                        $order['customer']['displayName']
                        ?? null,

                    'product' =>
                        $productTitle,

                    'product_type' =>
                        $productType,

                    'variant' =>
                        $line['variantTitle']
                        ?? null,

                    'sku' =>
                        $line['sku']
                        ?? null,

                    'quantity' =>
                        $unfulfilledQuantity,

                    'shopify_image' =>
                        $line['image']['url']
                        ?? null,

                    'financial_status' =>
                        $order['displayFinancialStatus']
                        ?? null,

                    'fulfillment_status' =>
                        $order['displayFulfillmentStatus']
                        ?? null,
                ];
            }
        }

        return [
            'items' => $items,

            /*
             * Number of Shopify orders examined.
             * This is NOT necessarily the number
             * of manufacturing orders.
             */
            'order_count' => count(
                $data['orders']['nodes']
                ?? []
            ),

            /*
             * Number of eligible bag-production
             * line items after filtering.
             */
            'item_count' => count($items),

            'has_next_page' =>
                $data['orders']['pageInfo']['hasNextPage']
                ?? false,

            'end_cursor' =>
                $data['orders']['pageInfo']['endCursor']
                ?? null,
        ];
    }
}