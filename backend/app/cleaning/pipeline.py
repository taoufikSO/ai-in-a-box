# backend/app/cleaning/pipeline.py
import pandas as pd
from rapidfuzz import fuzz
from .synonyms import HEADER_SYNONYMS, CANONICAL_ORDER
from .utils import norm_header, parse_date, parse_number, currency_code

CANONICAL = set(CANONICAL_ORDER)

def map_headers(df: pd.DataFrame) -> pd.DataFrame:
    rename = {}
    for c in df.columns:
        k = norm_header(str(c))
        target = HEADER_SYNONYMS.get(k)
        rename[c] = target if target else k.replace(" ", "_")
    return df.rename(columns=rename)

def compute_line_total(row):
    q = parse_number(row.get("quantity"))
    p = parse_number(row.get("unit_price"))
    if q is not None and p is not None:
        return round(q * p, 2)
    return parse_number(row.get("line_total"))

def clean_invoices(df_in: pd.DataFrame, config: dict | None = None):
    # ---- config ----
    config = config or {}
    fuzzy_threshold = int(config.get("fuzzy_threshold", 90))
    drop_dupes = bool(config.get("drop_duplicates", True))
    drop_negative_qty = bool(config.get("drop_negative_qty", False))
    flag_due_before_issue = bool(config.get("flag_due_before_issue", True))

    # ---- copy + header map ----
    df = df_in.copy()
    df = map_headers(df)

    # header mapping preview (original -> mapped)
    header_map = {}
    for c in df_in.columns:
        k = norm_header(str(c))
        mapped = HEADER_SYNONYMS.get(k, k.replace(" ", "_"))
        header_map[str(c)] = mapped

    # ---- normalize core fields ----
    for col in list(df.columns):
        low = col.lower()
        if low in ("issue_date", "due_date"):
            df[low] = df[low].map(parse_date) if low in df else None
        elif low in ("quantity", "unit_price", "line_total", "tax_rate",
                     "tax_amount", "total_before_tax", "total_amount"):
            df[low] = df[low].map(parse_number)
        elif low == "currency":
            df[low] = df[low].map(currency_code)

    # ---- recompute derived totals ----
    if "line_total" not in df:
        df["line_total"] = None
    df["line_total"] = df.apply(compute_line_total, axis=1)

    if "invoice_id" in df:
        grp = df.groupby("invoice_id", dropna=False)
        sum_lines = grp["line_total"].sum().round(2)
        if "total_before_tax" not in df:
            df["total_before_tax"] = None
        df = df.merge(
            sum_lines.rename("calc_total_before_tax"),
            left_on="invoice_id",
            right_index=True,
            how="left",
        )
        df["total_before_tax"] = df["total_before_tax"].fillna(df["calc_total_before_tax"])
        if "tax_amount" not in df:
            df["tax_amount"] = None
        if "tax_rate" in df:
            df["tax_amount"] = df["tax_amount"].fillna(
                (df["total_before_tax"] * df["tax_rate"]).round(2)
            )
        if "total_amount" not in df:
            df["total_amount"] = None
        df["total_amount"] = df["total_amount"].fillna(
            (df["total_before_tax"] + (df["tax_amount"].fillna(0))).round(2)
        )
        df.drop(columns=["calc_total_before_tax"], errors="ignore", inplace=True)

    # ---- anomaly flags ----
    def row_issues(r):
        tags = []
        if r.get("quantity") is not None and r["quantity"] < 0:
            tags.append("NEGATIVE_QTY")
        if r.get("unit_price") is not None and r["unit_price"] < 0:
            tags.append("NEGATIVE_PRICE")
        if flag_due_before_issue and r.get("issue_date") and r.get("due_date") and r["due_date"] < r["issue_date"]:
            tags.append("DUE_BEFORE_ISSUE")
        if r.get("tax_rate") is not None and not (0 <= r["tax_rate"] <= 0.5):
            tags.append("TAX_RATE_OUT_OF_RANGE")
        return "|".join(tags) if tags else ""

    df["__issues"] = df.apply(row_issues, axis=1)

    # optionally drop negative qty rows
    removed_neg = 0
    if drop_negative_qty and "quantity" in df.columns:
        before_drop = len(df)
        df = df[~(df["quantity"].fillna(0) < 0)].reset_index(drop=True)
        removed_neg = before_drop - len(df)

    # ---- duplicate removal (hard + soft) ----
    dup_removed = 0
    if drop_dupes:
        if "invoice_id" in df:
            before = len(df)
            df = df.drop_duplicates(
                subset=["invoice_id", "item_description", "line_total"], keep="first"
            )
            dup_removed += before - len(df)

        if {"customer_name", "total_amount", "issue_date"}.issubset(df.columns):
            df = df.sort_values(by=["customer_name", "issue_date"]).reset_index(drop=True)
            to_drop = []
            for i in range(1, len(df)):
                a, b = df.iloc[i - 1], df.iloc[i]
                if abs((b["total_amount"] or 0) - (a["total_amount"] or 0)) <= 0.01:
                    if fuzz.ratio(str(a["customer_name"]), str(b["customer_name"])) >= fuzzy_threshold:
                        to_drop.append(i)
            dup_removed += len(to_drop)
            if to_drop:
                df = df.drop(df.index[to_drop]).reset_index(drop=True)

    # ---- summary & preview ----
    profile = {
        "rows_in": len(df_in),
        "rows_out": len(df),
        "duplicates_removed": dup_removed,
        "errors_fixed": int((df["__issues"] != "").sum()),
        "currency_detected": (
            df["currency"].dropna().iloc[0]
            if "currency" in df and df["currency"].notna().any()
            else None
        ),
    }

    ordered = [c for c in CANONICAL_ORDER if c in df.columns] + \
              [c for c in df.columns if c not in CANONICAL and c != "__issues"] + \
              ["__issues"]
    df = df[ordered]

    preview = {
        "before": df_in.head(10).fillna("").astype(str).values.tolist(),
        "after": df.head(10).fillna("").astype(str).values.tolist(),
    }

    issues_series = df["__issues"].fillna("").str.split("|").explode()
    issues_series = issues_series[issues_series.str.len() > 0]
    issues_summary = issues_series.value_counts().to_dict()

    tips = []
    if dup_removed > 0:
        tips.append(f"Removed {dup_removed} duplicate rows. Consider adding unique invoice IDs upstream.")
    if removed_neg > 0:
        tips.append(f"Dropped {removed_neg} rows with negative quantities.")
    if issues_summary.get("DUE_BEFORE_ISSUE"):
        tips.append("Some invoices have due_date before issue_date; enforce date validation.")
    if issues_summary.get("TAX_RATE_OUT_OF_RANGE"):
        tips.append("Tax rate out of expected range (0–50%); verify tax tables.")
    if profile["currency_detected"] is None and "currency" in df.columns:
        tips.append("Missing currency codes; standardize to ISO-4217 (e.g., USD, EUR, GBP).")
    if not tips:
        tips.append("No critical anomalies detected under current settings.")

    return {
        "profile": profile,
        "issues_summary": issues_summary,
        "ai_feedback": tips,
        "header_map": header_map,
        "preview": preview,
        "clean_df": df,
        "applied_rules": {
            "fuzzy_threshold": fuzzy_threshold,
            "drop_duplicates": drop_dupes,
            "drop_negative_qty": drop_negative_qty,
            "flag_due_before_issue": flag_due_before_issue,
        },
    }
