import os
import time
import requests
import itertools
import re
from urllib.parse import quote
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from thefuzz import fuzz # <-- NEW: Import for fuzzy string matching

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
    4. Brug søgefeltet under "Materiale Filter" til at finde og vælge specifikke materialer.
    5. Vælg én eller flere vinkler (frames).
    6. Angiv billedindstillinger.
    7. Klik **Generér CSV**.
    """)

# Sidebar
st.sidebar.header("Configuration")

# --- UPDATED FUNCTION ---
@st.cache_data
def load_raw_data(file_path="raw-data.xlsx"):
    """Loads and preprocesses the raw data from the Excel file for matching."""
    try:
        df = pd.read_excel(file_path, engine='openpyxl')
        
        # NEW: Now also requires "Item Name"
        required_columns = ["Item No", "Item Name", "Base Color", "Color (lookup InRiver)"]
        if not all(col in df.columns for col in required_columns):
            st.error(f"Excel-filen '{file_path}' mangler en eller flere af de påkrævede kolonner: {required_columns}")
            return None

        # Pre-process columns for matching
        df["normalized_material_color"] = df["Color (lookup InRiver)"].astype(str).str.replace(' ', '').str.lower()
        
        def get_word_set(text):
            if pd.isna(text):
                return set()
            return set(re.findall(r'\w+', str(text).lower()))
            
        df["base_color_word_set"] = df["Base Color"].apply(get_word_set)
        
        return df
    except FileNotFoundError:
        st.error(f"VIGTIGT: Excel-filen '{file_path}' blev ikke fundet. Sørg for, at den er placeret i samme mappe som scriptet.")
        return None
    except Exception as e:
        st.error(f"Fejl ved indlæsning af Excel-fil '{file_path}': {e}")
        return None

# --- NEW FUNCTION ---
def find_best_product_match_index(api_product_name, raw_data_df, threshold=85):
    """
    Finds the index of the best matching product in raw_data_df using fuzzy string matching.
    Returns the index if the match score is above the threshold, otherwise None.
    """
    # Calculate similarity scores for the API product name against all item names in the Excel file.
    # We use token_set_ratio which is good at handling extra words or codes.
    scores = raw_data_df["Item Name"].apply(
        lambda item_name: fuzz.token_set_ratio(api_product_name, str(item_name))
    )
    
    if scores.empty or scores.max() < threshold:
        return None
        
    return scores.idxmax()

# --- NEW, SIMPLER FUNCTION ---
def check_color_match(api_base_color, api_material_color, candidate_row):
    """
    Checks if the API colors match the colors in the pre-selected candidate row from Excel.
    """
    if not api_base_color or not api_material_color:
        return False

    # Normalize API colors
    material_color_api_norm = str(api_material_color).replace(' ', '').lower()
    base_color_api_words = set(re.findall(r'\w+', str(api_base_color).lower()))
    
    # Check material color (exact match)
    material_match = (candidate_row['normalized_material_color'] == material_color_api_norm)
    
    # Check base color (word subset match)
    excel_base_words = candidate_row['base_color_word_set']
    base_match = len(excel_base_words) > 0 and excel_base_words.issubset(base_color_api_words)
    
    return material_match and base_match

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
    """
    if not product_list:
        return {}
    
    all_options = {}
    api_errors = []
    for prod_code in product_list:
        try:
            config_url = f"https://content.cylindo.com/api/v2/{CID}/products/{prod_code}/configuration"
            r = requests.get(config_url, timeout=5)
            r.raise_for_status()
            cfg = r.json()
            
            for feature in cfg.get("features", []):
                if feature.get("code") in ["TEXTILE", "LEATHER"]:
                    for option in feature.get("options", []):
                        all_options[option["code"]] = option.get("name", option["code"])
        except requests.exceptions.RequestException:
            api_errors.append(prod_code)
            continue
    
    if api_errors:
        st.sidebar.warning(f"Kunne ikke hente materialer for: {', '.join(api_errors)}")
            
    return {name: code for code, name in all_options.items()}

# --- Sidebar Inputs ---
product_codes = fetch_product_codes(CID)
# ... (rest of sidebar code is unchanged) ...
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

st.sidebar.subheader("Materiale Filter")
material_name_to_code_map = get_material_map(selected_products)
selected_material_names = [] 

