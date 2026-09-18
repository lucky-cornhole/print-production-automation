import json
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from flask import Flask, request, jsonify, render_template_string

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"

MATCHES_FILE = OUTPUT / "artwork_matches.json"

STATE = ROOT / "state"
STATE.mkdir(parents=True, exist_ok=True)

DECISIONS_FILE = STATE / "verification_decisions.json"

PRINT_BATCHES_DIR = OUTPUT / "print_batches"
PRINT_BATCHES_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)

# Confirmed Lucky Bags material recipes.
# side_1 corresponds to the first/only printable artwork for single bags,
# and FRONT for double bags. side_2 is the non-print backside for single
# bags and BACK for double bags.
MATERIAL_RULES = {
    "SUP": {"side_1": "Rave 9", "side_2": "Supreme 5"},
    "LUC": {"side_1": "Rave 8", "side_2": "Anchorage 5"},
    "CLV": {"side_1": "Rave 9", "side_2": "Lucky 5"},
    "ELT-S": {"side_1": "Rave 9", "side_2": "Viewmont 6"},
    "PSE": {"side_1": "Rave 9", "side_2": "Viewmont 6"},
    "SRF-ELT": {"side_1": "Rave 8", "side_2": "Malley 5"},
    "SRF": {"side_1": "Rave 8", "side_2": "Embry 5"},
    "CLT": {"side_1": "Rave 8", "side_2": "Rave 9"},
    "SNP": {"side_1": "Turbo 7", "side_2": "Rave 9"},
    "PSN": {"side_1": "Turbo 6", "side_2": "Rave 9"},
}

YARDS_PER_SIDE_PER_SET = 0.143


def load_json(path, default):
    if not path.exists():
        return default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def drive_thumbnail(file_id):
    if not file_id:
        return ""

    return (
        "https://drive.google.com/thumbnail"
        f"?id={file_id}&sz=w800"
    )


def prepare_items():
    items = load_json(MATCHES_FILE, [])
    decisions = load_json(DECISIONS_FILE, {})

    for item in items:
        line_id = item.get("line_item_id")

        saved = decisions.get(line_id, {})
        current_drive_file_ids = sorted(
            match.get("id")
            for match in item.get("matches", [])
            if match.get("id")
        )
        saved_drive_file_ids = sorted(saved.get("drive_file_ids") or [])

        # Legacy decisions without file IDs are deliberately not considered
        # print-safe. They can still be shown, but must be re-approved.
        decision = saved.get("decision")
        approval_current = (
            bool(current_drive_file_ids)
            and saved_drive_file_ids == current_drive_file_ids
        )

        item["decision"] = decision
        item["decision_at"] = saved.get("updated_at")
        item["approval_current"] = approval_current
        item["ready_for_print"] = (
            not item.get("is_custom", False)
            and decision == "CORRECT"
            and approval_current
        )

        for match in item.get("matches", []):
            match["thumbnail"] = drive_thumbnail(
                match.get("id")
            )

    priority = {
        "REVIEW": 0,
        "MISSING": 1,
        "CUSTOM": 2,
        "MATCHED": 3,
    }

    items.sort(
        key=lambda item: (
            priority.get(item.get("status"), 9),
            item.get("order") or "",
        )
    )

    return items



