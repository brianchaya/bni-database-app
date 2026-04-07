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
# NORMALIZE KODE (SUPER STRONG)
# ==============================
def normalize_kode(x):
    x = str(x).strip().upper()
    clean = re.sub(r'[^A-Z0-9]', '', x)
    if re.match(r'^N+A*$', clean) or re.match(r'^NA\d*$', clean):
        return "N/A"
    x = re.sub(r'\s+', ' ', x)
    return x

# ==============================
# EXTRACT UNIQUE CODE (BNI)
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

    if "pemindahan dari" in lower and "`" in text:
        return "N/A"

    if "jakom" in lower:
        return "IGNORE"

    return "N/A"

# ==============================
# LOAD STATEMENT (BNI)
# ==============================
def load_statement(file):
    if file.name.endswith(".csv"):
        return pd.read_csv(file)

    xls = pd.ExcelFile(file)

    for sheet in xls.sheet_names[:10]:
        preview = pd.read_excel(xls, sheet_name=sheet, header=None, nrows=20)

        for i in range(len(preview)):
            row = preview.iloc[i].astype(str).str.lower()
            if any("uraian" in str(x).lower() or "description" in str(x).lower() for x in row):
                return pd.read_excel(xls, sheet_name=sheet, header=i)

    return pd.read_excel(xls, sheet_name=0)

# ==============================
# LOAD EXISTING
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
# SPLIT EXISTING & OLD NEW
# ==============================
def split_existing_and_new(df):
    df = df.copy()

    marker_idx = df[
        df["ID"].astype(str).str.contains("--- NEW DATA ---", na=False)
    ].index

    if len(marker_idx) == 0:
        return df, pd.DataFrame(columns=df.columns)

    split_idx = marker_idx[0]
    existing = df.iloc[:split_idx].copy()
    new_old = df.iloc[split_idx+1:].copy()

    existing = existing[existing["ID"] != ""]
    new_old = new_old[new_old["ID"] != ""]

    return existing, new_old

# ==============================
# PREPARE NEW DATA (BNI)
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

    # Buang baris IGNORE (otopay, jakom, dll)
    df = df[df["KODE_UNIK"] != "IGNORE"]

    df["KODE_UNIK"] = df["KODE_UNIK"].apply(normalize_kode)

    db = df[[id_col, "KODE_UNIK", desc_col]].copy()
    db.columns = ["ID", "KODE_UNIK", "Description"]

    db["ID"] = db["ID"].astype(str)
    db["ID"] = db["ID"].apply(
        lambda x: "N/A" if str(x).strip() == "" or str(x).lower() in ["nan", "none", "nat"]
        else str(x).strip()
    )

    return db

# ==============================
# FILTER NEW ONLY
# ==============================
def filter_new_only(existing, new):
    existing = existing.copy()
    new = new.copy()

    def explode_existing(df):
        rows = []
        for _, row in df.iterrows():
            ids = [i.strip() for i in str(row["ID"]).split(";") if i.strip()]
            kodes = [k.strip() for k in str(row["KODE_UNIK"]).split(";") if k.strip()]
            desc = row["Description"]
            for i in ids:
                for k in kodes:
                    rows.append({"ID": i, "KODE_UNIK": k, "Description": desc})
        return pd.DataFrame(rows)

    existing_exploded = explode_existing(existing)

    def is_numeric(x):
        return str(x).strip().isdigit()

    existing_exploded.loc[~existing_exploded["ID"].apply(is_numeric), "KODE_UNIK"] = "N/A"
    new.loc[~new["ID"].apply(is_numeric), "KODE_UNIK"] = "N/A"

    existing_exploded["KODE_UNIK"] = existing_exploded["KODE_UNIK"].apply(normalize_kode)
    new["KODE_UNIK"] = new["KODE_UNIK"].apply(normalize_kode)

    existing_exploded["Description"] = existing_exploded["Description"].astype(str).str.strip().str.upper()
    new["Description"] = new["Description"].astype(str).str.strip().str.upper()

    existing_exploded = existing_exploded.drop_duplicates(subset=["ID", "KODE_UNIK", "Description"])

    existing_id_kode_pairs = set(
        existing_exploded.loc[existing_exploded["KODE_UNIK"] != "N/A"]
        .apply(lambda x: f"{x['ID']}||{x['KODE_UNIK']}", axis=1)
    )

    new_valid = new[new["KODE_UNIK"] != "N/A"].copy()
    new_valid["PAIR"] = new_valid.apply(lambda x: f"{x['ID']}||{x['KODE_UNIK']}", axis=1)
    new_valid = new_valid[~new_valid["PAIR"].isin(existing_id_kode_pairs)]
    new_valid = new_valid.drop(columns=["PAIR"])

    existing_na_desc = set(
        existing_exploded.loc[existing_exploded["KODE_UNIK"] == "N/A", "Description"]
    )

    new_na = new[new["KODE_UNIK"] == "N/A"]
    new_na = new_na[~new_na["Description"].isin(existing_na_desc)]

    final = pd.concat([new_valid, new_na], ignore_index=True)
    final = final.drop_duplicates(subset=["ID", "KODE_UNIK", "Description"])

    return final

