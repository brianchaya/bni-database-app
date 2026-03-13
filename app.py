import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.title("BRI Transaction Database Generator")

uploaded_file = st.file_uploader("Upload File Excel", type=["xlsx"])


# ==============================
# EXTRACT UNIQUE CODE
# ==============================
def ambil_kode_unik(text):

    if pd.isna(text):
        return "N/A"

    text = str(text)

    # MODEL 1
    m = re.search(r'BFVA11167000(\d{5})', text)
    if m:
        return m.group(1)

    # MODEL 3
    m = re.search(r'BRIVA11167000(\d{5})', text)
    if m:
        return m.group(1)

    # MODEL 2
    m = re.search(r'NBMB\s(.*?)\sTO', text)
    if m:
        return m.group(1).strip()

    # MODEL 4
    m = re.search(r'301([A-Z\s]+?):', text)
    if m:
        return m.group(1).strip()

    # MODEL 5 ATM0-ATM9
    for i in range(10):
        m = re.search(fr'ATM{i} ATM{i} (.*?)  TO', text)
        if m:
            return m.group(1).strip()

    # MODEL 6
    m = re.search(r'FROM (.*?) LA', text)
    if m:
        return m.group(1).strip()

    # MODEL 7
    m = re.search(r'FROM (.*?) ATM', text)
    if m:
        return m.group(1).strip()

    return "N/A"


# ==============================
# DETECT HEADER
# ==============================
def detect_header(file):

    preview = pd.read_excel(file, header=None, nrows=20)

    for i in range(20):
        row = preview.iloc[i].astype(str).str.lower()

        if any("uraian" in cell for cell in row):
            return i

    return 0


# ==============================
# DETECT COLUMNS
# ==============================
def detect_columns(df):

    df.columns = df.columns.str.strip()

    uraian_col = None
    id_col = None

    for col in df.columns:

        if "uraian" in col.lower():
            uraian_col = col

        if col.lower() == "id":
            id_col = col

    return id_col, uraian_col


# ==============================
# MAIN PROCESS
# ==============================
if uploaded_file:

    try:

        # detect header
        header_row = detect_header(uploaded_file)

        df = pd.read_excel(uploaded_file, header=header_row)

        # detect column
        id_col, uraian_col = detect_columns(df)

        if uraian_col is None:
            st.error("Kolom Uraian Transaksi tidak ditemukan.")
            st.write("Kolom yang tersedia:", df.columns)
            st.stop()

        if id_col is None:
            st.error("Kolom ID tidak ditemukan.")
            st.write("Kolom yang tersedia:", df.columns)
            st.stop()

        # ekstrak kode unik
        df["KODE_UNIK"] = df[uraian_col].apply(ambil_kode_unik)

        database = df[[id_col, "KODE_UNIK", uraian_col]].copy()

        # rename supaya konsisten
        database = database.rename(columns={
            id_col: "ID",
            uraian_col: "Uraian Transaksi"
        })

        # convert ID
        database["ID"] = pd.to_numeric(database["ID"], errors="coerce")

        # pisahkan valid dan N/A
        valid = database[database["KODE_UNIK"] != "N/A"].copy()
        anomali = database[database["KODE_UNIK"] == "N/A"].copy()

        # hapus duplikat
        valid = valid.drop_duplicates(subset=["ID","KODE_UNIK"])

        # sort ID
        valid = valid.sort_values("ID")

        # gabungkan
        hasil = pd.concat([valid, anomali], ignore_index=True)

        # ==============================
        # DASHBOARD INFO
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
            label="Download DATABASE_HASIL.xlsx",
            data=output.getvalue(),
            file_name="DATABASE_HASIL.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:

        st.error("Terjadi error saat memproses file.")
        st.write(e)