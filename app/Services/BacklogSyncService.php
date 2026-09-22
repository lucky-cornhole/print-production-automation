<?php
namespace App\Services;
use App\Models\ProductionItem;use Illuminate\Support\Facades\DB;
class BacklogSyncService{
 public function __construct(private ShopifyService $shopify,private GoogleDriveService $drive,private ArtworkMatcherService $matcher){}
 public function sync():array{$b=$this->shopify->getProductionBacklog();$index=$this->drive->artworkIndex();$added=$updated=$unchanged=$matched=$missing=0;DB::transaction(function()use($b,$index,&$added,&$updated,&$unchanged,&$matched,&$missing){foreach($b['items'] as $r){$i=ProductionItem::where('line_item_id',$r['line_item_id'])->first();$sf=['order_number'=>$r['order_number'],'product'=>$r['product'],'variant'=>$r['variant'],'sku'=>$r['sku'],'quantity'=>$r['quantity'],'shopify_image'=>$r['shopify_image']];if($i){$i->fill($sf);if($i->isDirty()){$i->save();$updated++;}else$unchanged++;continue;}$m=$this->matcher->match($r,$index);ProductionItem::create(['line_item_id'=>$r['line_item_id'],...$sf,...$m]);$added++;count($m['matches'])?$matched++:$missing++;}});return ['shopify_items'=>$b['item_count'],'orders_examined'=>$b['order_count'],'added'=>$added,'updated'=>$updated,'unchanged'=>$unchanged,'matched'=>$matched,'missing'=>$missing,'drive_files'=>count($index)];}
}
