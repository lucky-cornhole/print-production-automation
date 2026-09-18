import os,re,json,sys
from pathlib import Path
from collections import Counter
import requests
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parent; OUT=ROOT/"output"; OUT.mkdir(exist_ok=True); load_dotenv(ROOT/".env")
SERIES=json.loads((ROOT/"series.json").read_text())
SHOP=os.getenv("LB_SHOP",""); CID=os.getenv("LB_CLIENT_ID",""); SECRET=os.getenv("LB_CLIENT_SECRET","")
API=os.getenv("SHOPIFY_API_VERSION","2026-07"); DRIVE_ROOT=os.getenv("GOOGLE_DRIVE_ROOT_FOLDER_ID","")
def save(n,d): (OUT/n).write_text(json.dumps(d,indent=2,ensure_ascii=False),encoding="utf-8")
def token():
 r=requests.post(f"https://{SHOP}/admin/oauth/access_token",json={"client_id":CID,"client_secret":SECRET,"grant_type":"client_credentials"},timeout=30); r.raise_for_status()
 t=r.json().get("access_token")
 if not t: raise RuntimeError("No Shopify access_token returned")
 return t
def gql(t,q,v):
 r=requests.post(f"https://{SHOP}/admin/api/{API}/graphql.json",headers={"X-Shopify-Access-Token":t,"Content-Type":"application/json"},json={"query":q,"variables":v},timeout=60); r.raise_for_status()
 b=r.json()
 if b.get("errors"): raise RuntimeError(json.dumps(b["errors"],indent=2))
 return b["data"]
Q="""query Orders($after:String){orders(first:100,after:$after,query:"status:open fulfillment_status:unfulfilled"){pageInfo{hasNextPage endCursor}nodes{id name createdAt displayFinancialStatus displayFulfillmentStatus cancelledAt customer{displayName}lineItems(first:100){nodes{id name quantity sku variantTitle product{id title productType vendor}variant{id title sku image{url altText}selectedOptions{name value}}customAttributes{key value}}}}}}"""
def orders(t):
 out=[]; after=None
 while True:
  b=gql(t,Q,{"after":after})["orders"]; out+=b["nodes"]
  if not b["pageInfo"]["hasNextPage"]: return out
  after=b["pageInfo"]["endCursor"]
def series_code(sku,vt):
 s=(sku or "").upper()
 for c in sorted(SERIES,key=len,reverse=True):
  if re.search(rf"(^|-){re.escape(c)}(-|$)",s): return c
 vl=(vt or "").lower()
 for c,x in SERIES.items():
  if x["name"].lower() in vl:return c
def flatten(oset):
 out=[]
 for o in oset:
  for li in o["lineItems"]["nodes"]:
   a={x["key"]:x["value"] for x in li.get("customAttributes",[])}
   sku=li.get("sku") or (li.get("variant") or {}).get("sku") or ""; c=series_code(sku,li.get("variantTitle"))
   out.append({"order":o["name"],"created_at":o["createdAt"],"line_item_id":li["id"],"product":(li.get("product") or {}).get("title"),"product_type":(li.get("product") or {}).get("productType"),"variant":li.get("variantTitle"),"sku":sku,"quantity":li["quantity"],"options":{x["name"]:x["value"] for x in ((li.get("variant") or {}).get("selectedOptions") or [])},"variant_image":((li.get("variant") or {}).get("image") or {}).get("url"),"properties":a,"fpd":{k:v for k,v in a.items() if k.startswith("_fpd")},"is_custom":any(k.startswith("_fpd") for k in a),"series_code":c,"series_rule":SERIES.get(c),"production_candidate":bool(c)})
 return out
def drive_service():
 from googleapiclient.discovery import build
 scopes=["https://www.googleapis.com/auth/drive.readonly"]
 service_json=os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON","").strip()
 if service_json:
  from google.oauth2 import service_account
  try: info=json.loads(service_json)
  except json.JSONDecodeError as e: raise RuntimeError(f"GOOGLE_SERVICE_ACCOUNT_JSON is invalid JSON: {e}")
  creds=service_account.Credentials.from_service_account_info(info,scopes=scopes)
  return build("drive","v3",credentials=creds,cache_discovery=False)
 from google.oauth2.credentials import Credentials
 from google_auth_oauthlib.flow import InstalledAppFlow
 from google.auth.transport.requests import Request
 tp=ROOT/"token.json"; creds=None
 if tp.exists(): creds=Credentials.from_authorized_user_file(str(tp),scopes)
 if creds and creds.expired and creds.refresh_token:
  creds.refresh(Request()); tp.write_text(creds.to_json(),encoding="utf-8")
 if not creds or not creds.valid:
  cp=ROOT/"credentials.json"
  if not cp.exists(): raise RuntimeError("Missing credentials.json for local Google Drive OAuth.")
  creds=InstalledAppFlow.from_client_secrets_file(str(cp),scopes).run_local_server(port=0)
  tp.write_text(creds.to_json(),encoding="utf-8")
 return build("drive","v3",credentials=creds,cache_discovery=False)
