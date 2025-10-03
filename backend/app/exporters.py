# backend/app/exporters.py
from io import BytesIO
import pandas as pd

def export_xlsx_styled(df: pd.DataFrame, sheet_name: str = "Cleaned"):
    """
    Return XLSX bytes with nice formatting:
      - bold header, freeze top row
      - auto column widths
      - numeric formatting for common columns
    """
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        wb  = writer.book
        ws  = writer.sheets[sheet_name]

        # Bold header + freeze
        header_fmt = wb.add_format({"bold": True, "text_wrap": True, "bg_color": "#F5F5F5", "border": 1})
        for col_num, value in enumerate(df.columns.values):
            ws.write(0, col_num, value, header_fmt)
        ws.freeze_panes(1, 0)

        # Auto-width
        for i, col in enumerate(df.columns):
            # measure width from data sample + header
            col_series = df[col].astype(str)
            max_len = max([len(str(col))] + [len(s) for s in col_series.head(200)])
            ws.set_column(i, i, min(max_len + 2, 60))

        # Friendly number formats
        money_fmt = wb.add_format({"num_format": "#,##0.00"})
        qty_fmt   = wb.add_format({"num_format": "#,##0"})
        pct_fmt   = wb.add_format({"num_format": "0.00%"})

        def col_has(name: str):
            name = name.lower()
            return [i for i, c in enumerate(df.columns) if c.lower() == name]

        # common finance columns
        for key in ["unit_price", "line_total", "total_before_tax", "tax_amount", "total_amount"]:
            for idx in col_has(key):
                ws.set_column(idx, idx, None, money_fmt)

        for key in ["quantity", "qty_on_hand", "reorder_point"]:
            for idx in col_has(key):
                ws.set_column(idx, idx, None, qty_fmt)

        for idx in col_has("tax_rate"):
            ws.set_column(idx, idx, None, pct_fmt)

    bio.seek(0)
    return bio.getvalue()
