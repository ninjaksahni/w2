# app.py
import streamlit as st
import pandas as pd
from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

st.set_page_config(page_title="Amazon Warehouse Stock — Markdown Cards", layout="wide")

st.title("📦 Amazon Warehouse Stock")

st.markdown(
    """
**Step 1 — Download:** Get the Ledger Report CSV from Amazon Seller Central for the **last 2 days excluding today**:  
https://sellercentral.amazon.in/reportcentral/LEDGER_REPORT/1

**Step 2 — Upload:** Upload the downloaded CSV below.
"""
)

uploaded_file = st.file_uploader("📤 Upload Ledger CSV", type=["csv"])


# ---------- helpers ----------
def _read_csv_safe(uploaded_file):
    uploaded_file.seek(0)
    for enc in (None, "latin1", "utf-8"):
        try:
            if enc:
                return pd.read_csv(uploaded_file, encoding=enc)
            return pd.read_csv(uploaded_file)
        except Exception:
            uploaded_file.seek(0)
    uploaded_file.seek(0)
    return pd.read_csv(uploaded_file, engine="python", encoding="utf-8", error_bad_lines=False)


def _find_column_by_name(df, desired_name):
    mapping = {c.strip().lower(): c for c in df.columns}
    return mapping.get(desired_name.strip().lower())


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def generate_pdf_report(df, timestamp):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="WarehouseTitle", fontSize=14, leading=16, spaceAfter=8, textColor=colors.darkblue, bold=True))
    styles.add(ParagraphStyle(name="NormalSmall", fontSize=10, leading=12))

    elements = []
    elements.append(Paragraph(f"Amazon Warehouse Stock Report", styles["Title"]))
    elements.append(Paragraph(f"Generated on: {timestamp}", styles["Normal"]))
    elements.append(Spacer(1, 12))

    for location, loc_df in df.groupby("Location"):
        elements.append(Paragraph(f"🏬 {location}", styles["WarehouseTitle"]))

        data = [["MSKU", "Ending Warehouse Balance"]]
        for _, row in loc_df.iterrows():
            data.append([row["MSKU"], int(row["Ending Warehouse Balance"])])

        table = Table(data, colWidths=[300, 100])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                    ("ALIGN", (1, 1), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 12))

    doc.build(elements)
    buffer.seek(0)
    return buffer


# ---------- main ----------
if uploaded_file:
    try:
        df = _read_csv_safe(uploaded_file)
    except Exception as e:
        st.error(f"Could not read uploaded file: {e}")
        st.stop()

    df.columns = [c.strip() for c in df.columns]

    required = {
        "msku": "MSKU",
        "disposition": "Disposition",
        "balance": "Ending Warehouse Balance",
        "location": "Location",
    }

    found = {}
    for key, pretty in required.items():
        col = _find_column_by_name(df, pretty)
        if col is None:
            col = _find_column_by_name(df, key)
        found[key] = col

    missing = [v for k, v in found.items() if v is None]
    if missing:
        st.error(
            "CSV is missing required columns. Required: MSKU, Disposition, Ending Warehouse Balance, Location\n"
            f"Found: {list(df.columns)}"
        )
        st.stop()

    msku_col = found["msku"]
    disp_col = found["disposition"]
    bal_col = found["balance"]
    loc_col = found["location"]

    df[bal_col] = (
        df[bal_col].astype(str)
        .str.replace(",", "", regex=False)
        .str.replace(r"[^\d\.\-]", "", regex=True)
    )
    df[bal_col] = pd.to_numeric(df[bal_col], errors="coerce").fillna(0).astype(int)

    df[disp_col] = df[disp_col].astype(str).str.strip().str.upper()
    df_sellable = df[df[disp_col] == "SELLABLE"].copy()

    if df_sellable.empty:
        st.warning("No SELLABLE items found.")
        st.stop()

    df_sellable[loc_col] = df_sellable[loc_col].fillna("Unknown")

    agg = (
        df_sellable
        .groupby([loc_col, msku_col], as_index=False)[bal_col]
        .sum()
        .rename(columns={loc_col: "Location", msku_col: "MSKU", bal_col: "Ending Warehouse Balance"})
    )

    location_totals = agg.groupby("Location")["Ending Warehouse Balance"].sum().sort_values(ascending=False)
    locations = list(location_totals.index)
    total_warehouses = len(locations)
    unique_skus = agg["MSKU"].nunique()
    overall_total = int(agg["Ending Warehouse Balance"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Warehouses", total_warehouses)
    c2.metric("Unique MSKUs", unique_skus)
    c3.metric("Total Sellable Qty", overall_total)

    st.markdown("---")
    st.subheader("📍 Warehouses — All SKUs Listed")

    search = st.text_input("Filter MSKU contains", value="").strip().lower()
    if search:
        agg = agg[agg["MSKU"].astype(str).str.lower().str.contains(search)]
        location_totals = agg.groupby("Location")["Ending Warehouse Balance"].sum().sort_values(ascending=False)
        locations = list(location_totals.index)

    for chunk in chunks(locations, 3):
        cols = st.columns(3)
        for i, loc in enumerate(chunk):
            with cols[i]:
                loc_df = agg[agg["Location"] == loc].sort_values(
                    by="Ending Warehouse Balance", ascending=False
                ).reset_index(drop=True)

                loc_total = int(loc_df["Ending Warehouse Balance"].sum())

                # Header with download button
                col_header1, col_header2 = st.columns([0.7, 0.3])
                with col_header1:
                    st.markdown(f"### 🏬 **{loc}**")
                    st.caption(f"Total: **{loc_total}**")
                with col_header2:
                    csv_bytes = loc_df.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        label="⬇️ CSV",
                        data=csv_bytes,
                        file_name=f"{loc.replace(' ', '_')}_sellable.csv",
                        mime="text/csv",
                        key=f"dl_{loc}"
                    )

                # SKU list
                lines = [f"- 📦 **{row['MSKU']}** — {int(row['Ending Warehouse Balance'])}" for _, row in loc_df.iterrows()]
                st.markdown("\n".join(lines) if lines else "_No SKUs for this location after filters._")

    st.markdown("---")
    csv_bytes = agg.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="⬇️ Download aggregated CSV",
        data=csv_bytes,
        file_name="aggregated_sellable_by_location_msku.csv",
        mime="text/csv",
    )

    # PDF download
    st.markdown("### 📄 Download PDF Report")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pdf_buffer = generate_pdf_report(agg, timestamp)
    st.download_button(
        label="⬇️ Download PDF",
        data=pdf_buffer,
        file_name=f"warehouse_stock_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
        mime="application/pdf",
    )