if material_name_to_code_map:
    all_material_names = sorted(material_name_to_code_map.keys())
    material_search_query = st.sidebar.text_input("Søg i materialer")
    
    if material_search_query:
        filtered_material_names = [name for name in all_material_names if material_search_query.lower() in name.lower()]
    else:
        filtered_material_names = all_material_names
        
    select_all_materials = False
    if material_search_query and filtered_material_names:
        select_all_materials = st.sidebar.checkbox("Vælg alle fundne materialer")

    default_selection = filtered_material_names if select_all_materials else []
    selected_material_names = st.sidebar.multiselect(
        "Vælg specifikke materialer",
        options=filtered_material_names,
        default=default_selection,
        help="Hvis intet er valgt, inkluderes alle materialer."
    )
else:
    if selected_products:
        st.sidebar.info("De valgte produkter har ingen TEXTILE eller LEATHER materialer at filtrere på.")

selected_material_codes = [material_name_to_code_map.get(name) for name in selected_material_names if name in material_name_to_code_map]
#----------------------------------------------------

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
        raw_data_df = load_raw_data("raw-data.xlsx")
        
        if raw_data_df is None:
            st.stop()

        if selected_material_codes:
            st.info(f"Filtrerer for {len(selected_material_codes)} specifikke materialer.")
        
        with st.spinner("Genererer…"):
            rows = []
            progress_bar = st.progress(0)
            total_products = len(selected_products)
            
            # NEW: Cache for product name matches to avoid re-calculating
            product_match_cache = {}

            for i, prod in enumerate(selected_products):
                # --- NEW: STEP 1 - Find best product match first ---
                best_match_index = product_match_cache.get(prod)
                if best_match_index is None: # If not in cache, find it
                    best_match_index = find_best_product_match_index(prod, raw_data_df)
                    product_match_cache[prod] = best_match_index

                candidate_row = None
                item_no_from_product_match = ""
                if best_match_index is not None:
                    candidate_row = raw_data_df.iloc[best_match_index]
                    item_no_from_product_match = candidate_row["Item No"]
                # ----------------------------------------------------
                
                try:
                    # ... (The code to get Cylindo configurations is the same) ...
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

                    for exclusive_set in MANUAL_EXCLUSIVE_SETS:
                        intersecting_features = product_feature_codes.intersection(exclusive_set)
                        if len(intersecting_features) > 1:
                            group_options_with_keys = []
                            for f_code in intersecting_features:
                                for opt in features_by_code[f_code]["options"]:
                                    if not selected_material_codes or opt['code'] in selected_material_codes:
                                        group_options_with_keys.append((f_code, opt))
                                processed_codes.add(f_code)
                            
                            if group_options_with_keys:
                                all_combinable_entities.append(group_options_with_keys)

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
                            # ... (Build URL and base row - same as before) ...
                            query_params = {"size": size, "encoding": "png", "removeEnvironmentShadow": "true"}
                            if skip_sharpening: query_params["skipSharpening"] = "true"
                            feature_params = [f"feature={quote(f'{f_code}:{opt['code']}', safe=':')}" for f_code, opt in combo_of_tuples]
                            query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
                            url = (f"{base_url}/{frame}/{quote(prod)}.PNG?{query_string}&{'&'.join(feature_params)}")
                            
                            row = {"Product": prod, "Frame": frame, "size": size, "ImageURL": url}
                            for f_code, opt in combo_of_tuples:
                                row[f_code] = opt.get("code")
                            
                            row["Item No"] = "" # Default to empty

                            # --- NEW: STEP 2 - Check colors against the pre-found candidate row ---
                            if candidate_row is not None:
                                api_base_color = row.get("BASE")
                                api_material_color = row.get("TEXTILE") or row.get("LEATHER")

                                if check_color_match(api_base_color, api_material_color, candidate_row):
                                    row["Item No"] = item_no_from_product_match
                            # -----------------------------------------------------------------------

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
                
                cols = df.columns.tolist()
                if "Item No" in cols:
                    cols.insert(1, cols.pop(cols.index('Item No')))
                    df = df[cols]

                df = df.fillna('')
                st.success(f"Genereret {len(df)} rækker")
                st.dataframe(df.head(10))
                csv_data = df.to_csv(index=False, sep=";").encode("utf-8")
                st.download_button("Download CSV", data=csv_data, file_name=csv_name, mime="text/csv")
else:
    st.info("Opsæt dine filtre i sidebar og klik 'Generér CSV'")
