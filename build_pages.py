from pathlib import Path
import importlib.util

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
APP_FILE = ROOT / "verification_app.py"

def load_app():
    spec = importlib.util.spec_from_file_location("lb_verification_app", APP_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def static_verification(html):
    html = html.replace('href="/print-queue"', 'href="print-queue.html"')
    start = html.find("async function saveDecision(")
    end = html.find("function filterCards(", start)
    if start != -1 and end != -1:
        replacement = 'function saveDecision(lineItemId, decision, button) { alert("GitHub Pages preview: Correct/Wrong workflow will be connected next."); }\n\n'
        html = html[:start] + replacement + html[end:]
    return html

def static_print(html):
    html = html.replace('href="/"', 'href="index.html"')
    html = html.replace('href="/print-queue"', 'href="print-queue.html"')
    start = html.find("async function confirmPrintBatch()")
    end = html.find("</script>", start)
    if start != -1 and end != -1:
        prefix = html[:start]
        suffix = html[end:]
        replacement = '''async function confirmPrintBatch() {
  document.getElementById("batchResult").textContent =
    "GitHub Pages preview: Print Batch workflow will be connected next.";
  closePrintModal();
}
'''
        # Preserve open/close modal functions before confirm; replace confirm through script end.
        html = prefix + replacement + suffix
    return html

def main():
    m = load_app()
    if not m.MATCHES_FILE.exists():
        raise FileNotFoundError("output/artwork_matches.json not found. Run discover.py and matcher.py first.")
    DOCS.mkdir(parents=True, exist_ok=True)
    items = m.prepare_items()
    queue, material_totals = m.build_print_queue(items)
    summary = m.production_summary(items)
    with m.app.app_context():
        verification = m.render_template_string(m.HTML, items=items)
        print_queue = m.render_template_string(
            m.PRINT_HTML,
            queue=queue,
            material_totals=material_totals,
            summary=summary,
            yards_per_side=m.YARDS_PER_SIDE_PER_SET,
        )
    (DOCS/"index.html").write_text(static_verification(verification), encoding="utf-8")
    (DOCS/"print-queue.html").write_text(static_print(print_queue), encoding="utf-8")
    (DOCS/".nojekyll").write_text("", encoding="utf-8")
    print("Generated exact current UI:")
    print(DOCS/"index.html")
    print(DOCS/"print-queue.html")

if __name__ == "__main__":
    main()
