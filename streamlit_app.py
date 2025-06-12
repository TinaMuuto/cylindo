# === Streamlit Cylindo CSV Generator med prefix-gruppering ===

import os
import time
import requests
import itertools
from urllib.parse import quote
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# --- Load miljøvariabler ---
load_dotenv()
CID = os.getenv("CYLINDO_CID", "4928")

# --- Sideopsætning ---
st.set_page_config(page_title="Cylindo CSV Generator", layout="wide")
st.title("Cylindo CSV Generator")

# --- Brugsvejledning ---
with st.expander("📖 Sådan bruger du appen"):
    st.markdown("""
    1. **Gruppering (prefix-filter):**  
       Vælg en kode-gruppe (de to første tokens i product-code) eller “Alle” for at starte med hele listen.  
    2. **Søgning:**  
       Skriv en tekst for kun at vise produkter fra din gruppe, der indeholder denne tekst.  
    3. **Vælg alle / Multiselect:**  
       - Sæt flueben i **“Vælg alle”**, hvis du vil markere alle viste produkter.  
       - Ellers vælg manuelt de ønskede produkter i multiselect-feltet.  
    4. **Frames:**  
       Marker én eller flere frame-numre (1–36) for at vælge billedvinkler.  
    5. **Generér CSV:**  
       Klik **“Generér CSV”** i sidebar. Du får et downloadlink til en CSV med alle kombinationer.
    """)
    
# --- Sidebar inputs ---
st.sidebar.header("Configuration")

@st.cache_data
def fetch_product_codes(cid):
    """Henter alle produkt-koder for kunden."""
    url = f"https://content.cylindo.com/api/v2/{cid}/listcustomerproducts"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    return [item["code"] for item in data.get("products", []) if isinstance(item, dict) and "code" in item]

# 1) Hent alle koder
product_codes = fetch_product_codes(CID)

# 2) Byg prefix-grupper
prefix_map = {}
for code in product_codes:
    parts = code.split("_")
    prefix = "_".join(parts[:2]) if len(parts) >= 2 else code
    prefix_map.setdefault(prefix, []).append(code)

# 3) Vælg prefix
prefixes = sorted(prefix_map.keys())
selected_prefix = st.sidebar.selectbox("Grupper efter kode-prefix", ["Alle"] + prefixes)
if selected_prefix == "Alle":
    codes_for_selection = product_codes
else:
    codes_for_selection = prefix_map[selected_prefix]

# 4) Søg i koder
search_query = st.sidebar.text_input("Søg i produkt-kode")
if search_query:
    codes_for_selection = [c for c in codes_for_selection if search_query.lower() in c.lower()]
    if not codes_for_selection:
        st.sidebar.warning("Ingen produkter matcher søgningen.")

# 5) Vælg alle + multiselect
select_all = st.sidebar.checkbox("Vælg alle", False)
if select_all:
    selected_products = codes_for_selection
else:
    selected_products = st.sidebar.multiselect(
        "Vælg produkter",
        codes_for_selection,
        default=codes_for_selection[:1]
    )

# 6) Vælg frames
frame_options = list(range(1, 37))
selected_frames = st.sidebar.multiselect("Vælg frames", frame_options, default=[1])

# 7) Filnavn
csv_name = st.sidebar.text_input("Filnavn", "cylindo_export.csv")

# 8) Generér-knap
generate = st.sidebar.button("Generér CSV")

# --- Main: lav kombinationer og CSV kun for enabled produkter ---
if generate:
    with st.spinner("Genererer…"):
        rows = []
        base_qs = "encoding=png&size=1500&removeEnvironmentShadow=true"
        for product in selected_products:
            cfg_url = f"https://content.cylindo.com/api/v2/{CID}/products/{product}/configuration"
            resp = requests.get(cfg_url, timeout=20)
            if resp.status_code != 200:
                st.error(f"HTTP {resp.status_code} for {product}")
                continue
            cfg = resp.json()
            if not cfg.get("enabled", False):
                # spring deaktiverede produkter
                continue

            feats = cfg.get("features", [])
            feat_map = {
                f["code"]: [opt["code"] for opt in f.get("options", []) if isinstance(opt, dict) and "code" in opt]
                for f in feats if f.get("options")
            }
            if not feat_map:
                st.warning(f"Ingen features fundet for {product}")
                continue

            keys, values = zip(*feat_map.items())
            for frame in selected_frames:
                for combo in itertools.product(*values):
                    parts = [f"feature={quote(f'{k}:{v}', safe=':')}" for k, v in zip(keys, combo)]
                    img_url = (
                        f"https://content.cylindo.com/api/v2/{CID}"
                        f"/products/{product}/frames/{frame}?{base_qs}&" + "&".join(parts)
                    )
                    rows.append({
                        "Product":  product,
                        "Frame":    frame,
                        "Feature":  keys[0],
                        "Option":   combo[0],
                        "ImageURL": img_url
                    })
                time.sleep(0.05)

        if not rows:
            st.warning("Ingen data genereret – tjek dine valg.")
        else:
            df = pd.DataFrame(rows)
            st.success(f"Genereret {len(df)} rækker")
            st.dataframe(df.head(10))
            csv_bytes = df.to_csv(index=False, sep=";").encode("utf-8")
            st.download_button(
                "Download CSV",
                data=csv_bytes,
                file_name=csv_name,
                mime="text/csv"
            )
else:
    st.info("Angiv indstillinger i sidebar og klik 'Generér CSV'.")
