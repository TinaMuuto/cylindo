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

# --- Manually define known features that cannot be combined ---
MANUAL_EXCLUSIVE_SETS = [
    {"TEXTILE", "LEATHER"}
]
# --------------------------------------------------------------------

# Page setup
st.set_page_config(page_title="Cylindo CSV Generator", layout="wide")
st.title("Cylindo CSV Generator")

# User guide
with st.expander("📖 Sådan bruger du appen"):
    st.markdown("""
    1. Vælg prefix-gruppe eller “Alle”.
    2. Søg eventuelt i koderne.
    3. Vælg de produkter, du vil generere billeder for.
    4. **Nyt:** Brug søgefeltet under "Materiale Filter" til at finde og vælge specifikke materialer (f.eks. søg på "divina").
    5. Vælg én eller flere vinkler (frames).
    6. Angiv billedindstillinger.
    7. Klik **Generér CSV**.
    """)

# Sidebar
st.sidebar.header("Configuration")

@st.cache_data
def fetch_product_codes(cid):
    """Fetches all product codes from Cylindo API."""
    url = f"https://content.cylindo.com/api/v2/{cid}/listcustomerproducts"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        products = r.json().get("products", [])
        return [p["code"] for p in products if p.get("productType") == "Production" and "code" in p]
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching product codes: {e}")
        return []

@st.cache_data
def get_material_map(product_list):
    """
    Fetches configurations for selected products to find all TEXTILE/LEATHER options.
    Returns a dictionary mapping the material's user-friendly name to its code.
    """
    if not product_list:
        return {}
    
    all_options = {}  # Use dict {code: name} to handle duplicates
    for prod_code in product_list:
        try:
            config_url = f"https://content.cylindo.com/api/v2/{CID}/products/{prod_code}/configuration"
            r = requests.get(config_url, timeout=5) # Shorter timeout for interactive UI
            r.raise_for_status()
            cfg = r.json()
            
            for feature in cfg.get("features", []):
                if feature.get("code") in ["TEXTILE", "LEATHER"]:
                    for option in feature.get("options", []):
                        all_options[option["code"]] = option.get("name", option["code"])
        except requests.exceptions.RequestException:
            continue # Silently fail for a single product to not block the UI
            
    # Invert the map to be {name: code} for the UI
    return {name: code for code, name in all_options.items()}

# --- Sidebar Inputs ---
product_codes = fetch_product_codes(CID)
prefix_map = {}
for code in product_codes:
    parts = code.split("_")
    prefix = "_".join(parts[:2]) if len(parts) >= 2 else code
    prefix_map.setdefault(prefix, []).append(code)
prefixes = ["Alle"] + sorted(prefix_map.keys())
selected_prefix = st.sidebar.selectbox("Grupper efter prefix", prefixes)
codes_to_display = product_codes if selected_prefix == "Alle" else prefix_map[selected_prefix]

search_query = st.sidebar.text_input("Søg i produkt-kode")
if search_query:
    codes_to_display = [c for c in codes_to_display if search_query.lower() in c.lower()]
    if not codes_to_display:
        st.sidebar.warning("Ingen produkter matcher søgningen.")

select_all = st.sidebar.checkbox("Vælg alle produkter", False)
selected_products = codes_to_display if select_all else st.sidebar.multiselect(
    "Vælg produkter", codes_to_display, default=codes_to_display[:1] if codes_to_display else []
)

selected_frames = st.sidebar.multiselect(
    label="Vælg vinkler (1-36)",
    options=list(range(1, 37)), default=[1],
    help="Vælg en eller flere vinkler. Eksempler: 1 = forfra, 17 = bagfra, 4 = skråt forfra, 12 = skråt bagfra."
)

st.sidebar.subheader("Image Settings")
size = st.sidebar.number_input("Size (px)", min_value=1, value=1500)
skip_sharpening = st.sidebar.checkbox("Skip sharpening", value=True)

# --- NEW: Redesigned Material Filter with Search ---
st.sidebar.subheader("Materiale Filter")
material_name_to_code_map = get_material_map(selected_products)
selected_material_codes = []

