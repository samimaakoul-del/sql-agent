"""Interface Streamlit.

Lancer en local :  streamlit run src/sql_agent/ui/app.py
"""

import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="SQL Agent", page_icon="🔍", layout="wide")
st.title("🔍 SQL Agent")
st.caption("Repère, explique et corrige les requêtes SQL lentes – sans modifier la base.")

# --- État de l'API ---
try:
    health = httpx.get(f"{API_URL}/health", timeout=5).json()
except httpx.HTTPError:
    st.error(f"API injoignable sur {API_URL}. Vérifiez que le service « api » est démarré.")
    st.stop()

st.sidebar.success(f"API connectée – v{health['version']}")

# --- F1 : requêtes les plus coûteuses ---
st.header("Requêtes les plus coûteuses")

col1, col2, col3 = st.columns([2, 2, 1])
order_label = col1.radio(
    "Classer par",
    ["Temps total (charge serveur)", "Temps moyen (par appel)"],
    horizontal=True,
)
order_by = "total" if order_label.startswith("Temps total") else "mean"
limit = col2.slider("Nombre de requêtes", min_value=5, max_value=50, value=10, step=5)
col3.write("")
col3.button("🔄 Actualiser", use_container_width=True)

try:
    resp = httpx.get(
        f"{API_URL}/slow-queries", params={"limit": limit, "order_by": order_by}, timeout=15
    )
except httpx.HTTPError:
    st.error("L'API ne répond pas.")
    st.stop()

if resp.status_code != 200:
    st.error(resp.json().get("detail", f"Erreur {resp.status_code}"))
    st.stop()

queries = resp.json()
if not queries:
    st.info(
        "Rien à optimiser pour l'instant : aucune requête enregistrée. "
        "Générez du trafic avec `docker compose run --rm workload`."
    )
    st.stop()

st.dataframe(
    [
        {
            "Rang": i,
            "Requête": q["query"],
            "Temps moyen (ms)": q["mean_ms"],
            "Appels": q["calls"],
            "Temps total (ms)": q["total_ms"],
            "Part du total (%)": q["share_pct"],
        }
        for i, q in enumerate(queries, start=1)
    ],
    hide_index=True,
    use_container_width=True,
    column_config={
        "Part du total (%)": st.column_config.ProgressColumn(
            "Part du total (%)", min_value=0, max_value=100, format="%.1f %%"
        ),
        "Requête": st.column_config.TextColumn("Requête", width="large"),
    },
)
st.caption(
    "Les valeurs des requêtes sont remplacées par $1, $2… : pg_stat_statements regroupe "
    "les requêtes de même forme."
)
