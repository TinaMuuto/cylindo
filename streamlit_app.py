import os
import time
import requests
import itertools
import re
from urllib.parse import quote
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from thefuzz import fuzz

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

# --- App Description ---
st.markdown("""
This app allows you to easily generate a list of image URLs from Cylindo for your products. 
It connects to the Cylindo API, fetches product data, and then lets you configure image settings, 
including product codes, materials, angles, and size. The final output is a CSV file containing 
a URL for each configured image, along with its corresponding item number from your raw data.
""")
# ---------------------

# User guide
with st.expander("📖 How to use the app"):
    st.markdown("""
    1. Select a prefix group or "All".
    2. Optionally, search for specific codes.
    3. Select the products you want to generate images for.
    4. Use the search field under "Material Filter" to find and select specific materials.
    5. Choose one or more angles (frames).
    6. Specify the image settings.
    7. Click **Generate CSV**.
    """)

# Sidebar
st.sidebar.header("Configuration")

# --- UPDATED FUNCTION ---
@st.cache_data
def load_raw_data(file_path="raw-data.xlsx"):
    """Loads and preprocesses the raw data from the Excel file for matching."""
    try:
        df = pd.read_excel(file_path, engine='openpyxl')
        
        required_columns = ["Item No", "Item Name", "Base Color", "Color (lookup InRiver)"]
        if not all(col in df.columns for col in required_columns):
            st.error(f"The Excel file '{file_path}' is missing one or more of the required columns: {required_columns}")
            return None

        # NEW: More robust normalization for material codes
        def normalize_material_code(text):
            if pd.isna(text):
                return ""
            return "".join(re.findall(r'[a-zA-Z0-9]+', str(text).lower()))

        df["normalized_material_color"] = df["Color (lookup InRiver)"].apply(normalize_material_code)
        
        def get_word_set(text):
            if pd.isna(text):
                return set()
            return set(re.findall(r'\w+', str(text).lower()))
            
        df["base_color_word_set"] = df["Base Color"].apply(get_word_set)
        
        return df
    except FileNotFoundError:
        st.error(f"IMPORTANT: The Excel file '{file_path}' was not found. Please ensure it is in the same directory as the script.")
        return None
    except Exception as e:
        st.error(f"Error loading the Excel file '{file_path}': {e}")
        return None

# --- NEW CONSOLIDATED MATCHING FUNCTION ---
def find_item_no(api_product_name, api_base_color, api_material_color, raw_data_df, threshold=85):
    """
    Finds an Item No by first pre-filtering by product name similarity, then by colors.
    """
    if not all([api_product_name, api_base_color, api_material_color]) or raw_data_df.empty:
        return ""

    # --- STEP 1: Pre-filter DataFrame by Product Name Similarity ---
    scores = raw_data_df["Item Name"].apply(
        lambda item_name: fuzz.token_set_ratio(api_product_name, str(item_name))
    )
    candidate_df = raw_data_df[scores >= threshold]

    if candidate_df.empty:
        return ""

    # --- STEP 2: Filter the candidates by color ---
    def normalize_material_code(text):
        if not text: return ""
        return "".join(re.findall(r'[a-zA-Z0-9]+', str(text).lower()))

    material_color_api_norm = normalize_material_code(api_material_color)
    base_color_api_words = set(re.findall(r'\w+', str(api_base_color).lower()))
    
    condition1 = candidate_df['base_color_word_set'].apply(
        lambda excel_words: len(excel_words) > 0 and excel_words.issubset(base_color_api_words)
    )
    condition2 = candidate_df['normalized_material_color'] == material_color_api_norm
    
    final_match = candidate_df[condition1 & condition2]

    if not final_match.empty:
        return final_match.iloc[0]["Item No"]
        
    return ""


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
        st.sidebar.warning(f"Could not retrieve materials for: {', '.join(api_errors)}")
            
    return {name: code for code, name in all_options.items()}

# --- Sidebar Inputs ---
# ... (rest of sidebar code is unchanged) ...
product_codes = fetch_product_codes(CID)
prefix_map = {}
for code in product_codes:
    parts = code.split("_")
    prefix = "_".join(parts[:2]) if len(parts) >= 2 else code
    prefix_map.setdefault(prefix, []).append(code)
