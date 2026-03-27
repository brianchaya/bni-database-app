import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.title("BNI Transaction Database Generator")

# ==============================
# UPLOAD
# ==============================
uploaded_file = st.file_uploader("Upload Bank Statement", type=["xlsx","xls","csv"])
existing_file = st.file_uploader("Attach Existing Database (Optional)", type=["xlsx"])

# ==============================
# NORMALIZE KODE (SAMA PERSIS BRI)
# ==============================
def normalize_kode(x):
    x = str(x).strip().upper()

    clean = re.sub(r'[^A-Z0-9]', '', x)

    if re.match(r'^N+A*$', clean) or re.match(r'^NA\d*$', clean):
        return "N/A"

    x = re.sub(r'\s+', ' ', x)

    return x

# ==============================
# 🔥 BNI EXTRACT (GANTI DI SINI SAJA)
# ==============================
def extract_code(text):

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

    if "jakom" in lower:
        return "IGNORE"

    return "N/A"

# ==============================
# LOAD STATEMENT (SAMA)
# ==============================
def load_statement(file):

    if file.name.endswith(".csv"):
        return pd.read_csv(file)

    xls = pd.ExcelFile(file)

    for sheet in xls.sheet_names[:10]:
        preview = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=20)

        for i in range(len(preview)):
            row = preview.iloc[i].astype(str).str.lower()

            if any("uraian" in x or "description" in x for x in row):
                return pd.read_excel(xls, sheet_name=sheet, header=i)

    return pd.read_excel(xls, sheet_name=0)

# ==============================
# LOAD EXISTING (SAMA)
# ==============================
def load_existing(file):

    xls = pd.ExcelFile(file)

    for sheet in xls.sheet_names[:10]:
        df = pd.read_excel(xls, sheet_name=sheet)

        cols = [str(c).upper() for c in df.columns]

        if "ID" in cols and "KODE_UNIK" in cols:
            return df

    return pd.read_excel(xls, sheet_name=0)

# ==============================
# PREPARE NEW (SAMA + IGNORE FIX)
# ==============================
def prepare_new(df):

    if df is None or df.empty:
        st.error("File could not be read properly.")
        st.stop()

    df.columns = df.columns.astype(str).str.strip()

    id_cols = [c for c in df.columns if c.strip().upper() == "ID"]
    if len(id_cols) == 0:
        st.error("Column 'ID' not found.")
        st.stop()

    id_col = id_cols[0]

    desc_candidates = [
        c for c in df.columns
        if "uraian" in c.lower() or "description" in c.lower()
    ]

    if len(desc_candidates) == 0:
        st.error("Description column not found.")
        st.stop()

    desc_col = desc_candidates[0]

    df["KODE_UNIK"] = df[desc_col].apply(extract_code)

    # 🔥 FILTER IGNORE DI SINI
    df = df[df["KODE_UNIK"] != "IGNORE"]

    df["KODE_UNIK"] = df["KODE_UNIK"].apply(normalize_kode)

    db = df[[id_col, "KODE_UNIK", desc_col]].copy()
    db.columns = ["ID", "KODE_UNIK", "Description"]

    db["ID"] = db["ID"].astype(str).replace(
        ["nan", "None", "NaT", ""], "N/A"
    )

    return db

# ==============================
# 🔥 SISANYA = 100% COPY BRI LU
# ==============================

def filter_new_only(existing, new):

    existing["KODE_UNIK"] = existing["KODE_UNIK"].apply(normalize_kode)
    new["KODE_UNIK"] = new["KODE_UNIK"].apply(normalize_kode)

    existing_codes = set(
        existing[existing["KODE_UNIK"] != "N/A"]["KODE_UNIK"]
    )

    new_valid = new[new["KODE_UNIK"] != "N/A"]
    new_na = new[new["KODE_UNIK"] == "N/A"]

    new_valid = new_valid[
        ~new_valid["KODE_UNIK"].isin(existing_codes)
    ]

    existing_na_desc = set(
        existing[existing["KODE_UNIK"] == "N/A"]["Description"]
    )

    new_na = new_na[
        ~new_na["Description"].isin(existing_na_desc)
    ]

    filtered = pd.concat([new_valid, new_na], ignore_index=True)

    return filtered

def clean_ids(x):

    ids = []

    for val in x.dropna():
        parts = str(val).split(";")

        for p in parts:
            p = p.strip()
            found = re.findall(r'\d+', p)

            if found:
                ids.extend(found)

    return " ; ".join(sorted(set(ids))) if ids else "N/A"

def grouping(db):

    db = db.copy()
    db["KODE_UNIK"] = db["KODE_UNIK"].apply(normalize_kode)

    db_na = db[db["KODE_UNIK"] == "N/A"].copy()
    db_valid = db[db["KODE_UNIK"] != "N/A"].copy()

    db_valid = db_valid.drop_duplicates(subset=["ID", "KODE_UNIK", "Description"])

    grouped = db_valid.groupby("KODE_UNIK").agg({
        "ID": clean_ids,
        "Description": lambda x: " ; ".join(x.astype(str))
    }).reset_index()

    def is_valid_id(x):
        nums = re.findall(r'\d+', str(x))
        return len(nums) > 0

    grouped["TYPE"] = grouped["ID"].apply(
        lambda x: "NA" if not is_valid_id(x)
        else ("DOUBLE" if ";" in x else "NORMAL")
    )

    normal = grouped[grouped["TYPE"] == "NORMAL"]
    double = grouped[grouped["TYPE"] == "DOUBLE"]

    db_na = db_na.drop_duplicates(subset=["Description"])
    db_na["TYPE"] = "NA"

    return normal, double, db_na

# ==============================
# MAIN (SAMA PERSIS)
# ==============================
if uploaded_file:

    df = load_statement(uploaded_file)
    new_db = prepare_new(df)

    if existing_file:

        exist_df_raw = load_existing(existing_file)
        exist_df_raw.columns = [c.upper() for c in exist_df_raw.columns]

        exist_df_raw = exist_df_raw[["ID", "KODE_UNIK", "DESCRIPTION"]]
        exist_df_raw.columns = ["ID", "KODE_UNIK", "Description"]

        exist_df_raw = exist_df_raw.fillna("N/A")

        filtered_new = filter_new_only(exist_df_raw, new_db)

        if filtered_new.empty:
            st.warning("No new valid data found.")
            new_final = pd.DataFrame()
        else:
            n_normal, n_double, n_na = grouping(filtered_new)
            new_final = pd.concat([n_normal, n_double, n_na], ignore_index=True)

        separator = pd.DataFrame({
            "ID": ["--- NEW DATA ---"],
            "KODE_UNIK": [""],
            "Description": [""],
            "TYPE": [""]
        })

        final = pd.concat([
            exist_df_raw,
            separator,
            new_final
        ], ignore_index=True)

        st.success("Mode: UPDATE DATABASE")

    else:

        normal, double, na = grouping(new_db)

        final = pd.concat([normal, double, na], ignore_index=True)

        st.success("Mode: CREATE NEW DATABASE")

    st.dataframe(final)

    output = BytesIO()
    final.to_excel(output, index=False)

    st.download_button(
        "Download Excel",
        output.getvalue(),
        "DATABASE_BNI.xlsx"
    )
