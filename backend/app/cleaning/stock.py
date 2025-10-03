# backend/app/cleaning/stock.py
import pandas as pd
from datetime import datetime, timedelta, date
from .utils import norm_header, parse_number

# Internal column names to avoid collisions with user uploads
INTERNAL_ISSUES_COL = "__aibox_issues"
INTERNAL_EXP_DATE_COL = "__aibox_exp_dt"

# Header synonyms for stock schemas (all lowercase keys)
STOCK_HEADER_SYNONYMS = {
    "sku": "sku",
    "product": "name",
    "product name": "name",
    "name": "name",
    "item": "name",

    "qty": "qty_on_hand",
    "quantity": "qty_on_hand",
    "qty_on_hand": "qty_on_hand",
    "on hand": "qty_on_hand",
    "onhand": "qty_on_hand",

    "reorder_point": "reorder_point",
    "reorder point": "reorder_point",
    "min qty": "reorder_point",
    "minimum qty": "reorder_point",

    "expiry": "expiry_date",
    "expiry date": "expiry_date",
    "expiration": "expiry_date",
    "expiration date": "expiry_date",
    "expire date": "expiry_date",
    "best before": "expiry_date",
    "bbd": "expiry_date",

    "supplier": "supplier",
    "vendor": "supplier",
}

CANONICAL_ORDER_STOCK = [
    "sku", "name", "supplier",
    "qty_on_hand", "reorder_point",
    "expiry_date",
    "__issues",
]


def _map_headers(df: pd.DataFrame) -> pd.DataFrame:
    """Rename headers to canonical names using STOCK_HEADER_SYNONYMS."""
    rename = {}
    for c in df.columns:
        k = norm_header(str(c))
        tgt = STOCK_HEADER_SYNONYMS.get(k, k.replace(" ", "_"))
        rename[c] = tgt
    return df.rename(columns=rename)


def _safe_to_date(value) -> date | None:
    """
    Convert many date-like inputs to a Python date safely.
    """
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        try:
            return value.date()
        except Exception:
            pass
    try:
        ts = pd.to_datetime(value, errors="coerce", utc=False)
        if pd.isna(ts):
            return None
        return ts.date()
    except Exception:
        return None


def clean_stock(df_in: pd.DataFrame, days_expiring: int = 30, drop_negative_qty: bool = False):
    """
    Normalize a stock file and flag:
      - LOW_STOCK (qty_on_hand <= reorder_point)
      - EXPIRING_SOON (expiry_date <= today + days_expiring)
      - EXPIRED (expiry_date < today)
      - NEGATIVE_QTY (qty_on_hand < 0)
    Works even if some columns are missing. Uses internal cols to avoid name clashes.
    """
    # 1) Map headers and copy
    df = _map_headers(df_in.copy())

    # 2) Normalize numbers
    if "qty_on_hand" in df.columns:
        df["qty_on_hand"] = df["qty_on_hand"].map(parse_number)
    if "reorder_point" in df.columns:
        df["reorder_point"] = df["reorder_point"].map(parse_number)

    # 3) Normalize expiry date (keep internal date; show ISO string)
    if "expiry_date" in df.columns:
        df[INTERNAL_EXP_DATE_COL] = df["expiry_date"].map(_safe_to_date)
        df["expiry_date"] = df[INTERNAL_EXP_DATE_COL].map(lambda d: d.isoformat() if d else None)
    else:
        df[INTERNAL_EXP_DATE_COL] = None

    # 4) Build issues into an INTERNAL col
    today = datetime.utcnow().date()
    soon_cutoff = today + timedelta(days=int(days_expiring))

    def _row_issues(r):
        tags = []
        q = r.get("qty_on_hand")
        rop = r.get("reorder_point")
        exp_dt = r.get(INTERNAL_EXP_DATE_COL)

        if q is not None and rop is not None and q <= rop:
            tags.append("LOW_STOCK")
        if exp_dt:
            if exp_dt < today:
                tags.append("EXPIRED")
            elif exp_dt <= soon_cutoff:
                tags.append("EXPIRING_SOON")
        if q is not None and q < 0:
            tags.append("NEGATIVE_QTY")
        return "|".join(tags) if tags else ""

    df[INTERNAL_ISSUES_COL] = df.apply(_row_issues, axis=1)

    # 5) Optional drop negative rows
    removed_neg = 0
    if drop_negative_qty and "qty_on_hand" in df.columns:
        before = len(df)
        df = df[~(df["qty_on_hand"].fillna(0) < 0)].reset_index(drop=True)
        removed_neg = before - len(df)

    # 6) Build summary strictly from the INTERNAL issues Series
    issues_series = df[INTERNAL_ISSUES_COL].fillna("").astype(str).str.split("|", regex=False).explode()
    issues_series = issues_series[issues_series.str.len() > 0]
    issues_summary = issues_series.value_counts().to_dict()

    # 7) Presentable __issues column (copy from internal after summary is computed)
    df["__issues"] = df[INTERNAL_ISSUES_COL]

    # 8) Order columns
    ordered = [c for c in CANONICAL_ORDER_STOCK if c in df.columns] + \
              [c for c in df.columns if c not in CANONICAL_ORDER_STOCK and c not in (INTERNAL_ISSUES_COL, INTERNAL_EXP_DATE_COL)] + \
              ["__issues"]
    df = df[ordered]

    # 9) Build preview
    preview = {
        "before": df_in.head(10).fillna("").astype(str).values.tolist(),
        "after": df.head(10).fillna("").astype(str).values.tolist(),
    }

    # 10) Tips and profile
    tips = []
    if issues_summary.get("LOW_STOCK"):
        tips.append("Some items are below or equal to reorder point — reorder suggested.")
    if issues_summary.get("EXPIRING_SOON"):
        tips.append("Items expiring soon — consider promotions or returns.")
    if issues_summary.get("EXPIRED"):
        tips.append("Expired items found — remove from sellable stock.")
    if removed_neg > 0:
        tips.append(f"Dropped {removed_neg} rows with negative quantities.")
    if not tips:
        tips.append("No critical stock anomalies detected under current settings.")

    profile = {
        "rows_in": len(df_in),
        "rows_out": len(df),
        "low_stock": int(issues_summary.get("LOW_STOCK", 0)),
        "expiring_soon": int(issues_summary.get("EXPIRING_SOON", 0)),
        "expired": int(issues_summary.get("EXPIRED", 0)),
        "negative_qty_dropped": removed_neg,
    }

    # 11) Remove internal columns (no longer needed)
    df.drop(columns=[INTERNAL_ISSUES_COL, INTERNAL_EXP_DATE_COL], errors="ignore", inplace=True)

    return {
        "profile": profile,
        "issues_summary": issues_summary,
        "ai_feedback": tips,
        "preview": preview,
        "clean_df": df,
    }