def children(s,fid):
 out=[]; pt=None
 while True:
  r=s.files().list(q=f"'{fid}' in parents and trashed=false",fields="nextPageToken,files(id,name,mimeType,size,webViewLink,imageMediaMetadata(width,height))",pageSize=1000,pageToken=pt,supportsAllDrives=True,includeItemsFromAllDrives=True).execute()
  out+=r.get("files",[]); pt=r.get("nextPageToken")
  if not pt:return out
def scan(s,rid):
 out=[]
 def walk(fid,path):
  for x in children(s,fid):
   p=path+[x["name"]]; n=x["name"].upper()
   row={"id":x["id"],"name":x["name"],"mimeType":x["mimeType"],"size":int(x["size"]) if x.get("size") else None,"path":"/".join(p),"webViewLink":x.get("webViewLink"),"width":(x.get("imageMediaMetadata") or {}).get("width"),"height":(x.get("imageMediaMetadata") or {}).get("height"),"front":"FRONT" in n,"back":"BACK" in n,"mockup":"MOCKUP" in "/".join(p).upper()}
   row["series_code"]=next((c for c in sorted(SERIES,key=len,reverse=True) if n.startswith(c+"-") or n.startswith(c+"_")),None); out.append(row)
   if x["mimeType"]=="application/vnd.google-apps.folder":walk(x["id"],p)
 walk(rid,[]); return out
def markdown(lines,df):
 p=[x for x in lines if x["production_candidate"]]; c=Counter(x["series_code"] for x in p); imgs=[x for x in df if x["mimeType"].startswith("image/")]
 md=["# Lucky Bags Production Discovery Audit","","## Shopify",f"- Line items: **{len(lines)}**",f"- Production bag candidates: **{len(p)}**",f"- Stock candidates: **{sum(not x['is_custom'] for x in p)}**",f"- Custom candidates: **{sum(x['is_custom'] for x in p)}**","","### Series"]
 for code in SERIES:md.append(f"- {code} / {SERIES[code]['name']}: **{c.get(code,0)}**")
 md+=["","## Google Drive",f"- Descendants: **{len(df)}**",f"- Images: **{len(imgs)}**",f"- FRONT images: **{sum(x['front'] for x in imgs)}**",f"- BACK images: **{sum(x['back'] for x in imgs)}**","","## Production candidates","|Order|Product|Variant|SKU|Qty|Series|Type|Custom|","|---|---|---|---|---:|---|---|---|"]
 for x in p:md.append(f"|{x['order']}|{x['product'] or ''}|{x['variant'] or ''}|`{x['sku']}`|{x['quantity']}|{x['series_code']}|{x['series_rule']['design_type']}|{'Yes' if x['is_custom'] else 'No'}|")
 md+=["","**Read-only audit:** nothing is modified and nothing is sent to print."]
 return "\n".join(md)
def main():
 if not SHOP or not CID or not SECRET: raise RuntimeError("Fill LB_SHOP, LB_CLIENT_ID and LB_CLIENT_SECRET in .env")
 print("Shopify read-only audit..."); os_=orders(token()); lines=flatten(os_); save("shopify_orders_raw.json",os_); save("shopify_line_items.json",lines); print(f"Shopify: {len(os_)} orders / {len(lines)} lines")
 df=[]
 if DRIVE_ROOT:
  print("Google Drive read-only audit..."); df=scan(drive_service(),DRIVE_ROOT); save("drive_files.json",df); print(f"Drive: {len(df)} descendants")
 (OUT/"AUDIT_REPORT.md").write_text(markdown(lines,df),encoding="utf-8"); print("DONE:",OUT/"AUDIT_REPORT.md")
if __name__=="__main__":
 try:main()
 except Exception as e:print("FAILED:",e,file=sys.stderr);sys.exit(1)
