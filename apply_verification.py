import json, os
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parent
items=json.loads((ROOT/"output/artwork_matches.json").read_text(encoding="utf-8"))
lid=os.environ["LINE_ITEM_ID"].strip()
decision=os.environ["DECISION"].strip().upper()
if decision not in {"CORRECT","WRONG"}: raise SystemExit("Invalid decision")
item=next((x for x in items if x.get("line_item_id")==lid),None)
if not item: raise SystemExit("Current production line item not found")
if item.get("is_custom"): raise SystemExit("Custom item blocked from stock verification")
ids=sorted(m.get("id") for m in item.get("matches",[]) if m.get("id"))
if not ids: raise SystemExit("No current Drive artwork IDs")
p=ROOT/"state/verification_decisions.json"; p.parent.mkdir(exist_ok=True)
state=json.loads(p.read_text(encoding="utf-8") or "{}") if p.exists() else {}
state[lid]={"decision":decision,"drive_file_ids":ids,"updated_at":datetime.now(timezone.utc).isoformat(),"updated_by":os.environ.get("GITHUB_ACTOR","unknown")}
p.write_text(json.dumps(state,indent=2)+"\n",encoding="utf-8")
print(decision, item.get("order"), ids)
