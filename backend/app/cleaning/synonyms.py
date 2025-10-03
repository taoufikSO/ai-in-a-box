# backend/app/cleaning/synonyms.py

# Map many messy headers → ONE canonical name (all keys are lowercase)
HEADER_SYNONYMS = {
    # ---- invoice id ----
    "invoice no": "invoice_id",
    "invoice number": "invoice_id",
    "invoice": "invoice_id",
    "invoice#": "invoice_id",
    "invoice_num": "invoice_id",
    "invid": "invoice_id",
    "inv_id": "invoice_id",
    "id facture": "invoice_id",

    # ---- dates ----
    "date": "issue_date",
    "invoice date": "issue_date",
    "due": "due_date",
    "due date": "due_date",

    # ---- customer ----
    "client": "customer_name",
    "client name": "customer_name",
    "customer": "customer_name",
    "customer name": "customer_name",
    "customername": "customer_name",
    "company": "customer_name",
    "customer id": "customer_id",

    # ---- line description ----
    "item": "item_description",
    "description": "item_description",

    # ---- qty / price / totals ----
    "qty": "quantity",
    "quantity": "quantity",
    "price": "unit_price",
    "unit price": "unit_price",
    "line total": "line_total",

    "subtotal": "total_before_tax",
    "sub total": "total_before_tax",
    "ht": "total_before_tax",

    "grand total": "total_amount",
    "ttc": "total_amount",
    "amount": "total_amount",
    "total": "total_amount",

    "tax": "tax_amount",
    "tva": "tax_amount",
    "tax rate": "tax_rate",

    # ---- misc ----
    "currency": "currency",
    "status": "status",
}

# Column order when we return the cleaned file
CANONICAL_ORDER = [
    "invoice_id", "issue_date", "due_date",
    "customer_name", "customer_id",
    "item_description", "quantity", "unit_price", "line_total",
    "currency", "tax_rate", "tax_amount",
    "total_before_tax", "total_amount",
    "status",
]