prefixes = ["All"] + sorted(prefix_map.keys())
selected_prefix = st.sidebar.selectbox("Group by Prefix", prefixes)
codes_to_display = product_codes if selected_prefix == "All" else prefix_map[selected_prefix]

search_query = st.sidebar.text_input("Search product code")
if search_query:
    codes_to_display = [c for c in codes_to_display if search_query.lower() in c.lower()]
    if not codes_to_display:
        st.sidebar.warning("No products match the search query.")

select_all = st.sidebar.checkbox("Select all products", False)
selected_products = codes_to_display if select_all else st.sidebar.multiselect(
    "Select Products", codes_to_display, default=codes_to_display[:1] if codes_to_display else []
)

selected_frames = st.sidebar.multiselect(
    label="Select Angles (1-36)",
    options=list(range(1, 37)), default=[1],
    help="Select one or more angles. Examples: 1 = front, 17 = back, 4 = diagonal front, 12 = diagonal back."
)

st.sidebar.subheader("Image Settings")
size = st.sidebar.number_input("Size (px)", min_value=1, value=1500)
skip_sharpening = st.sidebar.checkbox("Skip sharpening", value=True)

st.sidebar.subheader("Material Filter")
material_name_to_code_map = get_material_map(selected_products)
selected_material_names = []

if material_name_to_code_map:
    all_material_names = sorted(material_name_to_code_map.keys())
    material_search_query = st.sidebar.text_input("Search materials")
    
    if material_search_query:
        filtered_material_names = [name for name in all_material_names if material_search_query.lower() in name.lower()]
    else:
        filtered_material_names = all_material_names
        
    select_all_materials = False
    if material_search_query and filtered_material_names:
        select_all_materials = st.sidebar.checkbox("Select all found materials")

    default_selection = filtered_material_names if select_all_materials else []
    selected_material_names = st.sidebar.multiselect(
        "Select specific materials",
        options=filtered_material_names,
        default=default_selection,
        help="If nothing is selected, all materials will be included."
    )
else:
    if selected_products:
        st.sidebar.info("The selected products have no TEXTILE or LEATHER materials to filter.")

selected_material_codes = [material_name_to_code_map.get(name) for name in selected_material_names if name in material_name_to_code_map]
#----------------------------------------------------

st.sidebar.subheader("Export")
csv_name = st.sidebar.text_input("File name", "cylindo_export.csv")
generate = st.sidebar.button("Generate CSV")

# --- Main Logic ---
if generate:
    if not selected_products:
        st.warning("Please select at least one product.")
    elif not selected_frames:
        st.warning("Please select at least one angle.")
    else:
        raw_data_df = load_raw_data("raw-data.xlsx")
        
        if raw_data_df is None:
            st.stop()

        if selected_material_codes:
            st.info(f"Filtering for {len(selected_material_codes)} specific materials.")
        
        with st.spinner("Generating..."):
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
                        st.warning(f"No features found for {prod}"); continue
                    
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
                        st.info(f"No combinations for '{prod}' after applying filters."); continue
                    
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
                            
                            # --- REVISED MATCHING CALL ---
                            api_base_color = row.get("BASE")
                            api_material_color = row.get("TEXTILE") or row.get("LEATHER")
                            row["Item No"] = find_item_no(
                                api_product_name=prod,
                                api_base_color=api_base_color,
                                api_material_color=api_material_color,
                                raw_data_df=raw_data_df
                            )
                            # -----------------------------

                            rows.append(row)
                    
                    time.sleep(0.05)
                    progress_bar.progress((i + 1) / total_products)

                except requests.exceptions.RequestException as e:
                    st.error(f"Error fetching configuration for {prod}: {e}")
                    continue

            if not rows:
                st.warning("No data generated – please check your selections and product configurations.")
            else:
                df = pd.DataFrame(rows)
                
                cols = df.columns.tolist()
                if "Item No" in cols:
                    cols.insert(1, cols.pop(cols.index('Item No')))
                    df = df[cols]

                df = df.fillna('')
                st.success(f"Generated {len(df)} rows")
                st.dataframe(df.head(10))
                csv_data = df.to_csv(index=False, sep=";").encode("utf-8")
                st.download_button("Download CSV", data=csv_data, file_name=csv_name, mime="text/csv")
else:
    st.info("Set up your filters in the sidebar and click 'Generate CSV'")
