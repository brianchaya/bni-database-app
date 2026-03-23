import streamlit as st
import pandas as pd
import re
from io import BytesIO
from openpyxl import load_workbook
from openpyxl.styles import PatternFill

st.title("BNI Transaction Database Generator")

mode = st.radio(
    "Mode",
    ["Buat Database Baru", "Update Database Existing"]
)

uploaded_file = st.file_uploader(
    "Upload Rekening Koran",
    type=["xlsx","xls","csv"]
)

existing_file = None
if mode == "Update Database Existing":
    existing_file = st.file_uploader(
        "Upload Database Existing",
        type=["xlsx"]
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

    m = re.search(r'PEMINDAHAN DARI\\s+(\\d+)', text)
    if m:
        return m.group(1)

    m = re.search(r'\\|\\s*(\\d{16})', text)
    if m:
        return m.group(1)

    m = re.search(r'(\\d{16})\\s+[A-Za-z]', text)
    if m:
        return m.group(1)

    m = re.search(r'PENGIRIM\\s+(.*)', text)
    if m:
        return m.group(1).strip()

    m = re.search(r'\\|\\s*\\d+\\s+[A-Z\\s]+\\s([A-Z\\s]+)$', text)
    if m:
        return m.group(1).strip()

    if "pemindahan dari" in lower and "`" in text:
        return "N/A"

    if "jakom" in lower:
        return "IGNORE"

    return "N/A"

# =====================================
# HELPER PROCESS FUNCTION
# =====================================
def process_database(df, id_col, desc_col):

    df["KODE_UNIK"] = df[desc_col].apply(ambil_kode_unik)

    database = df[[id_col, "KODE_UNIK", desc_col]].copy()
    database = database.rename(columns={id_col: "ID", desc_col: "Description"})
    database["ID"] = pd.to_numeric(database["ID"], errors="coerce")

    database = database[database["KODE_UNIK"] != "IGNORE"]

    valid = database[database["KODE_UNIK"] != "N/A"].copy()
    anomali = database[database["KODE_UNIK"] == "N/A"].copy()

    dup_mask = valid.duplicated(subset=["ID"], keep=False) | valid.duplicated(subset=["KODE_UNIK"], keep=False)

    normal = valid[~dup_mask].copy()
    duplicate = valid[dup_mask].copy()

    if not duplicate.empty:
        grouped = duplicate.groupby(["KODE_UNIK"], dropna=False).agg({
            "ID": lambda x: " ; ".join(sorted(set(map(str, x)))) ,
            "Description": lambda x: " ; ".join(x)
        }).reset_index()
    else:
        grouped = pd.DataFrame(columns=["KODE_UNIK","ID","Description"])

    grouped = grouped[["ID","KODE_UNIK","Description"]]

    normal = normal.sort_values("ID")

    def extract_min_id(val):
        try:
            nums = [int(x.strip()) for x in str(val).split(";")]
            return min(nums)
        except:
            return float('inf')

    grouped["_sort_key"] = grouped["ID"].apply(extract_min_id)
    grouped = grouped.sort_values("_sort_key").drop(columns=["_sort_key"])

    hasil = pd.concat([normal, grouped, anomali], ignore_index=True)

    return hasil, database, valid, anomali, grouped

# =====================================
# MAIN
# =====================================
if uploaded_file:

    try:

        # LOAD NEW DATA
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file, sep=None, engine="python")
        else:
            df = pd.read_excel(uploaded_file)

        df.columns = df.columns.str.strip()

        id_col = [c for c in df.columns if c.lower()=="id"][0]
        desc_col = [c for c in df.columns if "description" in c.lower()][0]

        hasil_baru, database_baru, valid_baru, anomali_baru, grouped_baru = process_database(df, id_col, desc_col)

        # ==============================
        # UPDATE MODE
        # ==============================
        if mode == "Update Database Existing" and existing_file:

            existing_df = pd.read_excel(existing_file)

            # remove duplicates vs existing
            merge_key = existing_df["ID"].astype(str) + "|" + existing_df["KODE_UNIK"].astype(str)
            new_key = database_baru["ID"].astype(str) + "|" + database_baru["KODE_UNIK"].astype(str)

            mask_new = ~new_key.isin(set(merge_key))
            database_filtered = database_baru[mask_new]

            # reprocess filtered only
            hasil_new, _, valid_new, anomali_new, grouped_new = process_database(database_filtered, "ID", "Description")

            st.subheader("Summary Update")
            col1, col2, col3 = st.columns(3)
            col1.metric("Data baru", len(database_filtered))
            col2.metric("Duplicate (gabungan)", len(grouped_new))
            col3.metric("N/A baru", len(anomali_new))

            # gabungkan visual (dipisah 3 baris kosong)
            spacer = pd.DataFrame([[None,None,None]]*3, columns=["ID","KODE_UNIK","Description"])
            final_df = pd.concat([existing_df, spacer, hasil_new], ignore_index=True)

        else:
            final_df = hasil_baru

            col1, col2, col3 = st.columns(3)
            col1.metric("Total transaksi", len(database_baru))
            col2.metric("Database bersih", len(valid_baru))
            col3.metric("Perlu cek manual (N/A)", len(anomali_baru))

        st.success("Database berhasil dibuat")
        st.dataframe(final_df)

        # ==============================
        # EXPORT
        # ==============================
        output = BytesIO()
        final_df.to_excel(output, index=False)

        output.seek(0)
        wb = load_workbook(output)
        ws = wb.active

        yellow = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
        red = PatternFill(start_color="FF0000", end_color="FF0000", fill_type="solid")

        for i, row in final_df.iterrows():
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