if material_name_to_code_map:
    all_material_names = sorted(material_name_to_code_map.keys())
    
    # 1. Search box for materials
    material_search_query = st.sidebar.text_input("Søg i materialer")
    
    # 2. Filter materials based on search
    if material_search_query:
        filtered_material_names = [
            name for name in all_material_names
            if material_search_query.lower() in name.lower()
        ]
    else:
        filtered_material_names = all_material_names
        
    # 3. "Select All" checkbox for search results
    select_all_materials = False
    if material_search_query and filtered_material_names:
        select_all_materials = st.sidebar.checkbox("Vælg alle fundne materialer")

    # 4. Multiselect dropdown with filtered options
    default_selection = filtered_material_names if select_all_materials else []
    selected_material_names = st.sidebar.multiselect(
        "Vælg specifikke materialer",
        options=filtered_material_names,
        default=default_selection,
        help="Hvis intet er valgt, inkluderes alle materialer."
    )
    
    # 5. Convert selected names back to codes for filtering logic
    selected_material_codes = [material_name_to_code_map[name] for name in selected_material_names]
# ----------------------------------------------------

st.sidebar.subheader("Export")
csv_name = st.sidebar.text_input("Filnavn", "cylindo_export.csv")
generate = st.sidebar.button("Generér CSV")

# --- Main Logic ---
if generate:
    if not selected_products:
        st.warning("Vælg venligst mindst ét produkt.")
    elif not selected_frames:
        st.warning("Vælg venligst mindst én vinkel.")
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

                    if not cfg.get("enabled", False): continue
                    features_list = cfg.get("features", [])
                    if not features_list:
                        st.warning(f"Ingen features fundet for {prod}"); continue
                    
                    features_by_code = {f["code"]: f for f in features_list if f.get("options")}
                    product_feature_codes = set(features_by_code.keys())
                    
                    all_combinable_entities = []
                    processed_codes = set()

                    # 1. Process manually defined exclusive sets
                    for exclusive_set in MANUAL_EXCLUSIVE_SETS:
                        intersecting_features = product_feature_codes.intersection(exclusive_set)
                        if len(intersecting_features) > 1:
                            group_options_with_keys = []
                            for f_code in intersecting_features:
                                for opt in features_by_code[f_code]["options"]:
                                    # Filter by specific material codes if a selection has been made
                                    if selected_material_codes:
                                        if opt['code'] in selected_material_codes:
                                            group_options_with_keys.append((f_code, opt))
                                    else: # Otherwise, include all
                                        group_options_with_keys.append((f_code, opt))
                            processed_codes.add(f_code)
                            
                            if group_options_with_keys:
                                all_combinable_entities.append(group_options_with_keys)

                    # 2. Process all other standalone features
                    standalone_codes = product_feature_codes - processed_codes
                    for code in standalone_codes:
                        options_with_key = [(code, opt) for opt in features_by_code[code]["options"]]
                        if options_with_key:
                            all_combinable_entities.append(options_with_key)
                    
                    if not all_combinable_entities:
                        st.info(f"Ingen kombinationer for '{prod}' efter anvendelse af filtre."); continue
                    
                    base_url = f"https://content.cylindo.com/api/v2/{CID}/products/{quote(prod)}/frames"

                    for frame in selected_frames:
                        for combo_of_tuples in itertools.product(*all_combinable_entities):
                            query_params = {"size": size, "encoding": "png", "removeEnvironmentShadow": "true"}
                            if skip_sharpening: query_params["skipSharpening"] = "true"
                            feature_params = [f"feature={quote(f'{f_code}:{opt['code']}', safe=':')}" for f_code, opt in combo_of_tuples]
                            query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
                            url = (f"{base_url}/{frame}/{quote(prod)}.PNG?{query_string}&{'&'.join(feature_params)}")
                            row = {"Product": prod, "Frame": frame, "size": size, "ImageURL": url}
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
                df = pd.DataFrame(rows).fillna('')
                st.success(f"Genereret {len(df)} rækker")
                st.dataframe(df.head(10))
                csv_data = df.to_csv(index=False, sep=";").encode("utf-8")
                st.download_button("Download CSV", data=csv_data, file_name=csv_name, mime="text/csv")
else:
    st.info("Opsæt dine filtre i sidebar og klik 'Generér CSV'")