def build_print_queue(items):
    """
    Build an order-centric Ready for Print queue.

    Single bags show one approved print image.
    Double bags show FRONT + BACK side-by-side in the same tile.

    Material requirements are still calculated per printable side.
    """
    queue = []
    material_totals = {}

    for item in items:
        if not item.get("ready_for_print"):
            continue

        rule = MATERIAL_RULES.get(item.get("series_code"))
        if not rule:
            continue

        qty = int(item.get("quantity") or 0)
        matches = item.get("matches") or []
        design_type = item.get("design_type")

        entry = {
            "line_item_id": item.get("line_item_id"),
            "order": item.get("order"),
            "product": item.get("product"),
            "variant": item.get("variant"),
            "sku": item.get("sku"),
            "series_code": item.get("series_code"),
            "quantity": qty,
            "design_type": design_type,
            "artworks": [],
            "materials": [],
        }

        if design_type == "single":
            if len(matches) != 1:
                continue

            match = matches[0]
            entry["artworks"].append({
                "side": "PRINT",
                "material": rule["side_1"],
                "name": match.get("name"),
                "drive_link": match.get("webViewLink"),
                "thumbnail": match.get("thumbnail"),
            })

            entry["materials"].append({
                "side": "PRINT",
                "material": rule["side_1"],
                "yards": round(qty * YARDS_PER_SIDE_PER_SET, 3),
            })

            total = material_totals.setdefault(
                rule["side_1"],
                {"sets": 0, "yards": 0.0}
            )
            total["sets"] += qty
            total["yards"] += qty * YARDS_PER_SIDE_PER_SET

        elif design_type == "double":
            front = next(
                (m for m in matches if m.get("side") == "front"),
                None
            )
            back = next(
                (m for m in matches if m.get("side") == "back"),
                None
            )

            if not front or not back:
                continue

            entry["artworks"] = [
                {
                    "side": "FRONT",
                    "material": rule["side_1"],
                    "name": front.get("name"),
                    "drive_link": front.get("webViewLink"),
                    "thumbnail": front.get("thumbnail"),
                },
                {
                    "side": "BACK",
                    "material": rule["side_2"],
                    "name": back.get("name"),
                    "drive_link": back.get("webViewLink"),
                    "thumbnail": back.get("thumbnail"),
                },
            ]

            for side, material in [
                ("FRONT", rule["side_1"]),
                ("BACK", rule["side_2"]),
            ]:
                yards = round(qty * YARDS_PER_SIDE_PER_SET, 3)
                entry["materials"].append({
                    "side": side,
                    "material": material,
                    "yards": yards,
                })

                total = material_totals.setdefault(
                    material,
                    {"sets": 0, "yards": 0.0}
                )
                total["sets"] += qty
                total["yards"] += qty * YARDS_PER_SIDE_PER_SET

        else:
            continue

        queue.append(entry)

    for total in material_totals.values():
        total["yards"] = round(total["yards"], 3)

    queue.sort(key=lambda x: x.get("order") or "")
    return queue, dict(sorted(material_totals.items()))


