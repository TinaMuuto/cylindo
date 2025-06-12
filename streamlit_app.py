# === Streamlit Cylindo CSV Generator med gruppering ===
# Opsætning:
# 1) .env i roden: CYLINDO_CID=4928
# 2) .env i .gitignore
# 3) requirements.txt: streamlit, requests, python-dotenv, pandas
# 4) pip install -r requirements.txt
# 5) python3 -m streamlit run streamlit_app.py

import os
import time
import requests
import itertools
from urllib.parse import quote
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# Load miljøvariabler
load_dotenv()
CID = os.getenv("CYLINDO_CID", "4928")

# Streamlit sideopsætning
st.set_page_config(page_title="Cylindo CSV Generator", layout="wide")
st.title("Cylindo CSV Generator")

# Sidebar inputs
st.sidebar.header("Configuration")

@st.cache_data
def fetch_product_objects(cid):
    """Henter alle produkt-objekter (med metadata) for den angivne Kunde-ID."""
    url = f"https://content.cylindo.com/api/v2/{cid}/listcustomerproducts"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    return [item for item in data.get("products", []) if isinstance(item, dict)]

# 1) Hent produkt-objekter
product_objs = fetch_product_objects(CID)

# 2) Gruppér efter productType
product_types = sorted({p.get("productType", "Unknown") for p in product_objs})
selected_type = st.sidebar.selectbox("Grupper efter productType", ["Alle"] + product_types)
if selected_type == "Alle":
    grouped = product_objs
else:
    grouped = [p for p in product_objs if p.get("productType") == selected_type]

# 3) Søg i koder (delmatch)
search_query = st.sidebar.text_input("Søg i product code")
if search_query:
    filtered = [p for p in grouped if search_query.lower() in p.get("code", "").lower()]
    if not filtered:
        st.sidebar.warning("Ingen produkter matcher din søgning.")
else:
    filtered = grouped

# 4) Vælg alle checkbox
select_all = st.sidebar.checkbox("Vælg alle produkter", value=False)
codes_list = [p["code"] for p in filtered]
if select_all:
    selected_products = codes_list
else:
    selected_products = st.sidebar.multiselect(
        "Vælg én eller flere produkter",
        codes_list,
        default=codes_list[:1]
    )

# 5) Frame-udvælgelse
frame_options = list(range(1, 37))
selected_frames = st.sidebar.multiselect("Vælg frames", frame_options, default=[1])

# 6) Filnavn
csv_name = st.sidebar.text_input("Filnavn", value="cylindo_export.csv")

# 7) Generér-knap
generate = st.sidebar.button("Generér CSV")

# Main: lav kombinationer og CSV
if generate:
    with st.spinner("Henter data og genererer CSV…"):
        all_rows = []
        base_qs = "encoding=png&size=1500&removeEnvironmentShadow=true"
        for product in selected_products:
            cfg_url = f"https://content.cylindo.com/api/v2/{CID}/products/{product}/configuration"
            resp = requests.get(cfg_url, timeout=20)
            if resp.status_code != 200:
                st.error(f"HTTP {resp.status_code} for {product}")
                continue
            cfg = resp.json()
            feats = cfg.get("features", [])
            feat_map = {
                f["code"]: [opt["code"] for opt in f.get("options", []) if isinstance(opt, dict) and "code" in opt]
                for f in feats if f.get("options")
            }
            if not feat_map:
                st.warning(f"Ingen features for {product}")
                continue

            keys, values = zip(*feat_map.items())
            for frame in selected_frames:
                for combo in itertools.product(*values):
                    parts = [f"feature={quote(f'{k}:{v}', safe=':')}" for k, v in zip(keys, combo)]
                    img_url = (
                        f"https://content.cylindo.com/api/v2/{CID}"
                        f"/products/{product}/frames/{frame}?{base_qs}&" + "&".join(parts)
                    )
                    all_rows.append({
                        "Product": product,
                        "Frame": frame,
                        "Feature": keys[0],
                        "Option": combo[0],
                        "ImageURL": img_url
                    })
                time.sleep(0.05)

        if not all_rows:
            st.warning("Ingen data genereret – tjek valg.")
        else:
            df = pd.DataFrame(all_rows)
            st.success(f"Genereret {len(df)} rækker.")
            st.dataframe(df.head(10))
            csv_bytes = df.to_csv(index=False, sep=";").encode("utf-8")
            st.download_button(
                label="Download CSV",
                data=csv_bytes,
                file_name=csv_name,
                mime="text/csv"
            )
else:
    st.info("Vælg indstillinger i sidebar og klik 'Generér CSV'.")
