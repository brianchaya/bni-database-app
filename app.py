import streamlit as st
import pandas as pd
import re
from io import BytesIO
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

st.title("BNI Transaction Database Generator")

uploaded_file = st.file_uploader(
    "Upload File (.xlsx / .xls / .csv)",
    type=["xlsx","xls","csv"]
)

# =====================================
# EXTRACT UNIQUE CODE BNI
# =====================================
def ambil_kode_unik(text):

    if pd.isna(text):
        return "N/A"

    text = str(text)
    lower = text.lower()

    if "otopay" in lower:
        return "IGNORE"

    m = re.search(r'PEMINDAHAN DARI\s+(\d+)', text)
    if m:
        return m.group(1)

    m = re.search(r'\|\s*(\d{16})', text)
    if m:
        return m.group(1)

    m = re.search(r'(\d{16})\s+[A-Za-z]', text)
    if m:
        return m.group(1)

    m = re.search(r'PENGIRIM\s+(.*)', text)
    if m:
        return m.group(1).strip()

    m = re.search(r'\|\s*\d+\s+[A-Z\s]+\s([A-Z\s]+)$', text)
    if m:
        return m.group(1).strip()

    if "pemindahan dari" in lower and "`" in text:
        return "N/A"

    if "jakom" in lower:
        return "IGNORE"

    return "N/A"

# =====================================
# DETECT HEADER
# =====================================
def detect_header(file):

    preview = pd.read_excel(file, header=None, nrows=20)

    for i in range(20):
        row = preview.iloc[i].astype(str).str.lower()
        if any("description" in cell for cell in row):
            return i

    return 0

# =====================================
# DETECT COLUMN
# =====================================
def detect_columns(df):

    df.columns = df.columns.str.strip()

    desc_col = None
    id_col = None

    for col in df.columns:

        if "description" in col.lower():
            desc_col = col

        if col.lower() == "id":
            id_col = col

    return id_col, desc_col

# =====================================
# MAIN PROCESS
# =====================================
if uploaded_file:

    try:

        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
        else:
            header_row = detect_header(uploaded_file)
            df = pd.read_excel(uploaded_file, header=header_row)

        id_col, desc_col = detect_columns(df)

        if desc_col is None:
            st.error("Kolom Description tidak ditemukan")
            st.write(df.columns)
            st.stop()

        if id_col is None:
            st.error("Kolom ID tidak ditemukan")
            st.write(df.columns)
            st.stop()

        # ==============================
        # PROCESS DATA
        # ==============================
        df["KODE_UNIK"] = df[desc_col].apply(ambil_kode_unik)

        database = df[[id_col, "KODE_UNIK", desc_col]].copy()

        database = database.rename(columns={
            id_col: "ID",
            desc_col: "Description"
        })

        database["ID"] = pd.to_numeric(database["ID"], errors="coerce")

        # remove IGNORE
        database = database[database["KODE_UNIK"] != "IGNORE"]

        valid = database[database["KODE_UNIK"] != "N/A"].copy()
        anomali = database[database["KODE_UNIK"] == "N/A"].copy()

        # ==============================
        # GROUPING LOGIC (NEW)
        # ==============================
        # detect duplicates (by ID or KODE_UNIK)
        dup_mask = valid.duplicated(subset=["ID"], keep=False) | valid.duplicated(subset=["KODE_UNIK"], keep=False)

        normal = valid[~dup_mask].copy()
        duplicate = valid[dup_mask].copy()

        # group duplicates
        if not duplicate.empty:
            grouped = duplicate.groupby(["KODE_UNIK"], dropna=False).agg({
                "ID": lambda x: " ; ".join(sorted(set(map(str, x)))) ,
                "Description": lambda x: " ; ".join(x)
            }).reset_index()
        else:
            grouped = pd.DataFrame(columns=["KODE_UNIK","ID","Description"])

        # reorder columns
        grouped = grouped[["ID","KODE_UNIK","Description"]]

        # sort
        normal = normal.sort_values("ID")

        # IMPORTANT: sort grouped by smallest ID inside the string
        def extract_min_id(val):
            try:
                nums = [int(x.strip()) for x in str(val).split(";")]
                return min(nums)
            except:
                return float('inf')

        grouped = grouped.copy()
        grouped["_sort_key"] = grouped["ID"].apply(extract_min_id)
        grouped = grouped.sort_values("_sort_key").drop(columns=["_sort_key"])

        # final result: normal -> grouped -> N/A
        hasil = pd.concat([normal, grouped, anomali], ignore_index=True)

        # ==============================
        # DASHBOARD
        # ==============================
        col1, col2, col3 = st.columns(3)

        col1.metric("Total transaksi", len(database))
        col2.metric("Database bersih", len(valid))
        col3.metric("Perlu cek manual (N/A)", len(anomali))

        st.success("Database berhasil dibuat")

        st.dataframe(hasil)

        # ==============================
        # EXPORT WITH COLOR
        # ==============================
        output = BytesIO()
        hasil.to_excel(output, index=False)

        output.seek(0)
        wb = load_workbook(output)
        ws = wb.active

        yellow = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
        red = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")

        # apply coloring
        for i, row in hasil.iterrows():
            excel_row = i + 2

            if row["KODE_UNIK"] == "N/A":
                for col in range(1, 4):
                    ws.cell(row=excel_row, column=col).fill = red

            elif ";" in str(row["ID"]):
                for col in range(1, 4):
                    ws.cell(row=excel_row, column=col).fill = yellow

        final_output = BytesIO()
        wb.save(final_output)

        st.download_button(
            "Download DATABASE_HASIL_BNI.xlsx",
            final_output.getvalue(),
            "DATABASE_HASIL_BNI.xlsx"
        )

    except Exception as e:

        st.error("Terjadi error saat memproses file")
        st.write(e)
