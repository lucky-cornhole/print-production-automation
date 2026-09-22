<?php

namespace App\Http\Controllers;

use App\Models\PrintBatch;
use Illuminate\Http\Request;

class FactoryController extends Controller
{
    public function next()
    {
        $batch = PrintBatch::whereIn('status', [
            'QUEUED',
            'HANDOFF_REQUESTED',
        ])
            ->oldest()
            ->first();

        return response()->json([
            'ok' => true,
            'batch' => $batch,
        ]);
    }

    public function status(Request $request, PrintBatch $batch)
    {
        $status = $request->validate([
            'status' => 'required|in:CLAIMED,DOWNLOADING,PREPARED,HANDOFF_REQUESTED,SENT_TO_RIP,PRINTED,FAILED',
        ])['status'];

        $batch->status = $status;

        if ($status === 'CLAIMED' && !$batch->claimed_at) {
            $batch->claimed_at = now();
        }

        if ($status === 'PRINTED') {
            $batch->completed_at = now();
        }

        $batch->save();

        return response()->json([
            'ok' => true,
            'batch' => $batch->fresh(),
        ]);
    }
}