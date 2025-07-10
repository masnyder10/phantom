import streamlit as st
import pandas as pd
import requests
import io

st.set_page_config(page_title="Phantom Provider Detector", layout="wide")

st.title("Phantom Provider Detector")
st.markdown("Check NPIs against NPPES and flag suspicious provider activity.")

# Upload CSV or manual entry
upload = st.file_uploader("Upload CSV with NPI, CPT, and State columns (optional):", type="csv")
npi_input = st.text_area("Paste NPI numbers (one per line):")
submitted = st.button("Run Check")

@st.cache_data(show_spinner=False)
def fetch_nppes(npi):
    url = f"https://npiregistry.cms.hhs.gov/api/?number={npi}&version=2.1"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        return data.get("results", [{}])[0]
    except:
        return {}

@st.cache_data(show_spinner=False)
def load_deceased_npies():
    return {"1234567890", "9876543210"}  # Replace with real data if available

@st.cache_data(show_spinner=False)
def load_prison_npies():
    return {"1518983506"}  # Replace with FOIA data if available

def risk_assessment(npi, data, deceased_npies, prison_npies, cpt_code=None, claim_state=None, provider_state=None):
    flags = []
    score = 0

    if not data:
        return {"NPI": npi, "Risk Score": 100, "Risk Flags": "No match (fake or invalid NPI)"}

    basic = data.get("basic", {})
    name = basic.get("name") or f"{basic.get('first_name', '')} {basic.get('last_name', '')}".strip()
    status = basic.get("status", "Unknown")
    taxonomy = data.get("taxonomies", [{}])[0].get("desc", "No taxonomy")
    license_state = data.get("addresses", [{}])[0].get("state", "")
    org_name = basic.get("organization_name", "")

    if status != "A":
        flags.append("Inactive provider")
        score += 70

    if not name.strip():
        flags.append("Missing name")
        score += 10

    if taxonomy == "No taxonomy":
        flags.append("Missing taxonomy")
        score += 10

    if npi in deceased_npies:
        flags.append("Deceased provider")
        score += 70

    if npi in prison_npies:
        flags.append("Provider in prison")
        score += 90

    if cpt_code and taxonomy:
        if ("Psychiatry" in taxonomy and cpt_code.startswith("29")) or ("Cardiology" in taxonomy and cpt_code.startswith("93")):
            pass  # Acceptable
        else:
            flags.append("CPT/taxonomy mismatch")
            score += 30

    if claim_state and provider_state and claim_state != provider_state:
        flags.append("Cross-state billing anomaly")
        score += 25

    return {
        "NPI": npi,
        "Provider Name": name,
        "Status": status,
        "Taxonomy": taxonomy,
        "License State": license_state,
        "Organization Name": org_name,
        "Risk Score": score,
        "Risk Flags": ", ".join(flags)
    }

if submitted:
    deceased_npies = load_deceased_npies()
    prison_npies = load_prison_npies()

    results = []
    if upload:
        df_uploaded = pd.read_csv(upload)
        for _, row in df_uploaded.iterrows():
            npi = str(row["NPI"])
            cpt_code = str(row["CPT"]) if "CPT" in row else None
            claim_state = str(row["State"]) if "State" in row else None
            res = fetch_nppes(npi)
            row_result = risk_assessment(npi, res, deceased_npies, prison_npies, cpt_code, claim_state, res.get("addresses", [{}])[0].get("state", ""))
            results.append(row_result)
    elif npi_input.strip():
        npis = [line.strip() for line in npi_input.split("\n") if line.strip()]
        for npi in npis:
            if not npi.isdigit():
                results.append({"NPI": npi, "Risk Score": 100, "Risk Flags": "Invalid NPI format"})
                continue
            res = fetch_nppes(npi)
            row_result = risk_assessment(npi, res, deceased_npies, prison_npies)
            results.append(row_result)

    df = pd.DataFrame(results)
    st.success("Check complete.")

    def highlight_risk(row):
        if row["Risk Score"] >= 90:
            return ["background-color: #ffcccc"] * len(row)
        elif row["Risk Score"] >= 70:
            return ["background-color: #ffe699"] * len(row)
        return ["background-color: #e2f0cb"] * len(row)

    st.dataframe(df.style.apply(highlight_risk, axis=1), use_container_width=True)

    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("Download Results as CSV", data=csv, file_name="phantom_provider_results.csv", mime="text/csv")

