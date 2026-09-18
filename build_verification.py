import json
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "output" / "artwork_matches.json"
OUTPUT = ROOT / "output" / "verification.html"


def esc(value):
    return html.escape(str(value or ""))


def drive_thumbnail(file_id):
    if not file_id:
        return ""
    return f"https://drive.google.com/thumbnail?id={file_id}&sz=w800"


def status_class(status):
    return {
        "MATCHED": "matched",
        "REVIEW": "review",
        "MISSING": "missing",
        "CUSTOM": "custom",
    }.get(status, "unknown")


def artwork_card(match):
    image = drive_thumbnail(match.get("id"))

    return f"""
    <div class="artwork-card">
        <div class="artwork-label">
            DRIVE {esc((match.get("side") or "ARTWORK").upper())}
        </div>

        <div class="image-box">
            <img
                src="{esc(image)}"
                alt="{esc(match.get('name'))}"
                loading="lazy"
            >
        </div>

        <div class="filename">
            {esc(match.get("name"))}
        </div>

        <div class="small">
            Score: {esc(match.get("score"))}
        </div>

        <a
            class="drive-link"
            href="{esc(match.get('webViewLink'))}"
            target="_blank"
        >
            Open original in Google Drive
        </a>
    </div>
    """


def order_card(item):
    status = item.get("status") or "UNKNOWN"
    matches = item.get("matches") or []

    shopify_image = item.get("shopify_image")

    if shopify_image:
        shopify_image_html = f"""
            <div class="image-box">
                <img
                    src="{esc(shopify_image)}"
                    alt="Shopify product"
                    loading="lazy"
                >
            </div>
        """
    else:
        shopify_image_html = """
            <div class="image-box empty">
                No Shopify image
            </div>
        """

    drive_cards = ""

    if matches:
        drive_cards = "".join(
            artwork_card(match)
            for match in matches
        )
    else:
        drive_cards = """
            <div class="artwork-card">
                <div class="image-box empty">
                    No Drive artwork matched
                </div>
            </div>
        """

    return f"""
    <article class="order-card">

        <div class="order-header">
            <div>
                <div class="order-number">
                    {esc(item.get("order"))}
                </div>

                <h2>
                    {esc(item.get("product"))}
                </h2>
            </div>

            <span class="status {status_class(status)}">
                {esc(status)}
            </span>
        </div>

        <div class="details">
            <div>
                <span>Variant</span>
                <strong>{esc(item.get("variant") or "—")}</strong>
            </div>

            <div>
                <span>SKU</span>
                <strong>{esc(item.get("sku") or "—")}</strong>
            </div>

            <div>
                <span>Quantity</span>
                <strong>{esc(item.get("quantity"))}</strong>
            </div>

            <div>
                <span>Series</span>
                <strong>{esc(item.get("series_code"))}</strong>
            </div>

            <div>
                <span>Type</span>
                <strong>{esc(item.get("design_type"))}</strong>
            </div>

            <div>
                <span>Color</span>
                <strong>{esc(item.get("color") or "—")}</strong>
            </div>

            <div>
                <span>Confidence</span>
                <strong>{esc(item.get("confidence"))}</strong>
            </div>
        </div>

        <div class="comparison">

            <div class="shopify-card">
                <div class="artwork-label">
                    SHOPIFY ORDER IMAGE
                </div>

                {shopify_image_html}

                <div class="filename">
                    {esc(item.get("product"))}
                </div>
            </div>

            <div class="arrow">
                →
            </div>

            <div class="drive-area">
                {drive_cards}
            </div>

        </div>

    </article>
    """