# ==============================
# CLEAN ID (BNI)
# ==============================
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

# ==============================
# GROUPING
# ==============================
def grouping(db):
    db = db.copy()
    db["KODE_UNIK"] = db["KODE_UNIK"].apply(normalize_kode)

    def is_pure_numeric_single(x):
        return str(x).strip().isdigit()

    # Override: kalau ID bukan numeric → paksa jadi NA
    db.loc[~db["ID"].apply(is_pure_numeric_single), "KODE_UNIK"] = "N/A"

    db_na = db[db["KODE_UNIK"] == "N/A"].copy()
    db_valid = db[db["KODE_UNIK"] != "N/A"].copy()

    db_valid = db_valid.drop_duplicates(subset=["ID", "KODE_UNIK", "Description"])

    grouped = db_valid.groupby("KODE_UNIK").agg({
        "ID": clean_ids,
        "Description": lambda x: " ; ".join(x.astype(str))
    }).reset_index()

    grouped_by_id = db_valid.groupby("ID").agg({
        "KODE_UNIK": lambda x: list(set(x)),
        "Description": lambda x: " ; ".join(x.astype(str))
    }).reset_index()
    grouped_by_id.columns = ["ID", "KODE_UNIK", "Description"]

    grouped = pd.concat([grouped, grouped_by_id], ignore_index=True)

    def flatten_kode(x):
        if isinstance(x, list):
            return " ; ".join(sorted(x))
        return x

    grouped["KODE_UNIK"] = grouped["KODE_UNIK"].apply(flatten_kode)
    grouped = grouped.drop_duplicates(subset=["ID", "KODE_UNIK", "Description"])

    def is_pure_numeric(x):
        parts = str(x).strip().split(";")
        return all(p.strip().isdigit() for p in parts)

    def is_double(row):
        id_part = str(row["ID"])
        kode_part = str(row["KODE_UNIK"])

        if not is_pure_numeric(id_part):
            return "NA"

        id_count = len([i.strip() for i in id_part.split(";") if i.strip()])
        kode_count = len([k.strip() for k in kode_part.split(";") if k.strip()])

        if id_count > 1 or kode_count > 1:
            return "DOUBLE"

        return "NORMAL"

    grouped["TYPE"] = grouped.apply(is_double, axis=1)

    normal = grouped[grouped["TYPE"] == "NORMAL"]
    double = grouped[grouped["TYPE"] == "DOUBLE"]

    double_ids = set()
    for val in double["ID"]:
        for p in str(val).split(";"):
            double_ids.add(p.strip())

    normal = normal[
        ~normal["ID"].apply(lambda x: any(i.strip() in double_ids for i in str(x).split(";")))
    ]

    db_na = db_na.drop_duplicates(subset=["ID", "Description"])
    db_na["TYPE"] = "NA"

    return normal, double, db_na

