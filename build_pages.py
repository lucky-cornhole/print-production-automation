from pathlib import Path
import importlib.util
ROOT=Path(__file__).resolve().parent; DOCS=ROOT/"docs"
spec=importlib.util.spec_from_file_location("v",ROOT/"verification_app.py")
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
def ver(h):
 h=h.replace('href="/print-queue"','href="print-queue.html"')
 a=h.find("async function saveDecision("); b=h.find("function filterCards(",a)
 js="""function saveDecision(lineItemId, decision, button) {
 const title="[PRODUCTION VERIFY] "+decision;
 const body="LINE_ITEM_ID: "+lineItemId+"\\nDECISION: "+decision+"\\n\\nProduction verification request from Lucky Bags dashboard.";
 const url="https://github.com/lucky-cornhole/print-production-automation/issues/new?title="+encodeURIComponent(title)+"&body="+encodeURIComponent(body);
 window.open(url,"_blank");
}

"""
 if a!=-1 and b!=-1: h=h[:a]+js+h[b:]
 return h
def pq(h):
 h=h.replace('href="/"','href="index.html"').replace('href="/print-queue"','href="print-queue.html"')
 a=h.find("async function confirmPrintBatch()"); b=h.find("</script>",a)
 if a!=-1 and b!=-1:
  h=h[:a]+"""async function confirmPrintBatch() {
 document.getElementById("batchResult").textContent="Print Batch workflow will be connected after verification.";
 closePrintModal();
}
"""+h[b:]
 return h
def main():
 DOCS.mkdir(exist_ok=True)
 items=m.prepare_items(); q,mt=m.build_print_queue(items); s=m.production_summary(items)
 with m.app.app_context():
  h1=m.render_template_string(m.HTML,items=items)
  h2=m.render_template_string(m.PRINT_HTML,queue=q,material_totals=mt,summary=s,yards_per_side=m.YARDS_PER_SIDE_PER_SET)
 (DOCS/"index.html").write_text(ver(h1),encoding="utf-8")
 (DOCS/"print-queue.html").write_text(pq(h2),encoding="utf-8")
 (DOCS/".nojekyll").write_text("",encoding="utf-8")
 print("Generated GitHub Pages production UI")
if __name__=="__main__": main()
