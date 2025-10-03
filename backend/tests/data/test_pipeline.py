import pandas as pd
from app.cleaning.pipeline import clean_invoices

def test_clean_pipeline_core():
    df = pd.DataFrame({
        "Invoice No": ["INV-1","INV-1","INV-2","INV-3"],
        "Date": ["2025/09/01","2025/09/01","2025-09-02","2025-09-03"],
        "Due": ["2025/09/30","2025/09/30","2025/09/10","2025/08/30"],
        "Client": ["Acme","Acme","Delta","Gamma"],
        "Item": ["Widget","Widget","Gadget","Bracket"],
        "Qty": [2,2,-1,3],
        "Unit Price": [50,50,100,25],
        "TVA": [0.2,0.2,0.2,0.15],
        "Currency": ["USD","USD","USD","USD"],
    })
    result = clean_invoices(df)
    prof = result["profile"]
    assert prof["rows_in"] == 4
    assert prof["rows_out"] <= 4        # duplicate removed or same
    assert prof["duplicates_removed"] >= 1
    assert prof["errors_fixed"] >= 1    # negative qty or due-before-issue
