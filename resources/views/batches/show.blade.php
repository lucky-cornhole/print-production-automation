<x-layouts.app
    heading="{{ $batch->batch_id }}"
    subheading="Factory production batch"
>
    @php
        $status = $batch->status;

        $steps = [
            'QUEUED',
            'CLAIMED',
            'DOWNLOADING',
            'PREPARED',
            'HANDOFF_REQUESTED',
            'SENT_TO_RIP',
            'PRINTED',
        ];

        $currentIndex = array_search($status, $steps, true);
    @endphp

    <div class="stats compact">
        <div class="stat">
            <span>Status</span>
            <b class="smallb">{{ $batch->status }}</b>
        </div>

        <div class="stat">
            <span>Orders</span>
            <b>{{ $batch->order_count }}</b>
        </div>

        <div class="stat">
            <span>Artwork Files</span>
            <b>{{ $batch->artwork_file_count }}</b>
        </div>

        <div class="stat">
            <span>Material</span>
            <b>{{ number_format($batch->total_yards, 3) }} yd</b>
        </div>
    </div>

    <section class="panel">
        <div class="panel-head">
            <div>
                <h2>Factory Print Progress</h2>
                <p>
                    Track this batch from the cloud application
                    through the Factory PC and Epson Edge Print.
                </p>
            </div>
        </div>

        <div style="display:grid;gap:12px;margin-top:16px;">

            <div>
                {{ $currentIndex !== false && $currentIndex >= 0 ? '✓' : '○' }}
                <strong>Batch Created</strong>
            </div>

            <div>
                {{ $currentIndex !== false && $currentIndex >= 1 ? '✓' : '○' }}
                <strong>Factory PC Claimed Batch</strong>
            </div>

            <div>
                {{ $currentIndex !== false && $currentIndex >= 2 ? '✓' : '○' }}
                <strong>Downloading Artwork</strong>
            </div>

            <div>
                {{ $currentIndex !== false && $currentIndex >= 3 ? '✓' : '○' }}
                <strong>Artwork Prepared</strong>
            </div>

            <div>
                {{ $currentIndex !== false && $currentIndex >= 4 ? '✓' : '○' }}
                <strong>Edge Print Handoff Requested</strong>
            </div>

            <div>
                {{ $currentIndex !== false && $currentIndex >= 5 ? '✓' : '○' }}
                <strong>Sent to Epson Edge Print</strong>
            </div>

            <div>
                {{ $status === 'PRINTED' ? '✓' : '○' }}
                <strong>Print Completed</strong>
            </div>

        </div>

        @if($status === 'PREPARED')
            <div style="margin-top:22px;">
                <form
                    method="POST"
                    action="{{ route('batch.edge-print', $batch) }}"
                    onsubmit="return confirm(
                        'Send this prepared batch to Epson Edge Print? This will queue the artwork on the Factory PC but will not automatically start physical printing.'
                    );"
                >
                    @csrf

                    <button
                        type="submit"
                        class="btn primary"
                    >
                        SEND TO EDGE PRINT
                    </button>
                </form>
            </div>

        @elseif($status === 'HANDOFF_REQUESTED')
            <div
                style="
                    margin-top:22px;
                    padding:14px 16px;
                    border:1px solid #e5e7eb;
                    border-radius:10px;
                "
            >
                <strong>Waiting for Factory PC...</strong>

                <div style="margin-top:4px;">
                    The Factory Agent will detect this request
                    and hand the prepared artwork to Epson Edge Print.
                </div>
            </div>

        @elseif($status === 'SENT_TO_RIP')
            <div style="margin-top:22px;">
                <div
                    style="
                        margin-bottom:14px;
                        padding:14px 16px;
                        border:1px solid #e5e7eb;
                        border-radius:10px;
                    "
                >
                    <strong>Artwork sent to Epson Edge Print.</strong>

                    <div style="margin-top:4px;">
                        Review the jobs in Edge Print, RIP them,
                        and physically print the batch.
                    </div>
                </div>

                <form
                    method="POST"
                    action="{{ route('batch.printed', $batch) }}"
                    onsubmit="return confirm(
                        'Confirm that this complete batch has physically finished printing?'
                    );"
                >
                    @csrf

                    <button
                        type="submit"
                        class="btn primary"
                    >
                        MARK PRINTED
                    </button>
                </form>
            </div>

        @elseif($status === 'PRINTED')
            <div
                style="
                    margin-top:22px;
                    padding:14px 16px;
                    border:1px solid #d1fae5;
                    border-radius:10px;
                "
            >
                <strong>✓ PRINT COMPLETE</strong>

                @if($batch->completed_at)
                    <div style="margin-top:4px;">
                        Completed:
                        {{ $batch->completed_at->format('M d, Y · g:i A') }}
                    </div>
                @endif
            </div>

        @elseif($status === 'FAILED')
            <div
                style="
                    margin-top:22px;
                    padding:14px 16px;
                    border:1px solid #fecaca;
                    border-radius:10px;
                "
            >
                <strong>Factory processing failed.</strong>

                <div style="margin-top:4px;">
                    Check the Factory Agent log before retrying this batch.
                </div>
            </div>
        @endif
    </section>

    <section class="panel">
        <div class="panel-head">
            <div>
                <h2>Factory Payload</h2>
                <p>
                    The Factory Agent consumes this batch through
                    the protected Factory API.
                </p>
            </div>
        </div>

        @foreach($batch->payload['orders'] ?? [] as $order)
            <div class="batch-order">
                <div>
                    <b>
                        {{ $order['order'] }}
                        ·
                        {{ $order['product'] }}
                    </b>

                    <span>
                        {{ $order['variant'] }}
                        ·
                        {{ $order['series_code'] }}
                        ·
                        Qty {{ $order['quantity'] }}
                    </span>
                </div>

                <div class="pills">
                    @foreach($order['artworks'] as $artwork)
                        <span>
                            {{ $artwork['side'] }}
                            ·
                            {{ $artwork['material'] }}
                            ·
                            {{ $artwork['filename'] }}
                        </span>
                    @endforeach
                </div>
            </div>
        @endforeach
    </section>
</x-layouts.app>