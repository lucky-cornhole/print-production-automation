<?php
namespace App\Models;use Illuminate\Database\Eloquent\Model;class PrintBatch extends Model{protected $fillable=['batch_id','status','order_count','artwork_file_count','total_yards','payload','created_by','claimed_at','completed_at'];protected function casts():array{return ['payload'=>'array','claimed_at'=>'datetime','completed_at'=>'datetime'];}}
