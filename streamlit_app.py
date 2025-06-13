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
    5. Angiv den ønskede billedstørrelse (`Size`) og andre billedindstillinger.
    6. Klik **Generér CSV** – outputtet indeholder kun gyldige feature-kombinationer.
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

# 5) Image Settings
st.sidebar.subheader("Image Settings")
size = st.sidebar.number_input("Size (px)", min_value=1, value=1500)
skip_sharpening = st.sidebar.checkbox("Skip sharpening", value=True)


# 6) CSV filename and button
st.sidebar.subheader("Export")
csv_name = st.sidebar.text_input("Filnavn", "cylindo_export.csv")
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
                    config_url = f"https://content.cylindo.com/api/v2/{CID}/products/{prod}/configuration"
                    r = requests.get(config_url, timeout=20)
                    r.raise_for_status()
                    cfg = r.json()

                    if not cfg.get("enabled", False):
                        continue

                    features_list = cfg.get("features", [])
                    # NEW: Get feature groups to handle mutual exclusions
                    feature_groups = cfg.get("featureGroups", [])

                    if not features_list:
                        st.warning(f"Ingen features fundet for {prod}")
                        continue
                    
                    # Create a lookup map for features that have options
                    features_by_code = {f["code"]: f for f in features_list if f.get("options")}

                    # Find which features are part of a group
                    grouped_feature_codes = {f_code for group in feature_groups for f_code in group.get("features", [])}
                    
                    # List of entities to combine. Can be a standalone feature or a group of features.
                    all_combinable_entities = []

                    # 1. Add standalone features (those not in any group)
                    standalone_codes = set(features_by_code.keys()) - grouped_feature_codes
                    for code in standalone_codes:
                        options_with_key = [(code, opt) for opt in features_by_code[code]["options"]]
                        if options_with_key:
                            all_combinable_entities.append(options_with_key)
                    
                    # 2. Add feature groups as single entities
                    for group in feature_groups:
                        group_options_with_keys = []
                        for f_code in group.get("features", []):
                            if f_code in features_by_code:
                                for opt in features_by_code[f_code]["options"]:
                                    group_options_with_keys.append((f_code, opt))
                        if group_options_with_keys:
                            all_combinable_entities.append(group_options_with_keys)
                    
                    if not all_combinable_entities:
                        st.warning(f"Ingen kombinationer mulige for {prod}")
                        continue
                    
                    # Base URL for the image
                    base_url = f"https://content.cylindo.com/api/v2/{CID}/products/{quote(prod)}/frames"

                    for frame in selected_frames:
                        # NEW: Use the new logic to create valid combinations only
                        for combo_of_tuples in itertools.product(*all_combinable_entities):
                            # combo_of_tuples looks like: ( ('BASE', {'code': 'B1'}), ('TEXTILE', {'code': 'T1'}) )
                            
                            # Build query parameters
                            query_params = {
                                "size": size,
                                "encoding": "png",
                                "removeEnvironmentShadow": "true",
                            }
                            if skip_sharpening:
                                query_params["skipSharpening"] = "true"
                            
                            feature_params = [
                                f"feature={quote(f'{f_code}:{opt['code']}', safe=':')}" 
                                for f_code, opt in combo_of_tuples
                            ]
                            
                            query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
                            
                            url = (
                                f"{base_url}/{frame}/{quote(prod)}.PNG"
                                f"?{query_string}"
                                f"&{'&'.join(feature_params)}"
                            )
                            
                            row = {
                                "Product": prod,
                                "Frame": frame,
                                "size": size,
                                "ImageURL": url
                            }
                            # Add one column for each feature in the combination
                            for f_code, opt in combo_of_tuples:
                                row[f_code] = opt.get("code")

                            rows.append(row)
                    
                    time.sleep(0.05)
                    progress_bar.progress((i + 1) / total_products)

                except requests.exceptions.RequestException as e:
                    st.error(f"Fejl ved hentning af konfiguration for {prod}: {e}")
                    continue

            if not rows:
                st.warning("Ingen data genereret – tjek valg og produktkonfigurationer.")
            else:
                df = pd.DataFrame(rows)
                # Fill NaN for columns that don't apply to a row, making the sheet cleaner
                df = df.fillna('')
                st.success(f"Genereret {len(df)} rækker")
                st.dataframe(df.head(10))
                csv_data = df.to_csv(index=False, sep=";").encode("utf-8")
                st.download_button("Download CSV", data=csv_data, file_name=csv_name, mime="text/csv")
else:
    st.info("Opsæt dine filtre i sidebar og klik 'Generér CSV'")
