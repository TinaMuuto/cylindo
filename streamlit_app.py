import os
import requests
import itertools
from urllib.parse import quote
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# === Load environment variables ===
load_dotenv()
CID = os.getenv("CYLINDO_CID", "4928")

st.set_page_config(page_title="Cylindo CSV Generator", layout="wide")
st.title("Cylindo CSV Generator")

# === Sidebar: user inputs ===
st.sidebar.header("Configuration")
product_codes = []

@st.cache_data
def fetch_products(cid):
    """
    Hent alle product_codes for kunden.
    """
    url = f"https://content.cylindo.com/api/v2/{cid}/listcustomerproducts"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return [item['code'] for item in data.get('products', []) if isinstance(item, dict) and 'code' in item]

product_codes = fetch_products(CID)

product = st.sidebar.selectbox("Vælg produkt", product_codes)

# Frames selection: allow frames 1-36
frame_options = list(range(1, 37))
selected_frames = st.sidebar.multiselect(
    "Vælg frames", frame_options, default=[1]
)

# CSV filename
csv_name = st.sidebar.text_input("Filnavn", value="cylindo_export.csv")

# Generate button
generate = st.sidebar.button("Generér CSV")

# === Main: generate rows and download ===
if generate:
    with st.spinner("Henter konfiguration og genererer CSV…"):
        # fetch feature map
        url_cfg = f"https://content.cylindo.com/api/v2/{CID}/products/{product}/configuration"
        r = requests.get(url_cfg, timeout=20)
        if r.status_code != 200:
            st.error(f"Fejl ved hent af konfiguration: {r.status_code}")
        else:
            cfg = r.json()
            feats = cfg.get('features', [])
            # build feature map
            feat_map = {
                f['code']: [opt['code'] for opt in f.get('options', []) if isinstance(opt, dict) and 'code' in opt]
                for f in feats if f.get('options')
            }
            if not feat_map:
                st.warning("Ingen features fundet for dette produkt.")
            else:
                # assemble rows
                rows = []
                base_qs = 'encoding=png&size=1500&removeEnvironmentShadow=true'
                for frame in selected_frames:
                    for combo in itertools.product(*feat_map.values()):
                        parts = [f"feature={quote(f'{k}:{v}', safe=':')}" for k, v in zip(feat_map.keys(), combo)]
                        img_url = (
                            f"https://content.cylindo.com/api/v2/{CID}"
                            f"/products/{product}/frames/{frame}?{base_qs}&" + "&".join(parts)
                        )
                        # first feature & option
                        first_feat = list(feat_map.keys())[0]
                        first_opt = combo[0]
                        rows.append({
                            'Product': product,
                            'Frame': frame,
                            'Feature': first_feat,
                            'Option': first_opt,
                            'ImageURL': img_url
                        })
                # create DataFrame
                df = pd.DataFrame(rows)
                st.success(f"Genereret {len(df)} rækker.")
                # show head
                st.dataframe(df.head(10))
                # download button
                csv_bytes = df.to_csv(index=False, sep=";").encode('utf-8')
                st.download_button(
                    label="Download CSV",
                    data=csv_bytes,
                    file_name=csv_name,
                    mime='text/csv'
                )

else:
    st.info("Vælg produkt og frames i venstre menu, tryk 'Generér CSV'.")
