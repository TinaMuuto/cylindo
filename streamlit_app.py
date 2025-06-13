import os
import time
import requests
import itertools
from urllib.parse import quote
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
CID = os.getenv("CYLINDO_CID", "4928")

# Page setup
st.set_page_config(page_title="Cylindo CSV Generator", layout="wide")
st.title("Cylindo CSV Generator")

# User guide
with st.expander("📖 Sådan bruger du appen"):
    st.markdown("""
    1. Vælg prefix-gruppe eller “Alle”.
    2. Søg eventuelt i koderne.
    3. Kryds “Vælg alle” eller multiselect enkelte produkter.
    4. Vælg én eller flere frame-numre.
    5. Angiv den ønskede billedstørrelse (`Size`). Baggrunden vil være transparent.
    6. Klik **Generér CSV** – output indeholder de valgte kolonner og én kolonne per feature.
    """)

# Sidebar
st.sidebar.header("Configuration")

@st.cache_data
def fetch_product_codes(cid):
    """Fetches product codes from Cylindo API, filtering for Production-type products."""
    url = f"https://content.cylindo.com/api/v2/{cid}/listcustomerproducts"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        products = r.json().get("products", [])
        
        # Filter for products where productType is "Production"
        production_products = [
            p["code"] for p in products
            if p.get("productType") == "Production" and "code" in p
        ]
        return production_products
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching product codes: {e}")
        return []

# 1) Fetch codes & grouping
product_codes = fetch_product_codes(CID)
prefix_map = {}
for code in product_codes:
    parts = code.split("_")
    prefix = "_".join(parts[:2]) if len(parts) >= 2 else code
    prefix_map.setdefault(prefix, []).append(code)
prefixes = ["Alle"] + sorted(prefix_map.keys())
selected_prefix = st.sidebar.selectbox("Grupper efter prefix", prefixes)
codes_to_display = product_codes if selected_prefix == "Alle" else prefix_map[selected_prefix]

# 2) Search (partial match)
search_query = st.sidebar.text_input("Søg i produkt-kode")
if search_query:
    codes_to_display = [c for c in codes_to_display if search_query.lower() in c.lower()]
    if not codes_to_display:
        st.sidebar.warning("Ingen produkter matcher søgningen.")

# 3) Select all / multiselect
select_all = st.sidebar.checkbox("Vælg alle produkter", False)
selected_products = codes_to_display if select_all else st.sidebar.multiselect(
    "Vælg produkter", codes_to_display, default=codes_to_display[:1] if codes_to_display else []
)

# 4) Select frames
selected_frames = st.sidebar.multiselect(
    "Vælg frames (1–36)", list(range(1, 37)), default=[1]
)

# 5) Size (Background input removed)
size = st.sidebar.number_input("Size (px)", min_value=1, value=1024)

# 6) CSV filename and button
csv_name = st.sidebar.text_input("Filnavn", "cylindo_export_transparent.csv")
generate = st.sidebar.button("Generér CSV")

# Main content area
if generate:
    if not selected_products:
        st.warning("Vælg venligst mindst ét produkt.")
    elif not selected_frames:
        st.warning("Vælg venligst mindst ét frame-nummer.")
    else:
        with st.spinner("Genererer…"):
            rows = []
            progress_bar = st.progress(0)
            total_products = len(selected_products)

            for i, prod in enumerate(selected_products):
                try:
                    # Fetch configuration
                    config_url = f"https://content.cylindo.com/api/v2/{CID}/products/{prod}/configuration"
                    r = requests.get(config_url, timeout=20)
                    r.raise_for_status()
                    cfg = r.json()

                    if not cfg.get("enabled", False):
                        continue

                    features_list = cfg.get("features", [])
                    if not features_list:
                        st.warning(f"Ingen features fundet for {prod}")
                        continue

                    feat_map = {f["code"]: f["options"] for f in features_list if f.get("options")}
                    if not feat_map:
                        st.warning(f"Ingen features med options fundet for {prod}")
                        continue
                    
                    keys, vals = zip(*feat_map.items())
                    
                    for frame in selected_frames:
                        for combo in itertools.product(*vals):
                            feature_params = [
                                "feature=" + quote(f"{k}:{opt['code']}", safe=":")
                                for k, opt in zip(keys, combo)
                            ]
                            # MODIFIED: Removed background parameter from URL for transparency
                            url = (
                                f"https://content.cylindo.com/api/v2/{CID}"
                                f"/products/{quote(prod)}/frames/{frame}/{quote(prod)}.PNG"
                                f"?size={size}"
                                + "".join(f"&{p}" for p in feature_params)
                            )
                            # MODIFIED: Updated row definition for new header requirements
                            row = {
                                "Product": prod,
                                "Frame": frame,
                                "size": size,
                                "ImageURL": url
                            }
                            # MODIFIED: Creates one column per feature with the feature code as header
                            for k, opt in zip(keys, combo):
                                row[k] = opt.get("code")
                            rows.append(row)
                    
                    time.sleep(0.05) # Small delay to avoid overwhelming the API
                    progress_bar.progress((i + 1) / total_products)

                except requests.exceptions.RequestException as e:
                    st.error(f"Fejl ved hentning af konfiguration for {prod}: {e}")
                    continue

            if not rows:
                st.warning("Ingen data genereret – tjek valg og produktkonfigurationer.")
            else:
                df = pd.DataFrame(rows)
                st.success(f"Genereret {len(df)} rækker")
                st.dataframe(df.head(10))
                csv_data = df.to_csv(index=False, sep=";").encode("utf-8")
                st.download_button(
                    "Download CSV",
                    data=csv_data,
                    file_name=csv_name,
                    mime="text/csv"
                )
else:
    st.info("Opsæt dine filtre i sidebar og klik 'Generér CSV'")
