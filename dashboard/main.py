"""Punto de entrada del dashboard — hackaton-fup.

Ejecutar (con la API corriendo aparte en :8000):
    streamlit run dashboard/main.py

Navegación real en la barra lateral (Streamlit multipage), en vez de una
sola página larga: Resumen (KPIs/gráficas/alertas) y Agente (chat con
panel de razonamiento). Ver dashboard/theme.py para la paleta y el CSS
compartido, y DECISIONS.md para los supuestos de datos.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from dashboard.theme import inject_css, sidebar_brand
from dashboard.views import agente, resumen

st.set_page_config(page_title="HIS · hackaton-fup", layout="wide", page_icon="🏥")
inject_css()
sidebar_brand()

pagina = st.navigation(
    [
        st.Page(resumen.render, title="Resumen", icon="📊", url_path="resumen", default=True),
        st.Page(agente.render, title="Agente", icon="💬", url_path="agente"),
    ]
)
pagina.run()
