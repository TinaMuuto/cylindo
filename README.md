# 📸 Cylindo CSV Generator

Dette projekt er en **Streamlit-applikation** rettet mod **Digital afdeling** og er designet til at automatisere genereringen af en komplet liste af billed-URL'er fra **Cylindo's API**. Værktøjet henter produktkonfigurationer og opbygger unikke billed-URL'er for alle mulige kombinationer af de valgte indstillinger.

Applikationen kører live på: **https://cylindo.streamlit.app/**

---

## 🚀 Funktion og Formål

Hovedformålet er at skabe en **CSV-fil**, der kortlægger interne varenumre til deres korresponderende Cylindo billed-URL'er for brug i PIM-systemer, e-handel eller andre digitale platforme.

### Arbejdsgang

1.  **Indlæs Data:** Appen læser lokale produktdata (`raw-data.xlsx`) for at kunne matche Cylindo-kombinationer med interne **Item No** og materialedetaljer.
2.  **API-opslag:** Henter alle produktkoder og konfigurationsdetaljer (features/options) fra Cylindo.
3.  **Filtrering:** Brugeren vælger produktkoder, materialer (f.eks. TEXTILE, LEATHER), vinkler og billedindstillinger (størrelse, skarphed).
4.  **Generering:** Appen beregner **alle gyldige kombinationer** af de valgte funktioner for hvert produkt.
5.  **URL Konstruktion:** For hver kombination og vinkel konstrueres den komplette Cylindo URL.
6.  **Matching:** Den genererede kombination matches mod den lokale `raw-data.xlsx` for at finde det korrekte **Item No**.

---

## ⚙️ Opsætning og Filer

### 1. Nødvendige Filer

| Filnavn | Formål | Vigtige Kolonner (i Excel) |
| :--- | :--- | :--- |
| `raw-data.xlsx` | **Internt produktkatalog** til matching. | `Item No`, `Item Name`, `Base Color`, `Color (lookup InRiver)` |
| `.env` | Miljøvariabler (skal indeholde `CYLINDO_CID` (Customer ID)). | `CID` (Hardcoded standardværdi: `4928`) |

### 2. Matching Logik (`find_item_no`)

Cylindo-kombinationen matches mod den interne rådata (`raw-data.xlsx`) i to trin for at sikre høj nøjagtighed:

1.  **Produktnavn Filtrering:** Først filtreres rådataen baseret på lighed mellem Cylindo's **Product Code** og den interne **Item Name** ved hjælp af **Fuzzy Matching** (`fuzz.token_set_ratio` med en tærskel på **85**).
2.  **Farvefiltrering:** De resterende kandidater filtreres yderligere ved at matche:
    * **Base Color:** Visse ord fra Cylindo's Base Color (`api_base_color`) skal være til stede i rådataens `Base Color`.
    * **Materiale/Farve Kode:** Den normaliserede (kun alfanumerisk) kode fra Cylindo's `TEXTILE` / `LEATHER` matches mod den normaliserede kode i rådataens **`Color (lookup InRiver)`**.

### 3. URL Konstruktionslogik

Appen bruger **`itertools.product`** til at generere kartesiske produkter (alle kombinationer) af valgte features.

* **Eksklusive Sæt:** Sæt af features, der **ikke** kan kombineres (f.eks. TEXTILE og LEATHER), håndteres manuelt (`MANUAL_EXCLUSIVE_SETS`) for at undgå at generere ugyldige URL'er.
* **URL Format:** Den endelige URL opbygges med produktkode, frame/vinkel, billedstørrelse og alle de valgte feature-koder som foreskrevet af Cylindo API:
    ```
    [https://content.cylindo.com/api/v2/](https://content.cylindo.com/api/v2/){CID}/products/{product_code}/frames/{frame}.PNG?size={size}&feature={code:option}&...
    ```

---

## 📸 Billedparametre

Brugeren kan styre de vigtigste billedindstillinger i sidemenuen:

* **Frames (Angles):** Vælg vinkler fra 1 til 36 (f.eks. `1` for front, `17` for bagside).
* **Size (px):** Definerer billedets outputstørrelse.
* **Sharpening:** Mulighed for at **springe skarphed over** (`skipSharpening=true`).
* **Skygge:** Miljøskygger fjernes (`removeEnvironmentShadow=true`).
* **Filformat:** Output formatet er hårdkodet til **PNG** (`encoding=png`).
