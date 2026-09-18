import json
import re
from pathlib import Path
from difflib import SequenceMatcher

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"

SHOPIFY_FILE = OUTPUT / "shopify_line_items.json"
DRIVE_FILE = OUTPUT / "drive_files.json"
SERIES_FILE = ROOT / "series.json"

# Only these Drive production folders are allowed.
SERIES_FOLDERS = {
    "SNP": {
        "group": "(GROUP A) Non Carpet",
        "folder": "Snipers",
    },
    "CLT": {
        "group": "(GROUP A) Non Carpet",
        "folder": "Celtics",
    },
    "PSN": {
        "group": "(GROUP A) Non Carpet",
        "folder": "Pro Snipers",
    },
    "SRF": {
        "group": "(GROUP A) Non Carpet",
        "folder": "Surefire",
    },

    "LUC": {
        "group": "GROUP B (Carpet)",
        "folder": "Luciano",
    },
    "ELT-S": {
        "group": "GROUP B (Carpet)",
        "folder": "Elite S",
    },
    "CLV": {
        "group": "GROUP B (Carpet)",
        "folder": "Clover",
    },
    "SUP": {
        "group": "GROUP B (Carpet)",
        "folder": "Supreme",
    },
    "SRF-ELT": {
        "group": "GROUP B (Carpet)",
        "folder": "SFE",
    },
    "PSE": {
        "group": "GROUP B (Carpet)",
        "folder": "PSE",
    },
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize(value):
    """
    Convert names to a comparable representation.

    Example:
        Lucky Bags 2027 Lucky Friends
        -> LUCKY FRIENDS
    """

    if not value:
        return ""

    value = value.upper()

    replacements = [
        "LUCKY BAGS",
        "ACL PRO STAMPED",
        "2027",
        "2026",
        ".JPG",
        ".JPEG",
        ".PNG",
        ".WEBP",
    ]

    for item in replacements:
        value = value.replace(item, " ")

    value = value.replace("_", " ")
    value = value.replace("-", " ")

    value = re.sub(r"[^A-Z0-9 ]+", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_color(value):
    return normalize(value)


def extract_design(product_title):
    """
    Remove common Shopify prefixes but retain the actual design name.
    """

    if not product_title:
        return ""

    value = product_title

    prefixes = [
        "Lucky Bags 2027 ",
        "Lucky Bags 2026 ",
        "Lucky Bags ",
    ]

    for prefix in prefixes:
        if value.lower().startswith(prefix.lower()):
            value = value[len(prefix):]
            break

    return normalize(value)


def extract_color(item):
    options = item.get("options") or {}

    if options.get("Color"):
        return normalize_color(options["Color"])

    variant = item.get("variant") or ""

    # Variant is often:
    # Pro Sniper Elite / White

    if "/" in variant:
        pieces = [x.strip() for x in variant.split("/")]

        if len(pieces) >= 2:
            return normalize_color(pieces[-1])

    # Some Shopify variants don't expose Color separately.
    # Try Shopify image filename as supporting evidence later.
    return ""


def extract_shopify_image_tokens(item):
    url = item.get("variant_image") or ""

    if not url:
        return ""

    filename = url.split("/")[-1].split("?")[0]

    return normalize(filename)


def allowed_drive_file(file, series_code):
    """
    Restrict search to:
      Group A/B
        -> exact series folder
        -> production files only

    MOCKUPS are excluded.
    """

    config = SERIES_FOLDERS.get(series_code)

    if not config:
        return False

    path = file.get("path") or ""
    normalized_path = path.replace("\\", "/")

    if "MOCKUP" in normalized_path.upper():
        return False

    group = config["group"].upper()
    folder = config["folder"].upper()

    path_upper = normalized_path.upper()

    if group not in path_upper:
        return False

    # Require the expected series folder somewhere after group.
    parts = [x.strip().upper() for x in normalized_path.split("/")]

    if folder not in parts:
        return False

    mime = file.get("mimeType") or ""

    if not mime.startswith("image/"):
        return False

    return True


def score_candidate(item, drive_file):
    """
    Score Drive artwork using:
      design
      color
      Shopify image filename
      SKU design code

    Folder/series is already enforced before scoring.
    """

    filename = normalize(drive_file.get("name"))
    design = extract_design(item.get("product"))
    color = extract_color(item)
    shopify_image = extract_shopify_image_tokens(item)

    score = 0
    reasons = []

    # Strongest signal: design words appear in Drive filename.
    design_words = [
        x for x in design.split()
        if len(x) >= 3
    ]

    if design_words:
        matched_words = sum(
            1 for word in design_words
            if word in filename
        )

        ratio = matched_words / len(design_words)

        if ratio == 1:
            score += 60
            reasons.append("design-exact")
        elif ratio >= 0.67:
            score += 45
            reasons.append("design-strong")
        elif ratio >= 0.40:
            score += 25
            reasons.append("design-partial")

    # Color.
    if color and color in filename:
        score += 25
        reasons.append("color")

    # Shopify preview filename can sometimes contain the same
    # terminology as factory artwork.
    if shopify_image:
        similarity = SequenceMatcher(
            None,
            shopify_image,
            filename
        ).ratio()

        if similarity >= 0.75:
            score += 20
            reasons.append("shopify-image-strong")
        elif similarity >= 0.55:
            score += 10
            reasons.append("shopify-image-partial")

    return score, reasons


def determine_side(drive_file):
    name = (drive_file.get("name") or "").upper()

    # Handle common typo as well.
    if "FROINT" in name:
        return "front"

    if re.search(r"\bFRONT\b", name.replace("-", " ").replace("_", " ")):
        return "front"

    if re.search(r"\bBACK\b", name.replace("-", " ").replace("_", " ")):
        return "back"

    return "single"


def confidence(score):
    if score >= 75:
        return "HIGH"

    if score >= 50:
        return "MEDIUM"

    return "LOW"


def process_item(item, drive_files):
    series_code = item.get("series_code")
    rule = item.get("series_rule") or {}

    result = {
        "order": item.get("order"),
        "line_item_id": item.get("line_item_id"),
        "product": item.get("product"),
        "variant": item.get("variant"),
        "sku": item.get("sku"),
        "quantity": item.get("quantity"),
        "shopify_image": (
            item.get("variant_image")
            or (item.get("fpd") or {}).get("_fpd-url")
        ),
        "fpd": item.get("fpd") or {},
        "series_code": series_code,
        "design_type": rule.get("design_type"),
        "design": extract_design(item.get("product")),
        "color": extract_color(item),
        "is_custom": item.get("is_custom", False),
        "status": None,
        "confidence": None,
        "matches": [],
    }

    # Custom artwork will be handled separately.
    if item.get("is_custom"):
        result["status"] = "CUSTOM"
        result["confidence"] = "N/A"
        return result

    candidates = [
        f for f in drive_files
        if allowed_drive_file(f, series_code)
    ]

    scored = []

    for file in candidates:
        score, reasons = score_candidate(item, file)

        if score <= 0:
            continue

        scored.append({
            "id": file.get("id"),
            "name": file.get("name"),
            "path": file.get("path"),
            "webViewLink": file.get("webViewLink"),
            "width": file.get("width"),
            "height": file.get("height"),
            "side": determine_side(file),
            "score": score,
            "reasons": reasons,
        })

    scored.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    design_type = rule.get("design_type")

    if design_type == "single":
        # Single-side series should use artwork without FRONT/BACK where possible.
        single_candidates = [
            x for x in scored
            if x["side"] == "single"
        ]

        pool = single_candidates or scored

        if not pool:
            result["status"] = "MISSING"
            result["confidence"] = "NONE"
            return result

        best = pool[0]

        result["matches"] = [best]
        result["confidence"] = confidence(best["score"])

        if best["score"] >= 75:
            result["status"] = "MATCHED"
        else:
            result["status"] = "REVIEW"

        return result

    if design_type == "double":
        fronts = [
            x for x in scored
            if x["side"] == "front"
        ]

        backs = [
            x for x in scored
            if x["side"] == "back"
        ]

        if not fronts or not backs:
            result["status"] = "MISSING"
            result["confidence"] = "NONE"

            # Keep best candidates for debugging.
            result["matches"] = scored[:5]
            return result

        best_front = fronts[0]
        best_back = backs[0]

        result["matches"] = [
            best_front,
            best_back,
        ]

        lowest_score = min(
            best_front["score"],
            best_back["score"]
        )

        result["confidence"] = confidence(lowest_score)

        if lowest_score >= 75:
            result["status"] = "MATCHED"
        else:
            result["status"] = "REVIEW"

        return result

    result["status"] = "REVIEW"
    result["confidence"] = "NONE"

    return result


def create_report(results):
    matched = [x for x in results if x["status"] == "MATCHED"]
    review = [x for x in results if x["status"] == "REVIEW"]
    missing = [x for x in results if x["status"] == "MISSING"]
    custom = [x for x in results if x["status"] == "CUSTOM"]

    lines = [
        "# Lucky Bags Artwork Match Report",
        "",
        "## Summary",
        "",
        f"- Total production candidates: **{len(results)}**",
        f"- Automatically matched: **{len(matched)}**",
        f"- Review required: **{len(review)}**",
        f"- Missing artwork: **{len(missing)}**",
        f"- Custom orders: **{len(custom)}**",
        "",
    ]

    for status_name, collection in [
        ("MATCHED", matched),
        ("REVIEW", review),
        ("MISSING", missing),
        ("CUSTOM", custom),
    ]:
        lines += [
            f"## {status_name}",
            "",
        ]

        if not collection:
            lines += ["None.", ""]
            continue

        for item in collection:
            lines += [
                f"### {item['order']} — {item['product']}",
                "",
                f"- Variant: `{item.get('variant') or ''}`",
                f"- SKU: `{item.get('sku') or ''}`",
                f"- Series: `{item.get('series_code') or ''}`",
                f"- Type: `{item.get('design_type') or ''}`",
                f"- Design: `{item.get('design') or ''}`",
                f"- Color: `{item.get('color') or ''}`",
                f"- Confidence: **{item.get('confidence')}**",
            ]

            if item["matches"]:
                lines.append("")
                lines.append("Drive candidate(s):")

                for match in item["matches"]:
                    lines.append(
                        f"- `{match['name']}` "
                        f"— {match['side']} "
                        f"— score {match['score']} "
                        f"— {', '.join(match['reasons'])}"
                    )

            lines.append("")

    return "\n".join(lines)


def main():
    if not SHOPIFY_FILE.exists():
        raise FileNotFoundError(
            f"Missing {SHOPIFY_FILE}. Run discover.py first."
        )

    if not DRIVE_FILE.exists():
        raise FileNotFoundError(
            f"Missing {DRIVE_FILE}. Run discover.py with Google Drive enabled first."
        )

    shopify = load_json(SHOPIFY_FILE)
    drive = load_json(DRIVE_FILE)

    production_items = [
        item for item in shopify
        if item.get("production_candidate")
    ]

    results = [
        process_item(item, drive)
        for item in production_items
    ]

    json_output = OUTPUT / "artwork_matches.json"
    report_output = OUTPUT / "MATCH_REPORT.md"

    with open(json_output, "w", encoding="utf-8") as f:
        json.dump(
            results,
            f,
            indent=2,
            ensure_ascii=False
        )

    report_output.write_text(
        create_report(results),
        encoding="utf-8"
    )

    print("")
    print("=== Lucky Bags Artwork Matcher ===")
    print("")

    statuses = {}

    for result in results:
        status = result["status"]
        statuses[status] = statuses.get(status, 0) + 1

    print(f"Production candidates : {len(results)}")
    print(f"MATCHED               : {statuses.get('MATCHED', 0)}")
    print(f"REVIEW                : {statuses.get('REVIEW', 0)}")
    print(f"MISSING               : {statuses.get('MISSING', 0)}")
    print(f"CUSTOM                : {statuses.get('CUSTOM', 0)}")

    print("")
    print(f"JSON   : {json_output}")
    print(f"Report : {report_output}")
    print("")


if __name__ == "__main__":
    main()