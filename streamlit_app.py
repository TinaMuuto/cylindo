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

# Sideopsætning
st.set_page_config(page_title="Cylindo CSV Generator", layout="wide")
st.title("Cylindo CSV Generator")

# Brugsvejledning
with st.expander("📖 Sådan bruger du appen"):
    st.markdown("""
    1. Vælg prefix-gruppe eller “Alle”.  
    2. Søg eventuelt i koderne.  
    3. Kryds “Vælg alle” eller multiselect enkelte produkter.  
    4. Vælg én eller flere frame-numre.  
    5. Angiv `Background color` som hex (fx `F9F8F2`) og `Size` (px).  
    6. Klik **Generér CSV** – output indeholder kolonnerne `background`, `size` og for hver feature både `<FEATURE>_code` & `<FEATURE>_name`.  
    """)

# Sidebar
st.sidebar.header("Configuration")

@st.cache_data
def fetch_product_codes(cid):
    r = requests.get(f"https://content.cylindo.com/api/v2/{cid}/listcustomerproducts", timeout=20)
    r.raise_for_status()
    return [p["code"] for p in r.json().get("products", []) if "code" in p]

# 1) Hent koder & gruppering
product_codes = fetch_product_codes(CID)
prefix_map = {}
for code in product_codes:
    parts = code.split("_")
    prefix = "_".join(parts[:2]) if len(parts)>=2 else code
    prefix_map.setdefault(prefix, []).append(code)
prefixes = ["Alle"] + sorted(prefix_map.keys())
selected_prefix = st.sidebar.selectbox("Grupper efter prefix", prefixes)
codes = product_codes if selected_prefix=="Alle" else prefix_map[selected_prefix]

# 2) Søg (delmatch)
search = st.sidebar.text_input("Søg i produkt-kode")
if search:
    codes = [c for c in codes if search.lower() in c.lower()]
    if not codes:
        st.sidebar.warning("Ingen produkter matcher søgningen.")

# 3) Vælg alle / multiselect
select_all = st.sidebar.checkbox("Vælg alle produkter", False)
selected_products = codes if select_all else st.sidebar.multiselect(
    "Vælg produkter", codes, default=codes[:1]
)

# 4) Vælg frames
selected_frames = st.sidebar.multiselect(
    "Vælg frames (1–36)", list(range(1,37)), default=[1]
)

# 5) Background color & Size
background = st.sidebar.text_input("Background color (hex, uden #)", value="F9F8F2")
size = st.sidebar.number_input("Size (px)", min_value=1, value=1024)

# 6) CSV-filnavn og knap
csv_name = st.sidebar.text_input("Filnavn", "cylindo_export.csv")
generate = st.sidebar.button("Generér CSV")

# Main
if generate:
    with st.spinner("Genererer…"):
        rows = []
        for prod in selected_products:
            # Hent configuration & tjek enabled
            r = requests.get(
                f"https://content.cylindo.com/api/v2/{CID}/products/{prod}/configuration",
                timeout=20
            )
            if r.status_code!=200:
                st.error(f"HTTP {r.status_code} for {prod}")
                continue
            cfg = r.json()
            if not cfg.get("enabled", False):
                continue

            feats = cfg.get("features", [])
            feat_map = {f["code"]: f["options"] for f in feats if f.get("options")}
            if not feat_map:
                st.warning(f"Ingen features for {prod}")
                continue

            keys, vals = zip(*feat_map.items())
            for frame in selected_frames:
                for combo in itertools.product(*vals):
                    # URL-bygning med /frames/{frame}/{product}.PNG
                    feature_params = [
                        "feature=" + quote(f"{k}:{opt['code']}", safe=":")
                        for k,opt in zip(keys, combo)
                    ]
                    url = (
                        f"https://content.cylindo.com/api/v2/{CID}"
                        f"/products/{prod}/frames/{frame}/{prod}.PNG"
                        f"?background={background}"
                        f"&size={size}"
                        + "".join(f"&{p}" for p in feature_params)
                    )
                    # Byg row med alle kolonner
                    row = {
                        "Product": prod,
                        "Frame": frame,
                        "background": background,
                        "size": size,
                        "ImageURL": url
                    }
                    for k,opt in zip(keys, combo):
                        row[f"{k}_code"] = opt.get("code")
                        row[f"{k}_name"] = opt.get("name", "")
                    rows.append(row)
                time.sleep(0.05)

        if not rows:
            st.warning("Ingen data genereret – tjek valg.")
        else:
            df = pd.DataFrame(rows)
            st.success(f"Genereret {len(df)} rækker")
            st.dataframe(df.head(10))
            data = df.to_csv(index=False, sep=";").encode("utf-8")
            st.download_button("Download CSV", data=data, file_name=csv_name, mime="text/csv")
else:
    st.info("Opsæt dine filtre i sidebar og klik 'Generér CSV'")
