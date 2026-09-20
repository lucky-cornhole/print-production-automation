from __future__ import annotations
import hashlib, io, json, logging, os, shutil, signal, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

HERE=Path(__file__).resolve().parent
load_dotenv(HERE/".env")
VERSION=(HERE/"VERSION").read_text().strip()
BASE=os.getenv("PRODUCTION_API","http://127.0.0.1:8000/api").rstrip("/")
KEY=os.getenv("FACTORY_API_KEY","").strip()
CREDS=Path(os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE",str(HERE/"service-account.json")))
OUT=Path(os.getenv("FACTORY_PRINT_DIR",str(HERE/"factory_print")))
HOT=os.getenv("EDGE_PRINT_HOT_FOLDER","").strip()
POLL=max(10,int(os.getenv("POLL_SECONDS","30")))
RETENTION=max(1,int(os.getenv("LOCAL_RETENTION_HOURS","72")))
REQ_VER=os.getenv("REQUIRED_AGENT_VERSION","").strip()
REQ_SHA=os.getenv("REQUIRED_AGENT_SHA256","").strip().lower()
HEAD={"Authorization":f"Bearer {KEY}","Accept":"application/json"}
STOP=False
(HERE/"logs").mkdir(exist_ok=True)
logging.basicConfig(level=logging.INFO,format="%(asctime)s | %(levelname)s | %(message)s",
 handlers=[logging.FileHandler(HERE/"logs/factory-agent.log",encoding="utf-8"),logging.StreamHandler()])
log=logging.getLogger("factory-agent")

def sig(*_):
 global STOP; STOP=True
signal.signal(signal.SIGINT,sig); signal.signal(signal.SIGTERM,sig)

def sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for c in iter(lambda:f.read(1048576),b""): h.update(c)
 return h.hexdigest()

def integrity():
 if not KEY: raise RuntimeError("FACTORY_API_KEY is not configured")
 if not CREDS.exists(): raise RuntimeError(f"Service account missing: {CREDS}")
 if REQ_VER and VERSION!=REQ_VER: raise RuntimeError(f"AGENT UPDATE REQUIRED: installed={VERSION}, required={REQ_VER}")
 if REQ_SHA and sha(__file__)!=REQ_SHA: raise RuntimeError("AGENT UPDATE REQUIRED: checksum mismatch")

def api(method,path,**kw):
 r=requests.request(method,BASE+path,headers=HEAD,timeout=60,**kw); r.raise_for_status()
 return r.json() if r.content else {}

def status(i,s): log.info("Batch %s -> %s",i,s); api("POST",f"/factory/batches/{i}/status",json={"status":s})
def next_batch(): return api("GET","/factory/batches/next").get("batch")
def drive():
 c=service_account.Credentials.from_service_account_file(str(CREDS),scopes=["https://www.googleapis.com/auth/drive.readonly"])
 return build("drive","v3",credentials=c,cache_discovery=False)
def safe(s):
 for c in '<>:"/\\|?*': s=s.replace(c,"_")
 return s.strip().rstrip(".") or "artwork"
def download(svc,fid,dest):
 dest.parent.mkdir(parents=True,exist_ok=True)
 req=svc.files().get_media(fileId=fid)
 with io.FileIO(dest,"wb") as fh:
  dl=MediaIoBaseDownload(fh,req); done=False
  while not done: _,done=dl.next_chunk()

def prepare(b):
 i,bid,p=b["id"],b["batch_id"],b["payload"]; folder=OUT/safe(bid)
 status(i,"CLAIMED"); status(i,"DOWNLOADING"); svc=drive()
 expected=sum(len(o.get("artworks",[])) for o in p.get("orders",[])); count=0
 try:
  for o in p.get("orders",[]):
   for a in o.get("artworks",[]):
    material=safe(a.get("material") or "Unassigned")
    name=safe(f"{str(o.get('order','')).replace('#','')}_{o.get('series_code','')}_{a.get('side','PRINT')}_{a.get('filename','artwork')}")
    log.info("Downloading %s | %s | %s",o.get("order"),material,a.get("side"))
    download(svc,a["drive_file_id"],folder/material/name); count+=1
  folder.mkdir(parents=True,exist_ok=True)
  manifest={"agent_version":VERSION,"prepared_at":datetime.now(timezone.utc).isoformat(),
            "expected_artwork_files":expected,"downloaded_artwork_files":count,"batch":p}
  (folder/"batch.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
  if count!=expected: raise RuntimeError(f"Artwork mismatch {count}/{expected}")
  status(i,"PREPARED"); log.info("PREPARED %s: %d/%d files",bid,count,expected)
  if HOT: log.warning("Edge Print folder configured but automatic RIP handoff is disabled pending controlled factory test.")
 except Exception:
  try: status(i,"FAILED")
  except Exception: pass
  raise

def cleanup():
 if not OUT.exists(): return
 cutoff=datetime.now(timezone.utc)-timedelta(hours=RETENTION)
 for d in OUT.iterdir():
  marker=d/".printed"
  if d.is_dir() and marker.exists() and datetime.fromtimestamp(marker.stat().st_mtime,timezone.utc)<=cutoff:
   shutil.rmtree(d,ignore_errors=True)

def once():
 integrity(); cleanup(); b=next_batch()
 if not b: log.info("No QUEUED batch."); return False
 log.info("Found %s",b["batch_id"]); prepare(b); return True

def main():
 one="--once" in sys.argv
 log.info("Lucky Bags Factory Agent v%s",VERSION)
 while not STOP:
  try: did=once()
  except Exception as e:
   log.exception("Agent error: %s",e)
   if one: raise
   time.sleep(POLL); continue
  if one: break
  time.sleep(2 if did else POLL)

if __name__=="__main__": main()
