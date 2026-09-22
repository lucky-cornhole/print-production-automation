<?php

namespace App\Http\Controllers;

use App\Models\ProductionItem;
use App\Models\PrintBatch;
use App\Services\ProductionService;
use App\Services\BacklogSyncService;
use Illuminate\Http\Request;

class ProductionController extends Controller
{
    public function __construct(
        private ProductionService $svc,
        private BacklogSyncService $backlogSync
    ) {}

    public function dashboard()
    {
        $items = ProductionItem::with('decision')->get();

        $ready = $items->filter(
            fn ($item) => $this->svc->ready($item)
        );

        return view('dashboard.index', [
            'total' => $items->count(),
            'ready' => $ready->count(),
            'review' => $items->where('match_status', 'REVIEW')->count(),
            'custom' => $items->where('is_custom', true)->count(),
            'summary' => $this->svc->summary($ready),
            'batches' => PrintBatch::latest()->limit(5)->get(),
        ]);
    }

    public function syncBacklog()
    {
        try {
            $r = $this->backlogSync->sync();
            return redirect()->route('dashboard')->with('ok', sprintf('Shopify backlog refreshed: %d current · %d added · %d updated · %d unchanged · %d matched · %d missing.', $r['shopify_items'], $r['added'], $r['updated'], $r['unchanged'], $r['matched'], $r['missing']));
        } catch (\Throwable $e) {
            report($e);
            return redirect()->route('dashboard')->with('error', 'Shopify backlog refresh failed: '.$e->getMessage());
        }
    }

    public function verification()
    {
        $items = ProductionItem::with('decision')
            ->orderByRaw("
                CASE match_status
                    WHEN 'REVIEW' THEN 0
                    WHEN 'MISSING' THEN 1
                    WHEN 'CUSTOM' THEN 2
                    ELSE 3
                END
            ")
            ->orderBy('order_number')
            ->get();

        foreach ($items as $item) {
            $item->ready_for_print = $this->svc->ready($item);
            $item->approval_current = $this->svc->current($item);
        }

        return view('production.verification', compact('items'));
    }

    public function verify(Request $request, ProductionItem $item)
    {
        $decision = $request->validate([
            'decision' => 'required|in:CORRECT,WRONG',
        ])['decision'];

        $this->svc->verify(
            $item,
            $decision,
            $request->user()->id
        );

        return back()->with(
            'ok',
            $decision === 'CORRECT'
                ? 'Artwork approved.'
                : 'Artwork marked wrong.'
        );
    }

    public function queue()
    {
        $items = $this->svc->queue();

        return view('production.queue', [
            'items' => $items,
            'summary' => $this->svc->summary($items),
            'materials' => ProductionService::MATERIALS,
        ]);
    }

    public function batch(Request $request)
    {
        $batch = $this->svc->batch(
            $request->user()->id
        );

        return redirect('/batches/'.$batch->id)
            ->with('ok', 'Production batch created.');
    }

    public function batches()
    {
        return view('batches.index', [
            'batches' => PrintBatch::latest()->get(),
        ]);
    }

    public function showBatch(PrintBatch $batch)
    {
        return view('batches.show', compact('batch'));
    }

    /**
     * Operator requests the prepared batch to be handed
     * from the Factory Agent to Epson Edge Print.
     */
    public function requestEdgePrint(Request $request, PrintBatch $batch)
    {
        abort_unless(
            $batch->status === 'PREPARED',
            422,
            'Only a PREPARED batch can be sent to Edge Print.'
        );

        $batch->status = 'HANDOFF_REQUESTED';
        $batch->save();

        return redirect('/batches/'.$batch->id)
            ->with(
                'ok',
                'Edge Print handoff requested. Waiting for Factory PC.'
            );
    }

    /**
     * Operator confirms the batch was physically printed.
     */
    public function markPrinted(Request $request, PrintBatch $batch)
    {
        abort_unless(
            $batch->status === 'SENT_TO_RIP',
            422,
            'Only a batch already sent to Edge Print can be marked printed.'
        );

        $batch->status = 'PRINTED';
        $batch->completed_at = now();
        $batch->save();

        return redirect('/batches/'.$batch->id)
            ->with('ok', 'Batch marked as printed.');
    }
}