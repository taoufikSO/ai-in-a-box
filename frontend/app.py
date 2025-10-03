# frontend/app.py
import os
import io
import requests
import pandas as pd
import streamlit as st

# ------------------ Config ------------------
API_URL = os.getenv("API_URL", "http://localhost:8000")  # internal base for API requests
PUBLIC_BACKEND_BASE = os.getenv("PUBLIC_BACKEND_BASE", API_URL)  # what the BROWSER should open

def public_link(path: str) -> str:
    """Join a backend path with a browser-reachable base URL."""
    if not path.startswith("/"):
        path = "/" + path
    return PUBLIC_BACKEND_BASE.rstrip("/") + path

st.set_page_config(page_title="AI-in-a-Box", layout="wide")
st.title("AI-in-a-Box")

# ------------------ Helpers ------------------
def api_online() -> bool:
    try:
        return requests.get(f"{API_URL}/health", timeout=5).ok
    except Exception:
        return False

def _ensure_state_keys():
    for k in [
        "last_inv", "last_stock",
        "demo_inv_active", "demo_stock_active",
        "_demo_inv_bytes", "_demo_inv_name",
        "_demo_stock_bytes", "_demo_stock_name",
    ]:
        if k not in st.session_state:
            st.session_state[k] = None

def _clear_inv_demo():
    st.session_state["demo_inv_active"] = False
    st.session_state["_demo_inv_bytes"] = None
    st.session_state["_demo_inv_name"] = None

def _clear_stock_demo():
    st.session_state["demo_stock_active"] = False
    st.session_state["_demo_stock_bytes"] = None
    st.session_state["_demo_stock_name"] = None

def file_from_upload_or_demo(upload, demo_active, demo_bytes_key, demo_name_key):
    """Return ('real'|'demo'|None, file_like) where file_like has .name and .getvalue()."""
    if upload is not None:
        return ("real", upload)
    if demo_active and st.session_state.get(demo_bytes_key):
        class _Demo:
            name = st.session_state.get(demo_name_key, "demo.csv")
            type = "text/csv"
            def getvalue(self):
                return st.session_state[demo_bytes_key].getvalue()
        return ("demo", _Demo())
    return (None, None)

def impact_card(profile: dict, hourly_rate: float = 25.0):
    rows_in  = profile.get("rows_in", 0) or 0
    rows_out = profile.get("rows_out", 0) or 0
    dupes    = profile.get("duplicates_removed", 0) or 0
    errors   = profile.get("errors_fixed", 0) or 0
    minutes_saved = (dupes + errors) * 0.5
    cost_saved = (minutes_saved / 60.0) * hourly_rate
    c1, c2, c3 = st.columns(3)
    c1.metric("Minutes saved (est.)", f"{minutes_saved:.1f}")
    c2.metric("Estimated cost saved", f"${cost_saved:,.2f}")
    c3.metric("Rows processed", f"{rows_in} → {rows_out}")

# ------------------ App ------------------
_online = api_online()
st.info(f"API: {'ONLINE ✅' if _online else 'OFFLINE ❌'} → {API_URL}")
_ensure_state_keys()

tabs = st.tabs(["💸 Invoices", "📦 Stock"])

