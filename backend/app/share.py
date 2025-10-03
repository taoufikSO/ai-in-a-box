# backend/app/share.py
import os
import pandas as pd
from io import BytesIO

HTML_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <style>
    body {{ font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 24px; color: #222; }}
    .wrap {{ max-width: 1100px; margin: 0 auto; }}
    h1 {{ font-size: 22px; margin: 0 0 8px; }}
    .sub {{ color: #666; margin-bottom: 16px; }}
    table {{ border-collapse: collapse; width: 100%; font-size: 13px; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 8px 10px; }}
    th {{ background: #f8fafc; text-align: left; position: sticky; top: 0; }}
    .note {{ margin-top: 10px; color: #6b7280; }}
    .pill {{ display:inline-block; padding: 2px 8px; border-radius: 9999px; background:#eef2ff; color:#3730a3; font-size:12px; }}
    .btn {{ display:inline-block; padding:8px 12px; border-radius:8px; background:#111827; color:white; text-decoration:none; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>AI-in-a-Box • {heading}</h1>
    <div class="sub">Public preview (read-only) • <span class="pill">{kind}</span></div>
    {table_html}
    <p class="note">Showing up to the first {limit} rows. Download the full file from the app.</p>
  </div>
</body>
</html>
"""

def read_any(path: str) -> pd.DataFrame:
    if path.lower().endswith(".csv"):
        return pd.read_csv(path)
    if path.lower().endswith(".xlsx") or path.lower().endswith(".xls"):
        return pd.read_excel(path)
    raise ValueError("Unsupported file type")

def render_share_page(file_path: str, kind: str = "invoices", limit: int = 200) -> bytes:
    df = read_any(file_path)
    df_show = df.head(limit)
    table_html = df_show.to_html(index=False, escape=False)
    html = HTML_TEMPLATE.format(
        title=f"AI-in-a-Box • {kind.title()}",
        heading=f"Cleaned {kind}",
        table_html=table_html,
        kind=kind.title(),
        limit=limit,
    )
    return html.encode("utf-8")
