"""Interface Streamlit (squelette semaine 1).

Lancer en local :  streamlit run src/sql_agent/ui/app.py
"""

import os

import httpx
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="SQL Agent", page_icon="🔍", layout="wide")
st.title("🔍 SQL Agent")
st.caption("Repère, explique et corrige les requêtes SQL lentes – sans modifier la base.")

try:
    health = httpx.get(f"{API_URL}/health", timeout=5).json()
    st.success(f"API connectée (version {health['version']})")
except httpx.HTTPError:
    st.error(f"API injoignable sur {API_URL}. Vérifiez que le service `api` est démarré.")
