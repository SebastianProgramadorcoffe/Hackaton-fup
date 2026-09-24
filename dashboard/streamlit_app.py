"""Dashboard del HIS — hackaton-fup.

Ejecutar (con la API corriendo aparte en :8000):
    streamlit run dashboard/streamlit_app.py

Las gráficas leen directo de SQLite (rápido, sin costo de API). El chat de
la barra lateral es el único punto que llama al agente NL2SQL vía la API.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

from app.alerts import alertas_activas
from dashboard.queries import (
    cirugias_programadas_por_semana,
    espera_promedio_por_triage,
    fecha_corte_demo,
    medicamentos_bajo_inventario,
    ocupacion_por_servicio,
    resumen_kpis,
)

# Paleta validada del proyecto (ver skill dataviz / references/palette.md).
SERIE_1 = "#2a78d6"  # azul — magnitud / serie principal
SERIE_2 = "#eb6834"  # naranja — segunda serie categórica (p. ej. capacidad)
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
INK_SECONDARY = "#52514e"
GRIDLINE = "#e1e0d9"

API_URL = "http://localhost:8000"

st.set_page_config(page_title="HIS · hackaton-fup", layout="wide")


def _apply_chart_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        plot_bgcolor="#fcfcfb",
        paper_bgcolor="#fcfcfb",
        font=dict(color=INK_SECONDARY, family="system-ui, -apple-system, 'Segoe UI', sans-serif"),
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    fig.update_xaxes(gridcolor=GRIDLINE, zeroline=False)
    fig.update_yaxes(gridcolor=GRIDLINE, zeroline=False)
    return fig


st.title("🏥 Dashboard HIS — Hospital Susana López de Valencia")
st.caption(
    f"Prototipo de hackatón. Fecha de corte usada como \"hoy\": **{fecha_corte_demo()}** "
    "(el dataset es histórico y fijo — ver DECISIONS.md)."
)

st.subheader("🚨 Alertas activas")
todas_las_alertas = alertas_activas()
n_criticas = sum(1 for a in todas_las_alertas if a.nivel == "critical")
n_warning = len(todas_las_alertas) - n_criticas
if not todas_las_alertas:
    st.success("Sin alertas activas de camas ni de inventario en este momento.")
else:
    st.markdown(f"**{n_criticas} crítica(s)** · **{n_warning} de atención**")
    top_alertas = todas_las_alertas[:6]  # las más severas primero; el detalle completo está más abajo
    for a in top_alertas:
        texto = f"**{a.servicio_o_medicamento}** — {a.detalle}"
        st.error(texto) if a.nivel == "critical" else st.warning(texto)
    if len(todas_las_alertas) > len(top_alertas):
        st.caption(
            f"+ {len(todas_las_alertas) - len(top_alertas)} alerta(s) más — ver el detalle de "
            "inventario más abajo, o consultar GET /alerts."
        )
    st.caption(
        "Notificación automática: `scripts/check_alerts.py` reconsulta estos mismos umbrales y "
        "puede programarse (cron / Programador de tareas) para avisar por webhook — ver README.md."
    )

st.divider()

kpis = resumen_kpis()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Camas UCI ocupadas hoy", f"{kpis['camas_uci_ocupadas']} / {kpis['camas_uci_capacidad']}")
espera = kpis["espera_prom_urgencias_min"]
c2.metric("Espera prom. urgencias (7d)", f"{espera:.0f} min" if espera is not None else "s/d")
c3.metric("Medicamentos en alerta (<5 días)", kpis["medicamentos_en_alerta"])
top = kpis["servicio_mas_ocupado_pct"]
c4.metric("Servicio más ocupado", top["servicio"].title() if top else "s/d", f"{top['pct_ocupacion']}%" if top else "")

st.divider()

col_izq, col_der = st.columns(2)

with col_izq:
    st.subheader("Ocupación de camas por servicio (hoy)")
    df_ocup = ocupacion_por_servicio()
    fig = go.Figure()
    fig.add_bar(name="Ocupadas", x=df_ocup["servicio"], y=df_ocup["ocupadas"], marker_color=SERIE_1)
    fig.add_bar(name="Capacidad estimada", x=df_ocup["servicio"], y=df_ocup["capacidad"], marker_color=SERIE_2)
    fig.update_layout(barmode="group", xaxis_tickangle=-30)
    st.plotly_chart(_apply_chart_theme(fig), width='stretch')
    st.caption("Capacidad estimada = camas distintas observadas en el histórico, no la capacidad física real.")

with col_der:
    st.subheader("Tiempo de espera promedio en urgencias (últimos 7 días)")
    df_espera = espera_promedio_por_triage(dias=7)
    if df_espera.empty:
        st.info("Sin datos de urgencias en los últimos 7 días de la fecha de corte.")
    else:
        df_espera["triage"] = "Triage " + df_espera["nivel_triage"].astype(str)
        fig = px.bar(
            df_espera, x="triage", y="minutos_espera_prom",
            color_discrete_sequence=[SERIE_1],
            labels={"triage": "Nivel de triage", "minutos_espera_prom": "Minutos"},
        )
        st.plotly_chart(_apply_chart_theme(fig), width='stretch')

col_izq2, col_der2 = st.columns(2)

with col_izq2:
    st.subheader("Cirugías programadas por semana (uso de quirófanos)")
    df_cir = cirugias_programadas_por_semana(semanas=12)
    if df_cir.empty:
        st.info("Sin cirugías programadas en el rango.")
    else:
        fig = px.line(df_cir, x="semana", y="n_cirugias", markers=True, color_discrete_sequence=[SERIE_1])
        st.plotly_chart(_apply_chart_theme(fig), width='stretch')

with col_der2:
    st.subheader("⚠️ Alertas de inventario de medicamentos")
    st.caption("Stock **simulado** para el prototipo — el consumo diario sí es real (ver DECISIONS.md).")
    df_alertas = medicamentos_bajo_inventario()
    if df_alertas.empty:
        st.success("Sin medicamentos por debajo del umbral de inventario.")
    else:
        def _badge(dias: float) -> str:
            color = STATUS["critical"] if dias < 2 else STATUS["warning"]
            etiqueta = "crítico" if dias < 2 else "alerta"
            return f'<span style="color:{color}; font-weight:600;">● {etiqueta}</span>'

        df_show = df_alertas.copy()
        df_show["estado"] = df_show["dias_inventario"].apply(_badge)
        st.write(
            df_show[["medicamento", "dias_inventario", "consumo_diario_prom", "estado"]].to_html(
                escape=False, index=False
            ),
            unsafe_allow_html=True,
        )

st.divider()

st.subheader("💬 Pregúntale al agente")
if "chat" not in st.session_state:
    st.session_state.chat = []

for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

pregunta = st.chat_input("Ej: ¿cuántas camas de UCI están ocupadas hoy?")
if pregunta:
    st.session_state.chat.append({"role": "user", "content": pregunta})
    with st.chat_message("user"):
        st.write(pregunta)
    with st.chat_message("assistant"):
        try:
            resp = requests.post(f"{API_URL}/ask", json={"question": pregunta}, timeout=60)
            resp.raise_for_status()
            respuesta = resp.json()["answer"]
        except requests.RequestException as exc:
            respuesta = f"No pude contactar al agente ({exc}). ¿Está corriendo `uvicorn app.api:app`?"
        st.write(respuesta)
        st.session_state.chat.append({"role": "assistant", "content": respuesta})
