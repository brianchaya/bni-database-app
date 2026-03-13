import streamlit as st
import pandas as pd
import re
from io import BytesIO

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

    # =========================
    # MODEL 2 → OTOPAY ignore
    # =========================
    if "otopay" in lower:
        return "IGNORE"

    # =========================
    # MODEL 1 & 8
    # PEMINDAHAN DARI
    # =========================
    m = re.search(r'PEMINDAHAN DARI\s+(\d+)', text)
    if m:
        return m.group(1)

    # =========================
    # MODEL 9
    # VA di awal kalimat
    # =========================
    m = re.search(r'\|\s*(\d{16})', text)
    if m:
        return m.group(1)

    # =========================
    # MODEL 7
    # VA setelah JAKOM
    # =========================
    m = re.search(r'(\d{16})\s+[A-Za-z]', text)
    if m:
        return m.group(1)

    # =========================
    # MODEL 3
    # =========================
    m = re.search(r'PENGIRIM\s+(.*)', text)
    if m:
        return m.group(1).strip()

    # =========================
    # MODEL 4
    # =========================
    m = re.search(r'\|\s*\d+\s+[A-Z\s]+\s([A-Z\s]+)$', text)
    if m:
        return m.group(1).strip()

    # =========================
    # MODEL 6
    # nomor hilang
    # =========================
    if "pemindahan dari" in lower and "`" in text:
        return "N/A"

    # =========================
    # MODEL 5
    # JAKOM tanpa info tambahan
    # =========================
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

        # ==============================
        # LOAD FILE
        # ==============================
        if uploaded_file.name.endswith(".csv"):

            df = pd.read_csv(uploaded_file, sep=None, engine="python")

        else:

            header_row = detect_header(uploaded_file)

            df = pd.read_excel(uploaded_file, header=header_row)

        # ==============================
        # DETECT COLUMN
        # ==============================
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

        # remove duplicate
        valid = valid.drop_duplicates(subset=["ID","KODE_UNIK"])

        # sort
        valid = valid.sort_values("ID")

        hasil = pd.concat([valid, anomali], ignore_index=True)

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
        # DOWNLOAD
        # ==============================
        output = BytesIO()

        hasil.to_excel(output, index=False)

        st.download_button(
            "Download DATABASE_HASIL_BNI.xlsx",
            output.getvalue(),
            "DATABASE_HASIL_BNI.xlsx"
        )

    except Exception as e:

        st.error("Terjadi error saat memproses file")
        st.write(e)