PRINT_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lucky Bags Ready for Print</title>
<style>
* { box-sizing:border-box; }
body { margin:0; background:#f5f6f8; color:#202124; font-family:Arial,Helvetica,sans-serif; }
header { background:#111; color:#fff; padding:16px 22px; }
header h1 { margin:0 0 4px; font-size:24px; }
header p { margin:0; color:#bbb; }
nav { background:#fff; padding:10px 22px; border-bottom:1px solid #ddd; }
nav a { margin-right:14px; text-decoration:none; font-weight:bold; }
main { max-width:1800px; margin:auto; padding:14px; }
.notice { background:#e8f5e9; border:1px solid #b7dfbd; padding:10px 13px; border-radius:8px; margin-bottom:12px; }
.material-summary { background:#fff; border:1px solid #ddd; border-radius:9px; padding:10px 12px; margin-bottom:12px; }
.material-summary h2 { margin:0 0 8px; font-size:17px; }
.materials { display:flex; flex-wrap:wrap; gap:8px; }
.material-pill { background:#f2f3f5; border-radius:16px; padding:7px 10px; font-size:12px; }
.queue { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; align-items:stretch; }
.job { background:#fff; border:1px solid #ddd; border-radius:9px; overflow:hidden; display:flex; flex-direction:column; height:100%; }
.job-head { padding:10px 12px; border-bottom:1px solid #eee; display:flex; justify-content:space-between; gap:10px; }
.order { color:#666; font-size:12px; font-weight:bold; }
.job h3 { margin:2px 0 0; font-size:17px; }
.type { padding:5px 8px; border-radius:14px; background:#eef1f4; font-size:10px; font-weight:bold; height:fit-content; }
.meta { padding:8px 12px; background:#fafafa; display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:7px; font-size:11px; }
.meta span { display:block; color:#777; text-transform:uppercase; font-size:9px; margin-bottom:2px; }
.artworks { padding:10px 12px; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; flex:1; }
.artworks.single { grid-template-columns:1fr; }
.art { min-width:0; }
.art-label { text-align:center; font-size:11px; font-weight:bold; margin-bottom:5px; }
.art img { width:100%; height:145px; object-fit:contain; background:#fafafa; border-radius:7px; }
.filename { margin-top:5px; font-size:10px; font-weight:bold; word-break:break-word; text-align:center; }
.art-meta { margin-top:3px; text-align:center; font-size:10px; color:#666; }
.art-link { display:block; text-align:center; margin-top:4px; font-size:10px; }
.job-foot { border-top:1px solid #eee; padding:8px 12px; display:flex; justify-content:space-between; gap:8px; align-items:center; }
.material-list { font-size:10px; color:#555; }
.approved { padding:5px 8px; border-radius:14px; background:#dff5e5; color:#176b32; font-size:10px; font-weight:bold; white-space:nowrap; }
.batch-actions { display:flex; justify-content:space-between; align-items:center; gap:12px; margin:12px 0; background:#fff; border:1px solid #ddd; border-radius:9px; padding:12px; }
.print-all { border:0; border-radius:8px; padding:11px 18px; background:#111; color:#fff; font-weight:bold; cursor:pointer; }
.print-all:disabled { opacity:.55; cursor:wait; }
.batch-result { font-size:12px; font-weight:bold; }
.summary-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin-bottom:12px; }
.summary-box { background:#fff; border:1px solid #ddd; border-radius:9px; padding:10px 12px; }
.summary-box span { display:block; color:#777; font-size:9px; text-transform:uppercase; }
.summary-box strong { font-size:20px; }
.modal-backdrop { display:none; position:fixed; inset:0; background:rgba(0,0,0,.55); z-index:100; align-items:center; justify-content:center; padding:20px; }
.modal { background:#fff; width:min(650px,100%); max-height:90vh; overflow:auto; border-radius:10px; padding:20px; }
.modal h2 { margin-top:0; }
.modal-actions { display:flex; justify-content:flex-end; gap:10px; margin-top:18px; }
.cancel-btn { border:1px solid #bbb; background:#fff; border-radius:7px; padding:9px 14px; cursor:pointer; }
.confirm-btn { border:0; background:#111; color:#fff; border-radius:7px; padding:9px 14px; font-weight:bold; cursor:pointer; }
.empty { background:#fff; border:1px solid #ddd; border-radius:9px; padding:30px; text-align:center; color:#777; }
@media(max-width:850px) {
  .queue { grid-template-columns:1fr; }
  .meta { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .artworks { grid-template-columns:1fr; }
}
</style>
</head>
<body>
<header>
  <h1>Lucky Bags — Ready for Print</h1>
  <p>Approved stock orders only. Double-sided bags keep FRONT and BACK together.</p>
</header>
<nav>
  <a href="/">← Verification</a>
  <a href="/print-queue">Ready for Print</a>
</nav>
<main>
<div class="notice">
  Safety gate active: only artwork explicitly approved against its exact Drive file ID(s) appears here.
  Nothing is sent to Epson yet.
</div>

<section class="summary-grid">
  <div class="summary-box"><span>Approved Orders</span><strong>{{ summary.approved_orders }}</strong></div>
  <div class="summary-box"><span>Total Sets</span><strong>{{ summary.total_sets }}</strong></div>
  <div class="summary-box"><span>Printable Sides</span><strong>{{ summary.printable_sides }}</strong></div>
  <div class="summary-box"><span>Artwork Files</span><strong>{{ summary.artwork_files }}</strong></div>
</section>

{% if summary.printable_materials %}
<section class="material-summary">
  <h2>Printable Material Requirement</h2>
  <div class="materials">
  {% for material, total in summary.printable_materials.items() %}
    <div class="material-pill"><strong>{{ material }}</strong> · {{ total.sides }} side(s) · {{ "%.3f"|format(total.yards) }} yd</div>
  {% endfor %}
  </div>
</section>
{% endif %}

{% if summary.nonprint_materials %}
<section class="material-summary">
  <h2>Non-Print Backside Material</h2>
  <div class="materials">
  {% for material, total in summary.nonprint_materials.items() %}
    <div class="material-pill"><strong>{{ material }}</strong> · {{ total.sides }} side(s) · {{ "%.3f"|format(total.yards) }} yd</div>
  {% endfor %}
  </div>
</section>
{% endif %}

<div class="batch-actions">
  <div>
    <strong>Total material: {{ "%.3f"|format(summary.total_yards) }} yd</strong><br>
    <span class="batch-result" id="batchResult"></span>
  </div>
  <button class="print-all" onclick="openPrintModal()" {% if summary.approved_orders == 0 %}disabled{% endif %}>
    PRINT ALL APPROVED ({{ summary.approved_orders }})
  </button>
</div>

{% if material_totals %}
<section class="material-summary">
  <h2>Material Requirement</h2>
  <div class="materials">
    {% for material, total in material_totals.items() %}
    <div class="material-pill">
      <strong>{{ material }}</strong> ·
      {{ total.sets }} set-side(s) ·
      {{ "%.3f"|format(total.yards) }} yd
    </div>
    {% endfor %}
  </div>
</section>
{% endif %}

{% if not queue %}
<div class="empty">No approved stock orders are currently ready for print.</div>
{% endif %}

<div class="queue">
{% for job in queue %}
<article class="job">
  <div class="job-head">
    <div>
      <div class="order">{{ job.order }}</div>
      <h3>{{ job.product }}</h3>
    </div>
    <div class="type">{{ job.design_type|upper }}</div>
  </div>

  <div class="meta">
    <div><span>Variant</span><strong>{{ job.variant or '—' }}</strong></div>
    <div><span>SKU</span><strong>{{ job.sku or '—' }}</strong></div>
    <div><span>Series</span><strong>{{ job.series_code }}</strong></div>
    <div><span>Qty</span><strong>{{ job.quantity }}</strong></div>
  </div>

  <div class="artworks {% if job.design_type == 'single' %}single{% endif %}">
    {% for art in job.artworks %}
    <div class="art">
      <div class="art-label">{{ art.side }} — {{ art.material }}</div>
      {% if art.thumbnail %}
      <img src="{{ art.thumbnail }}" loading="lazy">
      {% endif %}
      <div class="filename">{{ art.name }}</div>
      <div class="art-meta">
        {{ art.material }} · {{ "%.3f"|format(job.quantity * yards_per_side) }} yd
      </div>
      <a class="art-link" href="{{ art.drive_link }}" target="_blank">Open approved artwork</a>
    </div>
    {% endfor %}
  </div>

  <div class="job-foot">
    <div class="material-list">
      {% for material in job.materials %}
        {{ material.side }}: <strong>{{ material.material }}</strong>
        {% if not loop.last %} · {% endif %}
      {% endfor %}
    </div>
<span class="approved">✓ APPROVED</span>
  </div>
</article>
{% endfor %}
</div>
<div class="modal-backdrop" id="printModal">
  <div class="modal">
    <h2>Confirm Production Batch</h2>
    <p><strong>{{ summary.approved_orders }}</strong> approved orders ·
       <strong>{{ summary.total_sets }}</strong> sets ·
       <strong>{{ summary.printable_sides }}</strong> printable sides ·
       <strong>{{ summary.artwork_files }}</strong> original artwork files</p>
    <p>Before creating the batch, the server will re-check every approval and exact Drive file ID. Custom, wrong, missing, unverified, or changed artwork will not be included.</p>
    <h3>Printable Materials</h3>
    <ul>
    {% for material, total in summary.printable_materials.items() %}
      <li>{{ material }} — {{ total.sides }} side(s) — {{ "%.3f"|format(total.yards) }} yd</li>
    {% endfor %}
    </ul>
    {% if summary.nonprint_materials %}
    <h3>Non-Print Backside Materials</h3>
    <ul>
    {% for material, total in summary.nonprint_materials.items() %}
      <li>{{ material }} — {{ total.sides }} side(s) — {{ "%.3f"|format(total.yards) }} yd</li>
    {% endfor %}
    </ul>
    {% endif %}
    <div class="modal-actions">
      <button class="cancel-btn" onclick="closePrintModal()">Cancel</button>
      <button class="confirm-btn" id="confirmBatchBtn" onclick="confirmPrintBatch()">CONFIRM PRINT BATCH</button>
    </div>
  </div>
</div>
</main>
<script>
function openPrintModal() {
  document.getElementById("printModal").style.display = "flex";
}
function closePrintModal() {
  document.getElementById("printModal").style.display = "none";
}
async function confirmPrintBatch() {
  const btn = document.getElementById("confirmBatchBtn");
  btn.disabled = true;
  try {
    const response = await fetch("/api/print-batch", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({})
    });
    const result = await response.json();
    if (!result.ok) {
      document.getElementById("batchResult").textContent =
        "BLOCKED: " + (result.error || "Unable to create batch");
      closePrintModal();
      return;
    }
    document.getElementById("batchResult").textContent =
      "BATCH CREATED: " + result.batch_id +
      " (" + result.orders + " orders / " + result.artwork_files + " files)";
    closePrintModal();
  } catch (e) {
    document.getElementById("batchResult").textContent = "ERROR creating batch";
    closePrintModal();
  } finally {
    btn.disabled = false;
  }
}
</script>
</body>
</html>
"""

HTML = r"""
<!DOCTYPE html>
<html lang="en">

<head>
<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1"
>

<title>Lucky Bags Production Verification</title>

<style>

* {
    box-sizing: border-box;
}

body {
    margin: 0;
    background: #f5f6f8;
    color: #202124;
    font-family: Arial, Helvetica, sans-serif;
}

header {
    background: #111;
    color: white;
    padding: 14px 22px;
    position: sticky;
    top: 0;
    z-index: 20;
}

header h1 {
    margin: 0 0 6px;
    font-size: 22px;
}

header p {
    margin: 0;
    color: #bbb;
}

.filters {
    background: white;
    padding: 10px 18px;
    border-bottom: 1px solid #ddd;
    position: sticky;
    top: 62px;
    z-index: 19;
}

.filters button {
    border: 1px solid #ccc;
    background: white;
    padding: 7px 11px;
    border-radius: 20px;
    margin-right: 6px;
    cursor: pointer;
}

.filters button:hover {
    background: #eee;
}

main {
    max-width: 1800px;
    margin: auto;
    padding: 14px;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
    align-items: stretch;
}

.card {
    background: white;
    display: flex;
    flex-direction: column;
    height: 100%;
    border: 1px solid #ddd;
    border-radius: 9px;
    margin-bottom: 0;
    overflow: hidden;
}

.card.verified {
    border: 3px solid #2e8b57;
}

.card.wrong {
    border: 3px solid #c62828;
}

.header {
    padding: 10px 14px;
    display: flex;
    justify-content: space-between;
    border-bottom: 1px solid #eee;
}

.header h2 {
    margin: 2px 0 0;
}

.order {
    font-weight: bold;
    color: #666;
}

.status {
    font-weight: bold;
    padding: 6px 10px;
    border-radius: 18px;
    height: fit-content;
}

.MATCHED {
    background: #dff5e5;
    color: #176b32;
}

.REVIEW {
    background: #fff1c9;
    color: #805d00;
}

.MISSING {
    background: #ffe0e0;
    color: #9b1c1c;
}

.CUSTOM {
    background: #e7e5ff;
    color: #4538a3;
}

.details {
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(150px, 1fr));
    gap: 8px;
    background: #fafafa;
    padding: 8px 14px;
}

.details span {
    display: block;
    color: #777;
    font-size: 11px;
    text-transform: uppercase;
    margin-bottom: 4px;
}

.comparison {
    display: grid;
    grid-template-columns:
        minmax(0, 1fr)
        minmax(0, 1.25fr);
    gap: 10px;
    padding: 8px 14px;
    align-items: center;
    flex: 1;
}

.drive-area {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    align-items: start;
}

.drive-area.single-drive {
    grid-template-columns: 1fr;
}

.label {
    font-size: 12px;
    font-weight: bold;
    margin-bottom: 8px;
}

.image {
    min-height: 105px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: #f3f3f3;
    border-radius: 8px;
    overflow: hidden;
}

.image img {
    width: 100%;
    height: 130px;
    object-fit: contain;
    background: white;
}

.empty {
    color: #999;
    padding: 18px;
}

.filename {
    font-weight: bold;
    font-size: 13px;
    margin-top: 5px;
    word-break: break-word;
}

.small {
    color: #777;
    font-size: 12px;
    margin-top: 4px;
}

.arrow {
    display: none;
}

.actions {
    padding: 9px 14px;
    border-top: 1px solid #eee;
    display: flex;
    gap: 12px;
    align-items: center;
}

.actions button {
    border: 0;
    border-radius: 7px;
    padding: 8px 14px;
    font-weight: bold;
    cursor: pointer;
}

.correct {
    background: #198754;
    color: white;
}

.wrong-button {
    background: #dc3545;
    color: white;
}

.decision {
    margin-left: auto;
    font-weight: bold;
}

.decision.ok {
    color: #198754;
}

.decision.bad {
    color: #dc3545;
}

.blocked {
    color: #9b1c1c;
    font-weight: bold;
}

.custom-info {
    min-height: 130px;
    border: 1px dashed #8b7fd1;
    background: #f6f4ff;
    border-radius: 8px;
    padding: 14px;
}

.custom-message {
    font-size: 13px;
    line-height: 1.4;
    margin: 8px 0;
}

.custom-state {
    margin-top: 12px;
    display: inline-block;
    background: #e7e5ff;
    color: #4538a3;
    padding: 6px 9px;
    border-radius: 14px;
    font-size: 11px;
    font-weight: bold;
}

.custom-action {
    color: #4538a3;
    font-weight: bold;
}

@media(max-width: 850px) {

    main {
        grid-template-columns: 1fr;
    }

    .card {
        height: auto;
    }

    .drive-area {
        grid-template-columns: 1fr;
    }

    .comparison {
        grid-template-columns: 1fr;
    }

    .arrow {
        transform: rotate(90deg);
    }
}

</style>
</head>

<body>

<header>
    <h1>Lucky Bags Production Verification</h1>
    <p>
        Verify Shopify order artwork against factory artwork.
        Nothing can print from this page.
    </p>
</header>

<div class="filters">
    <a href="/print-queue" style="font-weight:bold;margin-right:12px;">Ready for Print →</a>
    <button onclick="filterCards('ALL')">All</button>
    <button onclick="filterCards('SINGLE')">Single Side</button>
    <button onclick="filterCards('DOUBLE')">Double Side</button>
    <button onclick="filterCards('CUSTOM')">Custom Bags</button>
    <button onclick="filterCards('READY')">Ready for Print</button>
    <button onclick="filterCards('UNVERIFIED')">Unverified</button>
    <button onclick="filterCards('CORRECT')">Verified</button>
    <button onclick="filterCards('WRONG_REVIEW')">Wrong / Review</button>
</div>

<main>

{% for item in items %}

<article
    class="
        card
        {% if item.decision == 'CORRECT' %}verified{% endif %}
        {% if item.decision == 'WRONG' %}wrong{% endif %}
    "
    data-status="{{ item.status }}"
    data-decision="{{ item.decision or '' }}"
    data-type="{{ item.design_type }}"
    data-custom="{{ 'yes' if item.is_custom else 'no' }}"
    data-ready="{{ 'yes' if item.ready_for_print else 'no' }}"
    id="card-{{ loop.index }}"
>

    <div class="header">

        <div>
            <div class="order">
                {{ item.order }}
            </div>

            <h2>{{ item.product }}</h2>
        </div>

        <div class="status {{ item.status }}">
            {{ item.status }}
        </div>

    </div>

    <div class="details">

        <div>
            <span>Variant</span>
            <strong>{{ item.variant or '—' }}</strong>
        </div>

        <div>
            <span>SKU</span>
            <strong>{{ item.sku or '—' }}</strong>
        </div>

        <div>
            <span>Quantity</span>
            <strong>{{ item.quantity }}</strong>
        </div>

        <div>
            <span>Series</span>
            <strong>{{ item.series_code }}</strong>
        </div>

        <div>
            <span>Type</span>
            <strong>{{ item.design_type }}</strong>
        </div>

        <div>
            <span>Color</span>
            <strong>{{ item.color or '—' }}</strong>
        </div>

        <div>
            <span>Confidence</span>
            <strong>{{ item.confidence }}</strong>
        </div>

    </div>

    <div class="comparison">

        <div>

            <div class="label">
                SHOPIFY ORDER IMAGE
            </div>

            {% if item.shopify_image %}

            <div class="image">
                <img
                    src="{{ item.shopify_image }}"
                    loading="lazy"
                >
            </div>

            {% else %}

            <div class="image empty">
                No Shopify image
            </div>

            {% endif %}

            <div class="filename">
                {{ item.product }}
            </div>

        </div>

        <div class="arrow">→</div>

        <div class="drive-area {% if item.design_type == 'single' %}single-drive{% endif %}">

            {% if item.matches %}

                {% for match in item.matches %}

                <div>

                    <div class="label">
                        DRIVE {{ match.side|upper }}
                    </div>

                    <div class="image">
                        <img
                            src="{{ match.thumbnail }}"
                            loading="lazy"
                        >
                    </div>

                    <div class="filename">
                        {{ match.name }}
                    </div>

                    <div class="small">
                        Score: {{ match.score }}
                    </div>

                    <a
                        href="{{ match.webViewLink }}"
                        target="_blank"
                    >
                        Open original in Google Drive
                    </a>

                </div>

                {% endfor %}

            {% else %}

                {% if item.is_custom %}
                <div class="custom-info">
                    <div class="label">CUSTOM PRODUCTION ARTWORK</div>
                    <div class="custom-message">
                        Custom bag artwork comes from the Shopify customizer (FPD),
                        not Google Drive.
                    </div>
                    <div class="small">
                        Series: {{ item.series_code }} ·
                        {{ item.design_type|upper }} ·
                        Qty: {{ item.quantity }}
                    </div>
                    <div class="custom-state">
                        Awaiting custom artwork verification
                    </div>
                </div>
                {% else %}
                <div class="image empty">
                    No Drive artwork matched
                </div>
                {% endif %}

            {% endif %}

        </div>

    </div>

    <div class="actions">

        {% if item.matches %}

            <button
                class="correct"
                onclick="saveDecision(
                    '{{ item.line_item_id }}',
                    'CORRECT',
                    this
                )"
            >
                ✓ Correct
            </button>

            <button
                class="wrong-button"
                onclick="saveDecision(
                    '{{ item.line_item_id }}',
                    'WRONG',
                    this
                )"
            >
                ✕ Wrong
            </button>

        {% else %}

            {% if item.is_custom %}
            <span class="custom-action">
                CUSTOM — artwork verification will use the FPD/customizer file
            </span>
            {% else %}
            <span class="blocked">
                No artwork available to verify
            </span>
            {% endif %}

        {% endif %}

        <span
            class="
                decision
                {% if item.decision == 'CORRECT' %}ok{% endif %}
                {% if item.decision == 'WRONG' %}bad{% endif %}
            "
        >

            {% if item.ready_for_print %}
                ✓ APPROVED — READY FOR PRINT
            {% elif item.decision == 'CORRECT' and not item.approval_current %}
                ⚠ RE-VERIFY ARTWORK
            {% elif item.decision == 'WRONG' and item.approval_current %}
                ✕ WRONG ARTWORK
            {% elif item.decision == 'WRONG' %}
                ⚠ ARTWORK CHANGED — RE-VERIFY
            {% else %}
                NOT VERIFIED
            {% endif %}

        </span>

    </div>

</article>

{% endfor %}

</main>

<script>

async function saveDecision(lineItemId, decision, button) {

    button.disabled = true;

    try {

        const response = await fetch(
            "/api/verify",
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    line_item_id: lineItemId,
                    decision: decision
                })
            }
        );

        const result = await response.json();

        if (!result.ok) {
            alert(result.error || "Unable to save");
            return;
        }

        window.location.reload();

    }
    catch (error) {
        alert("Unable to save verification.");
    }
    finally {
        button.disabled = false;
    }
}


function filterCards(filter) {

    document.querySelectorAll(".card").forEach(card => {

        const status = card.dataset.status;
        const decision = card.dataset.decision;
        const type = card.dataset.type;
        const custom = card.dataset.custom;
        const ready = card.dataset.ready;

        let visible = true;

        if (filter === "SINGLE") {
            visible = type === "single" && custom !== "yes";
        }
        else if (filter === "DOUBLE") {
            visible = type === "double" && custom !== "yes";
        }
        else if (filter === "CUSTOM") {
            visible = custom === "yes";
        }
        else if (filter === "READY") {
            visible = ready === "yes";
        }
        else if (filter === "UNVERIFIED") {
            visible = !decision;
        }
        else if (filter === "CORRECT") {
            visible = decision === "CORRECT";
        }
        else if (filter === "WRONG_REVIEW") {
            visible =
                decision === "WRONG" ||
                status === "REVIEW" ||
                status === "MISSING";
        }

        card.style.display = visible ? "" : "none";
    });
}

</script>

</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(
        HTML,
        items=prepare_items()
    )


def production_summary(items):
    ready = [x for x in items if x.get("ready_for_print")]
    material_totals = {}
    printable_materials = {}
    nonprint_materials = {}
    total_sets = 0
    printable_sides = 0
    artwork_files = 0

    for item in ready:
        qty = int(item.get("quantity") or 0)
        total_sets += qty
        rule = MATERIAL_RULES.get(item.get("series_code"))
        if not rule:
            continue

        dtype = item.get("design_type")
        if dtype == "single":
            printable_sides += qty
            artwork_files += 1
            usages = [
                (rule["side_1"], True, qty),
                (rule["side_2"], False, qty),
            ]
        elif dtype == "double":
            printable_sides += qty * 2
            artwork_files += 2
            usages = [
                (rule["side_1"], True, qty),
                (rule["side_2"], True, qty),
            ]
        else:
            usages = []

        for material, printable, sides in usages:
            yards = sides * YARDS_PER_SIDE_PER_SET
            target = printable_materials if printable else nonprint_materials
            rec = target.setdefault(material, {"sides": 0, "yards": 0.0})
            rec["sides"] += sides
            rec["yards"] += yards

            all_rec = material_totals.setdefault(material, {"sides": 0, "yards": 0.0})
            all_rec["sides"] += sides
            all_rec["yards"] += yards

    for group in (material_totals, printable_materials, nonprint_materials):
        for rec in group.values():
            rec["yards"] = round(rec["yards"], 3)

    return {
        "approved_orders": len(ready),
        "total_sets": total_sets,
        "printable_sides": printable_sides,
        "artwork_files": artwork_files,
        "printable_materials": dict(sorted(printable_materials.items())),
        "nonprint_materials": dict(sorted(nonprint_materials.items())),
        "material_totals": dict(sorted(material_totals.items())),
        "total_yards": round(sum(x["yards"] for x in material_totals.values()), 3),
    }


@app.route("/print-queue")
def print_queue():
    items = prepare_items()
    queue, material_totals = build_print_queue(items)
    summary = production_summary(items)
    return render_template_string(
        PRINT_HTML,
        queue=queue,
        material_totals=material_totals,
        summary=summary,
        yards_per_side=YARDS_PER_SIDE_PER_SET,
    )


@app.post("/api/print-batch")
def create_print_batch():
    items = prepare_items()
    ready = [x for x in items if x.get("ready_for_print")]

    if not ready:
        return jsonify(ok=False, error="No approved stock orders are ready for print"), 409

    orders = []
    artwork_file_count = 0

    for item in ready:
        # Re-check approval against exact current Drive IDs.
        line_id = item.get("line_item_id")
        decisions = load_json(DECISIONS_FILE, {})
        saved = decisions.get(line_id, {})
        current_ids = sorted(
            m.get("id") for m in item.get("matches", []) if m.get("id")
        )
        saved_ids = sorted(saved.get("drive_file_ids") or [])

        if item.get("is_custom") or saved.get("decision") != "CORRECT" or not current_ids or current_ids != saved_ids:
            continue

        rule = MATERIAL_RULES.get(item.get("series_code"))
        if not rule:
            continue

        matches = item.get("matches") or []
        dtype = item.get("design_type")
        artworks = []

        if dtype == "single":
            if len(matches) != 1:
                continue
            artworks = [{
                "side": "PRINT",
                "material": rule["side_1"],
                "drive_file_id": matches[0].get("id"),
                "filename": matches[0].get("name"),
                "drive_link": matches[0].get("webViewLink"),
            }]
        elif dtype == "double":
            front = next((m for m in matches if m.get("side") == "front"), None)
            back = next((m for m in matches if m.get("side") == "back"), None)
            if not front or not back:
                continue
            artworks = [
                {"side":"FRONT","material":rule["side_1"],"drive_file_id":front.get("id"),"filename":front.get("name"),"drive_link":front.get("webViewLink")},
                {"side":"BACK","material":rule["side_2"],"drive_file_id":back.get("id"),"filename":back.get("name"),"drive_link":back.get("webViewLink")},
            ]
        else:
            continue

        artwork_file_count += len(artworks)
        orders.append({
            "line_item_id": line_id,
            "order": item.get("order"),
            "product": item.get("product"),
            "variant": item.get("variant"),
            "sku": item.get("sku"),
            "series_code": item.get("series_code"),
            "design_type": dtype,
            "quantity": int(item.get("quantity") or 0),
            "artworks": artworks,
        })

    if not orders:
        return jsonify(ok=False, error="All approvals failed the final safety check"), 409

    # Recalculate summary from only the orders that passed final validation.
    batch_id = "LB-BATCH-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:4].upper()
    batch = {
        "batch_id": batch_id,
        "status": "QUEUED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "yards_per_side_per_set": YARDS_PER_SIDE_PER_SET,
        "order_count": len(orders),
        "artwork_file_count": artwork_file_count,
        "orders": orders,
    }

    path = PRINT_BATCHES_DIR / f"{batch_id}.json"
    save_json(path, batch)

    return jsonify(
        ok=True,
        batch_id=batch_id,
        orders=len(orders),
        artwork_files=artwork_file_count,
        batch_file=str(path),
    )


@app.post("/api/verify")
def verify():

    payload = request.get_json(silent=True) or {}

    line_item_id = payload.get("line_item_id")
    decision = payload.get("decision")

    if not line_item_id:
        return jsonify(
            ok=False,
            error="Missing line item ID"
        ), 400

    if decision not in {"CORRECT", "WRONG"}:
        return jsonify(
            ok=False,
            error="Invalid decision"
        ), 400

    items = load_json(MATCHES_FILE, [])
    current_item = next(
        (item for item in items if item.get("line_item_id") == line_item_id),
        None
    )

    if not current_item:
        return jsonify(
            ok=False,
            error="Production line item not found"
        ), 404

    current_drive_file_ids = sorted(
        match.get("id")
        for match in current_item.get("matches", [])
        if match.get("id")
    )

    if not current_drive_file_ids:
        return jsonify(
            ok=False,
            error="No Drive artwork is available to verify"
        ), 400

    decisions = load_json(
        DECISIONS_FILE,
        {}
    )

    decisions[line_item_id] = {
        "decision": decision,
        "drive_file_ids": current_drive_file_ids,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    save_json(
        DECISIONS_FILE,
        decisions
    )

    return jsonify(ok=True)


if __name__ == "__main__":

    if not MATCHES_FILE.exists():
        raise FileNotFoundError(
            "output/artwork_matches.json not found. "
            "Run matcher.py first."
        )

    print("")
    print("Lucky Bags Production Verification")
    print("----------------------------------")
    print("Open:")
    print("http://127.0.0.1:5000")
    print("")
    print("Press CTRL+C to stop.")
    print("")

    app.run(
        host="127.0.0.1",
        port=5000,
        debug=False
    )