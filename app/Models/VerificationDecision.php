<?php
namespace App\Models;use Illuminate\Database\Eloquent\Model;class VerificationDecision extends Model{protected $fillable=['line_item_id','decision','drive_file_ids','updated_by'];protected function casts():array{return ['drive_file_ids'=>'array'];}public function user(){return $this->belongsTo(User::class,'updated_by');}}
