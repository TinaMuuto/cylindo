# === Streamlit Cylindo CSV Generator ===
# Opsætning (skridt-for-skridt):
# 1) Opret en fil i roden af dit repo med navnet `.env`:
#    CYLINDO_CID=4928
# 2) Tilføj `.env` til din `.gitignore`.
# 3) Sørg for du har en `requirements.txt` med:
#    streamlit
#    requests
#    python-dotenv
#    pandas
# 4) Installér dependencies:
#    pip install -r requirements.txt
# 5) Start app med:
#    python3 -m streamlit run streamlit_app.py

import os
import requests
import itertools
import time
from urllib.parse import quote
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# === Load environment variables ===
load_dotenv()
CID = os.getenv("CYLINDO_CID", "4928")  # Henter CID fra .env

# === Streamlit page setup ===
st.set_page_config(page_title="Cylindo CSV Generator", layout="wide")
st.title("Cylindo CSV Generator")

# === Sidebar: User inputs ===
st.sidebar.header("Configuration")

@st.cache_data
def fetch_products(cid):
    """
    Henter alle produktkoder for den angivne Kunde-ID.
    """
    url = f"https://content.cylindo.com/api/v2/{cid}/listcustomerproducts"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return [item['code'] for item in data.get('products', []) if isinstance(item, dict) and 'code' in item]

# Hent produktliste
product_codes = fetch_products(CID)

# Checkbox for “vælg alle”
select_all = st.sidebar.checkbox("Vælg alle produkter", value=False)
if select_all:
    selected_products = product_codes
else:
    selected_products = st.sidebar.multiselect(
        "Vælg én eller flere produkter",
        product_codes,
        default=product_codes[:1]
    )

# Frame-udvælgelse (1–36)
frame_options = list(range(1, 37))
selected_frames = st.sidebar.multiselect("Vælg frames", frame_options, default=[1])

# Filnavn for CSV-download
csv_name = st.sidebar.text_input("Filnavn", value="cylindo_export.csv")

# Generér-knap
generate = st.sidebar.button("Generér CSV")

# === Main: generér data for hvert produkt+frame ===
if generate:
    with st.spinner("Henter data og genererer CSV…"):
        all_rows = []
        base_qs = 'encoding=png&size=1500&removeEnvironmentShadow=true'

        for product in selected_products:
            # Hent feature-konfiguration
            resp = requests.get(
                f"https://content.cylindo.com/api/v2/{CID}/products/{product}/configuration",
                timeout=20
            )
            if resp.status_code != 200:
                st.error(f"Fejl ved hent af konfiguration for {product}: HTTP {resp.status_code}")
                continue
            cfg = resp.json()
            feats = cfg.get('features', [])
            # Build feature->options mapping
            feat_map = {
                f['code']: [opt['code'] for opt in f.get('options', []) if isinstance(opt, dict) and 'code' in opt]
                for f in feats if f.get('options')
            }
            if not feat_map:
                st.warning(f"Ingen features fundet for {product}.")
                continue

            keys, values = zip(*feat_map.items())

            # For hver frame og kombination
            for frame in selected_frames:
                for combo in itertools.product(*values):
                    parts = [f"feature={quote(f'{k}:{v}', safe=':')}" for k, v in zip(keys, combo)]
                    img_url = (
                        f"https://content.cylindo.com/api/v2/{CID}"
                        f"/products/{product}/frames/{frame}?{base_qs}&" + "&".join(parts)
                    )
                    all_rows.append({
                        'Product':  product,
                        'Frame':    frame,
                        'Feature':  keys[0],
                        'Option':   combo[0],
                        'ImageURL': img_url
                    })
                time.sleep(0.05)
        # Vis og download
        if not all_rows:
            st.warning("Ingen data genereret. Tjek valg.")
        else:
            df = pd.DataFrame(all_rows)
            st.success(f"Genereret {len(df)} rækker.")
            st.dataframe(df.head(10))
            csv_bytes = df.to_csv(index=False, sep=';').encode('utf-8')
            st.download_button(
                label="Download CSV",
                data=csv_bytes,
                file_name=csv_name,
                mime='text/csv'
            )
else:
    st.info("Vælg produkter og frames i venstre menu, tryk 'Generér CSV'.")