# ==============================
# SORT BY ID
# ==============================
def sort_by_id(df):
    def get_min_id(x):
        nums = re.findall(r'\d+', str(x))
        return min([int(n) for n in nums]) if nums else 999999999

    df = df.copy()
    df["IS_NA"] = df["KODE_UNIK"].apply(lambda x: 1 if x == "N/A" else 0)
    df["SORT_KEY"] = df["ID"].apply(get_min_id)
    df = df.sort_values(["IS_NA", "SORT_KEY"]).drop(columns=["SORT_KEY", "IS_NA"])
    return df

# ==============================
# MAIN
# ==============================
if uploaded_file:

    df = load_statement(uploaded_file)
    new_db = prepare_new(df)

    if existing_file:

        exist_df_raw = load_existing(existing_file)
        exist_df_raw.columns = [c.upper() for c in exist_df_raw.columns]

        if "DESCRIPTION" not in exist_df_raw.columns:
            exist_df_raw["DESCRIPTION"] = ""

        exist_df_raw = exist_df_raw[["ID", "KODE_UNIK", "DESCRIPTION"]]
        exist_df_raw.columns = ["ID", "KODE_UNIK", "Description"]
        exist_df_raw = exist_df_raw.fillna("N/A")

        exist_df_raw["ID"] = exist_df_raw["ID"].astype(str).replace(["nan","None","NaT",""], "N/A")
        exist_df_raw["KODE_UNIK"] = exist_df_raw["KODE_UNIK"].astype(str).replace(["nan","None","NaT",""], "N/A")
        exist_df_raw["Description"] = exist_df_raw["Description"].astype(str).replace(["nan","None","NaT",""], "")

        # SPLIT
        exist_df, old_new = split_existing_and_new(exist_df_raw)

        # 🔥 PROMOTE old_new → jadi EXISTING (tidak hilang)
        if not old_new.empty:
            old_new = old_new.copy()
            old_new["TYPE"] = "EXISTING"
            exist_df = pd.concat([exist_df, old_new], ignore_index=True)

        # Untuk keperluan filter
        exist_all = exist_df.copy()
        exist_all["KODE_UNIK"] = exist_all["KODE_UNIK"].apply(normalize_kode)
        exist_all["Description"] = exist_all["Description"].astype(str).str.strip()

        exist_df = sort_by_id(exist_df)
        exist_df["TYPE"] = "EXISTING"
        exist_df["KODE_UNIK"] = exist_df["KODE_UNIK"].apply(normalize_kode)

        # FILTER
        filtered_new = filter_new_only(exist_all, new_db)

        # GROUPING new
        n_normal, n_double, n_na = grouping(filtered_new)
        new_final = pd.concat([n_normal, n_double, n_na], ignore_index=True)

        n_normal = new_final[new_final["TYPE"] == "NORMAL"]
        n_double = new_final[new_final["TYPE"] == "DOUBLE"]
        n_na = new_final[new_final["TYPE"] == "NA"]

        col1, col2, col3 = st.columns(3)
        col1.metric("New Normal", len(n_normal))
        col2.metric("New Merged", len(n_double))
        col3.metric("New NA", len(n_na))

        spacer = pd.DataFrame({"ID":["",""],"KODE_UNIK":["",""],"Description":["",""],"TYPE":["",""]})
        separator = pd.DataFrame({"ID":["--- NEW DATA ---"],"KODE_UNIK":[""],"Description":[""],"TYPE":[""]})

        final = pd.concat([exist_df, spacer, separator, new_final], ignore_index=True)

        st.success("Mode: UPDATE DATABASE")

    else:

        normal, double, na = grouping(new_db)

        col1, col2, col3 = st.columns(3)
        col1.metric("Normal Rows", len(normal))
        col2.metric("Merged Rows", len(double))
        col3.metric("Need Review (N/A)", len(na))

        normal = sort_by_id(normal)
        double = sort_by_id(double)
        na = sort_by_id(na)

        final = pd.concat([normal, double, na], ignore_index=True)

        st.success("Mode: CREATE NEW DATABASE")

    st.dataframe(final)

    output = BytesIO()

    try:
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            final.to_excel(writer, index=False)
    except:
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            final.to_excel(writer, index=False)

    st.download_button(
        "Download Excel",
        output.getvalue(),
        "DATABASE_BNI.xlsx"
    )