# ------------------ Invoices ------------------
with tabs[0]:
    with st.expander("Settings", expanded=False):
        colA, colB = st.columns(2)
        with colA:
            st.slider("Fuzzy duplicate threshold", 70, 100, 90, 1, key="inv_fuzzy")
            st.checkbox("Drop duplicates", value=True, key="inv_drop_dupes")
            st.checkbox("Drop rows with negative quantity", value=False, key="inv_drop_negative")
        with colB:
            st.checkbox("Flag due date before issue date", value=True, key="inv_flag_due")
        st.caption("Settings affect invoice cleaning on the server.")

    SAMPLE_INV = """Invoice No,Date,Due,Client,Item,Qty,Unit Price,TVA,Currency,Total
INV-001,2025/09/01,2025/09/30,Acme,Widgets,2,50,0.2,USD,120
INV-001,2025/09/01,2025/09/30,Acme,Widgets,2,50,0.2,USD,120
INV-002,09-02-2025,2025-09-10,Delta,Gadgets,-1,100,0.2,USD,100
INV-003,2025-09-03,2025-08-30,Gamma,Brackets,3,25,0.15,USD,86.25
"""
    c_demo = st.columns([1, 1, 5, 1])
    if c_demo[0].button("Use sample invoice file", key="btn_demo_inv"):
        st.session_state["demo_inv_active"] = True
        st.session_state["_demo_inv_bytes"] = io.BytesIO(SAMPLE_INV.encode("utf-8"))
        st.session_state["_demo_inv_name"] = "demo_invoices.csv"
        st.success("Sample enabled.")
    if c_demo[1].button("Clear sample", key="btn_clear_inv"):
        _clear_inv_demo()
        st.info("Sample cleared. Upload a file to analyze.")
    if c_demo[3].button("Download sample", key="btn_dl_inv_sample"):
        try:
            s = requests.get(f"{API_URL}/api/sample/invoice", timeout=10)
            st.download_button("Click to download sample CSV", s.content, "sample_invoices.csv", "text/csv", key="dl_real_inv_sample")
        except Exception as e:
            st.error(f"Failed to fetch sample: {e}")

    uploaded_inv = st.file_uploader("Upload invoice CSV/XLSX", type=["csv", "xlsx"], key="inv_upl")
    src_kind, inv_file = file_from_upload_or_demo(
        uploaded_inv,
        bool(st.session_state.get("demo_inv_active")),
        "_demo_inv_bytes",
        "_demo_inv_name",
    )
    fmt_inv = st.selectbox("Export format (Invoices)", ["csv", "xlsx"], index=0, key="fmt_inv")

    if inv_file:
        if not _online:
            st.warning("API offline — local preview only.")
            try:
                if inv_file.name.endswith(".csv"):
                    dfp = pd.read_csv(io.BytesIO(inv_file.getvalue()))
                else:
                    dfp = pd.read_excel(io.BytesIO(inv_file.getvalue()))
                st.dataframe(dfp.head(10))
            except Exception as e:
                st.error(f"Failed to read file: {e}")
        else:
            if src_kind == "real":
                _clear_inv_demo()  # ensure we don’t stay “stuck” on the sample
            with st.spinner("Cleaning invoices..."):
                try:
                    files = {"file": (inv_file.name, inv_file.getvalue(), getattr(inv_file, "type", "text/csv"))}
                    params = {
                        "fmt": fmt_inv,
                        "fuzzy": st.session_state["inv_fuzzy"],
                        "drop_dupes": st.session_state["inv_drop_dupes"],
                        "drop_negative_qty": st.session_state["inv_drop_negative"],
                        "flag_due_issue": st.session_state["inv_flag_due"],
                    }
                    r = requests.post(f"{API_URL}/api/clean", files=files, params=params, timeout=120)
                    if r.ok:
                        st.session_state["last_inv"] = r.json()
                        st.success("Invoices cleaned ✅")
                    else:
                        st.error(f"API error: {r.status_code} — {r.text}")
                except Exception as e:
                    st.error(f"Request failed: {e}")

    inv = st.session_state.get("last_inv")
    if inv:
        prof = inv.get("profile", {})
        impact_card(prof, hourly_rate=25.0)

        prev = inv.get("preview", {})
        st.write("**Before (sample)**")
        st.dataframe(pd.DataFrame(prev.get("before", [])))
        st.write("**After (sample)**")
        st.dataframe(pd.DataFrame(prev.get("after", [])))

        hmap = inv.get("header_map", {})
        if hmap:
            st.write("**Header mapping (original → canonical)**")
            st.table(pd.DataFrame({"original": list(hmap.keys()), "mapped_to": list(hmap.values())}))

        issues = inv.get("issues_summary", {})
        if issues:
            st.write("**Issues (summary)**")
            st.table(
                pd.DataFrame({"issue": list(issues.keys()), "count": list(issues.values())})
                .sort_values("count", ascending=False)
                .reset_index(drop=True)
            )

        notes = inv.get("ai_feedback", [])
        if notes:
            st.write("**AI notes**")
            for n in notes:
                st.markdown(f"- {n}")

        # ---- Share + Download (Invoices) ----
        top_col = st.columns([2, 1])
        share_url = inv.get("share_url")
        if share_url:
            full_share = public_link(share_url)          # <— use PUBLIC_BACKEND_BASE
            top_col[0].code(full_share)                  # shows http://localhost:8000/share/...
            top_col[0].markdown(f"[Open share link]({full_share})")

        tok = inv.get("download_token")
        if tok:
            try:
                url = f"{API_URL}/api/download/{tok}?fmt={fmt_inv}"
                content = requests.get(url, timeout=120).content
                top_col[1].download_button(
                    "⬇️ Download",
                    data=content,
                    file_name=f"cleaned_invoices.{fmt_inv}",
                    mime="text/csv" if fmt_inv == "csv"
                         else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_inv",
                )
            except Exception as e:
                st.error(f"Download failed: {e}")

