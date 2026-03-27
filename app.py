import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.title("BNI Transaction Database Generator (Upgraded)")

uploaded_file = st.file_uploader(
    "Upload File (.xlsx / .xls / .csv)",
    type=["xlsx","xls","csv"]
)

existing_file = st.file_uploader(
    "Attach Existing Database (Optional)",
    type=["xlsx"]
)

# =====================================
# NORMALIZE (AMBIL DARI BRI)
# =====================================
def normalize_kode(x):
    x = str(x).strip().upper()
    clean = re.sub(r'[^A-Z0-9]', '', x)

    if re.match(r'^N+A*$', clean) or re.match(r'^NA\d*$', clean):
        return "N/A"

    x = re.sub(r'\s+', ' ', x)
    return x

# =====================================
# EXTRACT BNI (TETAP)
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

    if "jakom" in lower:
        return "IGNORE"

    return "N/A"

# =====================================
# LOAD FILE
# =====================================
def load_file(file):

    if file.name.endswith(".csv"):
        return pd.read_csv(file, sep=None, engine="python")

    preview = pd.read_excel(file, header=None, nrows=20)

    for i in range(20):
        row = preview.iloc[i].astype(str).str.lower()
        if any("description" in x for x in row):
            return pd.read_excel(file, header=i)

    return pd.read_excel(file)

# =====================================
# DETECT COLUMN
# =====================================
def detect_columns(df):

    df.columns = df.columns.str.strip()

    id_col = None
    desc_col = None

    for col in df.columns:
        if col.lower() == "id":
            id_col = col
        if "description" in col.lower():
            desc_col = col

    return id_col, desc_col

# =====================================
# PREPARE DATA
# =====================================
def prepare_data(df, id_col, desc_col):

    df["KODE_UNIK"] = df[desc_col].apply(ambil_kode_unik)
    df["KODE_UNIK"] = df["KODE_UNIK"].apply(normalize_kode)

    db = df[[id_col, "KODE_UNIK", desc_col]].copy()

    db.columns = ["ID", "KODE_UNIK", "Description"]

    db = db[db["KODE_UNIK"] != "IGNORE"]

    db["ID"] = db["ID"].astype(str).replace(
        ["nan","None","NaT",""], "N/A"
    )

    return db

# =====================================
# FILTER NEW ONLY (ANTI DUPLIKAT)
# =====================================
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

    return pd.concat([new_valid, new_na], ignore_index=True)

# =====================================
# GROUPING BNI STYLE (RELATIONAL)
# =====================================
def grouping_bni(db):

    db = db.copy()
    db["KODE_UNIK"] = db["KODE_UNIK"].apply(normalize_kode)

    valid = db[db["KODE_UNIK"] != "N/A"].copy()
    na = db[db["KODE_UNIK"] == "N/A"].copy()

    grouped = []
    used = set()

    for i, row in valid.iterrows():
        if i in used:
            continue

        group = valid[
            (valid["KODE_UNIK"] == row["KODE_UNIK"]) |
            (valid["ID"] == row["ID"])
        ]

        used.update(group.index)

        ids = sorted(set(group["ID"]))
        kode = sorted(set(group["KODE_UNIK"]))
        desc = list(group["Description"])

        grouped.append({
            "ID": " ; ".join(ids),
            "KODE_UNIK": " ; ".join(kode),
            "Description": " ; ".join(desc),
            "TYPE": "DOUBLE" if len(group) > 1 else "NORMAL"
        })

    grouped_df = pd.DataFrame(grouped)

    normal = grouped_df[grouped_df["TYPE"] == "NORMAL"]
    double = grouped_df[grouped_df["TYPE"] == "DOUBLE"]

    na = na.drop_duplicates(subset=["Description"])
    na["TYPE"] = "NA"

    return normal, double, na

# =====================================
# MAIN
# =====================================
if uploaded_file:

    df = load_file(uploaded_file)
    id_col, desc_col = detect_columns(df)

    if not id_col or not desc_col:
        st.error("Kolom ID / Description tidak ditemukan")
        st.stop()

    new_db = prepare_data(df, id_col, desc_col)

    if existing_file:

        exist_df = pd.read_excel(existing_file)
        exist_df.columns = [c.upper() for c in exist_df.columns]

        exist_df = exist_df[["ID","KODE_UNIK","DESCRIPTION"]]
        exist_df.columns = ["ID","KODE_UNIK","Description"]

        exist_df = exist_df.fillna("N/A")

        filtered_new = filter_new_only(exist_df, new_db)

        if filtered_new.empty:
            st.warning("No new data")
            new_final = pd.DataFrame()
        else:
            n_normal, n_double, n_na = grouping_bni(filtered_new)
            new_final = pd.concat([n_normal,n_double,n_na], ignore_index=True)

        separator = pd.DataFrame({
            "ID": ["--- NEW DATA ---"],
            "KODE_UNIK": [""],
            "Description": [""],
            "TYPE": [""]
        })

        final = pd.concat([exist_df, separator, new_final], ignore_index=True)

        st.success("Mode: UPDATE DATABASE")

    else:

        n_normal, n_double, n_na = grouping_bni(new_db)

        final = pd.concat([n_normal,n_double,n_na], ignore_index=True)

        st.success("Mode: CREATE NEW DATABASE")

    st.dataframe(final)

    output = BytesIO()
    final.to_excel(output, index=False)

    st.download_button(
        "Download Excel",
        output.getvalue(),
        "DATABASE_BNI.xlsx"
    )
