# backend/app/cleaning/utils.py
import re
from datetime import datetime
from dateutil import parser

CURRENCY_MAP = {"$":"USD","€":"EUR","£":"GBP","MAD":"MAD","usd":"USD","eur":"EUR","gbp":"GBP"}

def norm_header(h: str) -> str:
    return re.sub(r"\s+", " ", h.strip().lower())

def parse_date(x):
    if x is None or str(x).strip()=="":
        return None
    try:
        return parser.parse(str(x), dayfirst=False).date().isoformat()
    except Exception:
        return None

def parse_number(x):
    if x is None: return None
    s = str(x).strip()
    if s == "": return None
    s = s.replace(" ", "")
    # remove currency symbols
    s = re.sub(r"[^\d\-,.]", "", s)
    # normalize decimal
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    s = s.replace(",", "")  # thousands
    try:
        return float(s)
    except Exception:
        return None

def currency_code(x):
    if x is None or str(x).strip()=="":
        return None
    k = str(x).strip()
    return CURRENCY_MAP.get(k, CURRENCY_MAP.get(k.upper(), k.upper()))