# ------------------ Stock ------------------
with tabs[1]:
    with st.expander("Settings", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            st.slider("Expiring soon (days)", 7, 120, 30, 1, key="stock_days_exp")
        with col2:
            st.checkbox("Drop rows with negative quantity", value=False, key="stock_drop_negative")
        st.caption("Settings affect stock cleaning on the server.")

    SAMPLE_STOCK = """SKU,Name,Supplier,Qty,Reorder Point,Expiry Date
SKU-1,Protein Bar,Acme,5,10,2025-10-05
SKU-2,Yogurt Cup,Delta,25,10,2025-10-15
SKU-3,Olive Oil,Gamma,0,5,2025-09-28
SKU-4,Granola,Beta,-2,5,2025-11-20
SKU-5,Cheese,Acme,7,7,2025-10-01
"""
    c_demo = st.columns([1, 1, 5, 1])
    if c_demo[0].button("Use sample stock file", key="btn_demo_stock"):
        st.session_state["demo_stock_active"] = True
        st.session_state["_demo_stock_bytes"] = io.BytesIO(SAMPLE_STOCK.encode("utf-8"))
        st.session_state["_demo_stock_name"] = "demo_stock.csv"
        st.success("Sample enabled.")
    if c_demo[1].button("Clear sample", key="btn_clear_stock"):
        _clear_stock_demo()
        st.info("Sample cleared. Upload a file to analyze.")
    if c_demo[3].button("Download sample", key="btn_dl_stock_sample"):
        try:
            s = requests.get(f"{API_URL}/api/sample/stock", timeout=10)
            st.download_button("Click to download sample CSV", s.content, "sample_stock.csv", "text/csv", key="dl_real_stock_sample")
        except Exception as e:
            st.error(f"Failed to fetch sample: {e}")

    uploaded_stock = st.file_uploader("Upload stock CSV/XLSX", type=["csv", "xlsx"], key="stock_upl")
    src_kind, stock_file = file_from_upload_or_demo(
        uploaded_stock,
        bool(st.session_state.get("demo_stock_active")),
        "_demo_stock_bytes",
        "_demo_stock_name",
    )
    fmt_stock = st.selectbox("Export format (Stock)", ["csv", "xlsx"], index=0, key="fmt_stock")

    if stock_file:
        if not _online:
            st.warning("API offline — local preview only.")
            try:
                if stock_file.name.endswith(".csv"):
                    sdf = pd.read_csv(io.BytesIO(stock_file.getvalue()))
                else:
                    sdf = pd.read_excel(io.BytesIO(stock_file.getvalue()))
                st.dataframe(sdf.head(10))
            except Exception as e:
                st.error(f"Failed to read file: {e}")
        else:
            if src_kind == "real":
                _clear_stock_demo()
            with st.spinner("Cleaning stock..."):
                try:
                    files = {"file": (stock_file.name, stock_file.getvalue(), getattr(stock_file, "type", "text/csv"))}
                    params = {
                        "fmt": fmt_stock,
                        "days_expiring": st.session_state["stock_days_exp"],
                        "drop_negative_qty": st.session_state["stock_drop_negative"],
                    }
                    r = requests.post(f"{API_URL}/api/stock/clean", files=files, params=params, timeout=120)
                    if r.ok:
                        st.session_state["last_stock"] = r.json()
                        st.success("Stock cleaned ✅")
                    else:
                        st.error(f"API error: {r.status_code} — {r.text}")
                except Exception as e:
                    st.error(f"Request failed: {e}")

    stk = st.session_state.get("last_stock")
    if stk:
        prof = stk.get("profile", {})
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Rows in", prof.get("rows_in", "-"))
        c2.metric("Rows out", prof.get("rows_out", "-"))
        c3.metric("Low stock", prof.get("low_stock", "-"))
        c4.metric("Expiring soon", prof.get("expiring_soon", "-"))

        prev = stk.get("preview", {})
        st.write("**Before (sample)**")
        st.dataframe(pd.DataFrame(prev.get("before", [])))
        st.write("**After (sample)**")
        st.dataframe(pd.DataFrame(prev.get("after", [])))

        issues = stk.get("issues_summary", {})
        if issues:
            st.write("**Issues (summary)**")
            st.table(
                pd.DataFrame({"issue": list(issues.keys()), "count": list(issues.values())})
                .sort_values("count", ascending=False)
                .reset_index(drop=True)
            )

        notes = stk.get("ai_feedback", [])
        if notes:
            st.write("**AI notes**")
            for n in notes:
                st.markdown(f"- {n}")

        # ---- Share + Download (Stock) ----
        top_col = st.columns([2, 1])
        share_url = stk.get("share_url")
        if share_url:
            full_share = public_link(share_url)          # <— use PUBLIC_BACKEND_BASE
            top_col[0].code(full_share)
            top_col[0].markdown(f"[Open share link]({full_share})")

        tok = stk.get("download_token")
        if tok:
            try:
                url = f"{API_URL}/api/download/{tok}?fmt={fmt_stock}"
                content = requests.get(url, timeout=120).content
                top_col[1].download_button(
                    "⬇️ Download",
                    data=content,
                    file_name=f"cleaned_stock.{fmt_stock}",
                    mime="text/csv" if fmt_stock == "csv"
                         else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_stock",
                )
            except Exception as e:
                st.error(f"Download failed: {e}")
