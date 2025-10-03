# backend/app/main.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, Response

from app.config import settings
from app.cleaning.pipeline import clean_invoices
from app.cleaning.stock import clean_stock
from app.exporters import export_xlsx_styled
from app.share import render_share_page

import pandas as pd
import io, uuid, os, tempfile

# ---------------------------------------------------------
# Create FastAPI app
# ---------------------------------------------------------
app = FastAPI(title="AI-in-a-Box API", version="0.3.0")

# Allow frontend to call the API
origins = [o.strip() for o in settings.CORS_ORIGINS.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Basic endpoints
# ---------------------------------------------------------
@app.get("/")
def root():
    return {"name": "AI-in-a-Box API", "status": "ok"}

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/version")
def version():
    return {"version": "0.3.0"}

# ---------------------------------------------------------
# Shared temp tokens for downloads + sharing
# ---------------------------------------------------------
TMP_DIR = tempfile.gettempdir()
TOKENS: dict[str, str] = {}       # token -> absolute file path
TOKENS_KIND: dict[str, str] = {}  # token -> "invoices" | "stock"

def _save_cleaned(result: dict, fmt: str, prefix: str, kind: str):
    token = str(uuid.uuid4())
    ext = "xlsx" if fmt == "xlsx" else "csv"
    out_path = os.path.join(TMP_DIR, f"{prefix}_{token}.{ext}")

    try:
        if fmt == "xlsx":
            data = export_xlsx_styled(result["clean_df"])
            with open(out_path, "wb") as f:
                f.write(data)
        else:
            result["clean_df"].to_csv(out_path, index=False, encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"Failed to write cleaned file: {e}")

    TOKENS[token] = out_path
    TOKENS_KIND[token] = kind
    del result["clean_df"]
    result["download_token"] = token
    result["share_url"] = f"/share/{token}"
    return result

# ---------------------------------------------------------
# Invoices cleaning
# ---------------------------------------------------------
@app.post("/api/clean")
async def api_clean(
    file: UploadFile = File(...),
    fmt: str = "csv",
    fuzzy: int = 90,
    drop_dupes: bool = True,
    drop_negative_qty: bool = False,
    flag_due_issue: bool = True,
):
    name = file.filename or ""
    if not (name.endswith(".csv") or name.endswith(".xlsx")):
        raise HTTPException(400, "Only CSV or XLSX allowed")

    data = await file.read()

    MAX = 50 * 1024 * 1024
    if len(data) > MAX:
        raise HTTPException(413, "File too large (max 50MB)")

    try:
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(data))
        else:
            df = pd.read_excel(io.BytesIO(data))
    except Exception as e:
        raise HTTPException(400, f"Failed to read file: {e}")

    config = {
        "fuzzy_threshold": int(fuzzy),
        "drop_duplicates": bool(drop_dupes),
        "drop_negative_qty": bool(drop_negative_qty),
        "flag_due_before_issue": bool(flag_due_issue),
    }
    result = clean_invoices(df, config=config)
    return JSONResponse(_save_cleaned(result, fmt, "aibox_inv", "invoices"))

# ---------------------------------------------------------
# Stock cleaning
# ---------------------------------------------------------
@app.post("/api/stock/clean")
async def api_clean_stock(
    file: UploadFile = File(...),
    fmt: str = "csv",
    days_expiring: int = 30,
    drop_negative_qty: bool = False,
):
    name = file.filename or ""
    if not (name.endswith(".csv") or name.endswith(".xlsx")):
        raise HTTPException(400, "Only CSV or XLSX allowed")

    try:
        raw = await file.read()
        if name.endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw))
        else:
            df = pd.read_excel(io.BytesIO(raw))

        if df is None or len(df) == 0:
            raise HTTPException(400, "No rows detected in file.")

        result = clean_stock(df, days_expiring=int(days_expiring), drop_negative_qty=bool(drop_negative_qty))
        return JSONResponse(_save_cleaned(result, fmt, "aibox_stock", "stock"))

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not process stock file: {e}")

# ---------------------------------------------------------
# Download endpoint (shared)
# ---------------------------------------------------------
@app.get("/api/download/{token}")
def api_download(token: str, fmt: str = "csv"):
    path = TOKENS.get(token)
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Token expired or not found")

    mime = (
        "text/csv"
        if fmt == "csv"
        else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    return StreamingResponse(
        open(path, "rb"),
        media_type=mime,
        headers={
            "Content-Disposition": f'attachment; filename="cleaned.{fmt}"'
        },
    )

# ---------------------------------------------------------
# Public share page
# ---------------------------------------------------------
@app.get("/share/{token}")
def share_preview(token: str):
    path = TOKENS.get(token)
    if not path or not os.path.exists(path):
        raise HTTPException(404, "Token expired or not found")
    kind = TOKENS_KIND.get(token, "invoices")
    html = render_share_page(path, kind=kind, limit=200)
    return Response(content=html, media_type="text/html; charset=utf-8")