def main():

    if not INPUT.exists():
        raise FileNotFoundError(
            f"{INPUT} not found. Run matcher.py first."
        )

    with open(INPUT, "r", encoding="utf-8") as f:
        items = json.load(f)

    counts = {}

    for item in items:
        status = item.get("status", "UNKNOWN")
        counts[status] = counts.get(status, 0) + 1

    cards = "\n".join(order_card(item) for item in items)

    page = f"""<!DOCTYPE html>
<html lang="en">

<head>
<meta charset="UTF-8">

<meta
    name="viewport"
    content="width=device-width, initial-scale=1.0"
>

<title>Lucky Bags Production Verification</title>

<style>

* {{
    box-sizing: border-box;
}}

body {{
    margin: 0;
    background: #f5f6f8;
    color: #202124;
    font-family:
        Arial,
        Helvetica,
        sans-serif;
}}

header {{
    background: #111;
    color: white;
    padding: 28px 36px;
}}

header h1 {{
    margin: 0 0 6px;
    font-size: 28px;
}}

header p {{
    margin: 0;
    color: #bbb;
}}

.summary {{
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    padding: 22px 36px;
    background: white;
    border-bottom: 1px solid #ddd;
}}

.summary-box {{
    min-width: 130px;
    padding: 12px 18px;
    border-radius: 8px;
    background: #f1f3f4;
}}

.summary-box strong {{
    display: block;
    font-size: 24px;
}}

.summary-box span {{
    font-size: 12px;
    text-transform: uppercase;
    color: #666;
}}

main {{
    max-width: 1500px;
    margin: 0 auto;
    padding: 28px;
}}

.order-card {{
    background: white;
    border: 1px solid #ddd;
    border-radius: 12px;
    margin-bottom: 24px;
    overflow: hidden;
}}

.order-header {{
    padding: 20px 24px;
    border-bottom: 1px solid #eee;
    display: flex;
    justify-content: space-between;
    gap: 20px;
    align-items: flex-start;
}}

.order-number {{
    font-weight: bold;
    color: #666;
    margin-bottom: 4px;
}}

.order-header h2 {{
    margin: 0;
    font-size: 21px;
}}

.status {{
    padding: 8px 12px;
    border-radius: 20px;
    font-weight: bold;
    font-size: 12px;
}}

.status.matched {{
    background: #dff5e5;
    color: #176b32;
}}

.status.review {{
    background: #fff1c9;
    color: #805d00;
}}

.status.missing {{
    background: #ffe0e0;
    color: #9b1c1c;
}}

.status.custom {{
    background: #e7e5ff;
    color: #4538a3;
}}

.details {{
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(150px, 1fr));
    gap: 16px;
    padding: 18px 24px;
    background: #fafafa;
    border-bottom: 1px solid #eee;
}}

.details span {{
    display: block;
    font-size: 11px;
    color: #777;
    text-transform: uppercase;
    margin-bottom: 4px;
}}

.details strong {{
    font-size: 14px;
}}

.comparison {{
    padding: 24px;
    display: grid;
    grid-template-columns:
        minmax(260px, 1fr)
        50px
        minmax(300px, 2fr);
    gap: 18px;
    align-items: center;
}}

.shopify-card,
.artwork-card {{
    min-width: 0;
}}

.drive-area {{
    display: grid;
    grid-template-columns:
        repeat(auto-fit, minmax(250px, 1fr));
    gap: 18px;
}}

.artwork-label {{
    font-size: 12px;
    font-weight: bold;
    margin-bottom: 10px;
    color: #555;
}}

.image-box {{
    width: 100%;
    min-height: 260px;
    background: #eee;
    border-radius: 8px;
    overflow: hidden;
    display: flex;
    align-items: center;
    justify-content: center;
}}

.image-box img {{
    width: 100%;
    height: 320px;
    object-fit: contain;
    background: white;
}}

.image-box.empty {{
    color: #999;
    padding: 30px;
    text-align: center;
}}

.filename {{
    margin-top: 10px;
    font-size: 13px;
    font-weight: bold;
    word-break: break-word;
}}

.small {{
    margin-top: 4px;
    color: #777;
    font-size: 12px;
}}

.drive-link {{
    display: inline-block;
    margin-top: 10px;
    font-size: 12px;
}}

.arrow {{
    font-size: 34px;
    text-align: center;
    color: #aaa;
}}

.warning {{
    margin: 0 36px 20px;
    padding: 12px 16px;
    background: #fff3cd;
    border: 1px solid #ffe69c;
    border-radius: 8px;
    font-size: 13px;
}}

@media (max-width: 850px) {{

    .comparison {{
        grid-template-columns: 1fr;
    }}

    .arrow {{
        transform: rotate(90deg);
    }}

}}

</style>
</head>

<body>

<header>
    <h1>Lucky Bags Production Verification</h1>
    <p>
        Shopify order image vs Google Drive production artwork
    </p>
</header>

<section class="summary">

    <div class="summary-box">
        <strong>{len(items)}</strong>
        <span>Total</span>
    </div>

    <div class="summary-box">
        <strong>{counts.get("MATCHED", 0)}</strong>
        <span>Matched</span>
    </div>

    <div class="summary-box">
        <strong>{counts.get("REVIEW", 0)}</strong>
        <span>Review</span>
    </div>

    <div class="summary-box">
        <strong>{counts.get("MISSING", 0)}</strong>
        <span>Missing</span>
    </div>

    <div class="summary-box">
        <strong>{counts.get("CUSTOM", 0)}</strong>
        <span>Custom</span>
    </div>

</section>

<div class="warning">
    Verification only. Nothing on this page can print or modify Shopify/Google Drive.
</div>

<main>
{cards}
</main>

</body>
</html>
"""

    OUTPUT.write_text(page, encoding="utf-8")

    print("")
    print("=== Verification Page Generated ===")
    print("")
    print(f"Orders  : {len(items)}")
    print(f"Matched : {counts.get('MATCHED', 0)}")
    print(f"Review  : {counts.get('REVIEW', 0)}")
    print(f"Missing : {counts.get('MISSING', 0)}")
    print(f"Custom  : {counts.get('CUSTOM', 0)}")
    print("")
    print(f"Page: {OUTPUT}")
    print("")


if __name__ == "__main__":
    main()