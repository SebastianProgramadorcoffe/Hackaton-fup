"""Dashboard del HIS — hackaton-fup.

Ejecutar (con la API corriendo aparte en :8000):
    streamlit run dashboard/streamlit_app.py

Las gráficas leen directo de SQLite (rápido, sin costo de API). El chat es
el único punto que llama al agente NL2SQL vía la API.

Diseño: tema oscuro + un único acento dorado (ver .streamlit/config.toml).
Los colores de las gráficas y de las alertas usan la variante de superficie
oscura de la paleta validada del skill dataviz — nunca colores inventados
para los datos, el acento de lujo es solo para el "chrome" de la interfaz
(títulos, insignias, bordes). Detalles metodológicos (stock simulado, fecha
de corte, etc.) se agrupan en una nota al pie en vez de repetirse como
subtítulos sueltos, para que la vista principal quede limpia.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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

# ---------------------------------------------------------------------------
# Paleta — variante de superficie OSCURA de la paleta validada (dataviz).
# Los hex de datos (SERIE_1/2, STATUS) son los mismos del modo claro que ya
# se usaban antes, sustituidos por sus pasos "Dark" documentados; no son
# elegidos a ojo. El dorado es el único acento decorativo, ajeno al dato.
# ---------------------------------------------------------------------------
ACCENT = "#c9a15e"           # acento de lujo — solo chrome, nunca dato
SERIE_1 = "#3987e5"          # azul (dark) — serie principal
SERIE_2 = "#d95926"          # naranja (dark) — segunda serie categórica
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
SURFACE = "#1a1a19"          # superficie de gráfica (dark)
PAGE = "#0d0d0d"             # plano de página (dark)
INK_PRIMARY = "#ffffff"
INK_SECONDARY = "#c3c2b7"
INK_MUTED = "#898781"
GRIDLINE = "#2c2c2a"

API_URL = "http://localhost:8000"

st.set_page_config(page_title="HIS · hackaton-fup", layout="wide", page_icon="🏥")

# ---------------------------------------------------------------------------
# CSS: tipografía con carácter, quitar el "chrome" de Streamlit que el
# usuario final no necesita ver (menú, footer "Made with Streamlit", barra
# de decoración), y afinar tarjetas/números/badges.
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {{
        font-family: 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
    }}

    /* Quitar chrome que no aporta a quien usa el dashboard (no al desarrollo) */
    #MainMenu, footer, [data-testid="stDecoration"], [data-testid="stToolbar"] {{
        visibility: hidden; height: 0;
    }}

    /* Tipografía de las cifras clave: alineadas y con carácter */
    [data-testid="stMetricValue"] {{
        font-variant-numeric: tabular-nums;
        font-weight: 700;
        color: {INK_PRIMARY};
    }}
    [data-testid="stMetricLabel"] {{
        color: {INK_MUTED};
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-size: 0.72rem;
    }}
    [data-testid="stMetric"] {{
        background: {SURFACE};
        border: 1px solid rgba(201, 161, 94, 0.18);
        border-radius: 14px;
        padding: 1rem 1.1rem 0.8rem;
    }}

    h1, h2, h3 {{ letter-spacing: -0.01em; }}
    h1 {{ font-weight: 700; }}

    .marca-eyebrow {{
        text-transform: uppercase;
        letter-spacing: 0.18em;
        font-size: 0.72rem;
        color: {ACCENT};
        font-weight: 600;
        margin-bottom: 0.2rem;
    }}
    .badge {{
        display: inline-block;
        border: 1px solid rgba(201, 161, 94, 0.35);
        color: {ACCENT};
        border-radius: 999px;
        padding: 0.15rem 0.7rem;
        font-size: 0.75rem;
        font-weight: 500;
        margin-right: 0.4rem;
    }}

    .stButton>button, .stChatInput textarea {{
        border-radius: 10px !important;
        transition: border-color 180ms ease, box-shadow 180ms ease;
    }}
    .stButton>button:hover {{
        border-color: {ACCENT} !important;
        color: {ACCENT} !important;
    }}

    div[data-testid="stExpander"] {{
        border: 1px solid rgba(201, 161, 94, 0.18);
        border-radius: 12px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)


def _apply_chart_theme(fig: go.Figure) -> go.Figure:
    fig.update_layout(
        plot_bgcolor=SURFACE,
        paper_bgcolor=SURFACE,
        font=dict(color=INK_SECONDARY, family="Plus Jakarta Sans, system-ui, sans-serif"),
        margin=dict(l=10, r=10, t=40, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(color=INK_SECONDARY)),
    )
    fig.update_xaxes(gridcolor=GRIDLINE, zeroline=False, color=INK_MUTED)
    fig.update_yaxes(gridcolor=GRIDLINE, zeroline=False, color=INK_MUTED)
    return fig


# ---------------------------------------------------------------------------
# Encabezado
# ---------------------------------------------------------------------------
st.markdown('<div class="marca-eyebrow">Hospital Susana López de Valencia</div>', unsafe_allow_html=True)
st.title("🏥 Panel de operación hospitalaria")
st.markdown(
    f'<span class="badge">Hoy · {fecha_corte_demo()}</span>'
    '<span class="badge">Prototipo de hackatón</span>',
    unsafe_allow_html=True,
)
st.write("")

# ---------------------------------------------------------------------------
# Alertas activas — resumen conciso; el detalle completo va en las tablas
# de más abajo, y la nota operativa (cron/webhook) va en el pie de página.
# ---------------------------------------------------------------------------
todas_las_alertas = alertas_activas()
n_criticas = sum(1 for a in todas_las_alertas if a.nivel == "critical")
n_atencion = len(todas_las_alertas) - n_criticas

st.subheader("Alertas activas")
if not todas_las_alertas:
    st.success("Sin alertas de camas ni de inventario en este momento.")
else:
    st.markdown(f"**{n_criticas}** crítica(s) · **{n_atencion}** de atención")
    for a in todas_las_alertas[:5]:
        texto = f"**{a.servicio_o_medicamento.title()}** — {a.detalle}"
        (st.error if a.nivel == "critical" else st.warning)(texto)
    if len(todas_las_alertas) > 5:
        st.caption(f"+ {len(todas_las_alertas) - 5} alerta(s) más en el detalle de inventario, más abajo.")

st.divider()

# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
kpis = resumen_kpis()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Camas UCI ocupadas", f"{kpis['camas_uci_ocupadas']} / {kpis['camas_uci_capacidad']}")
espera = kpis["espera_prom_urgencias_min"]
c2.metric("Espera prom. urgencias", f"{espera:.0f} min" if espera is not None else "s/d", help="Últimos 7 días")
c3.metric("Medicamentos en alerta", kpis["medicamentos_en_alerta"], help="Menos del umbral configurado de días de inventario")
top = kpis["servicio_mas_ocupado_pct"]
c4.metric(
    f"Más ocupado: {top['servicio'].title()}" if top else "Servicio más ocupado",
    f"{top['pct_ocupacion']}%" if top else "s/d",
    help="% de ocupación actual del servicio más lleno (no es una tendencia).",
)

st.write("")

# ---------------------------------------------------------------------------
# Gráficas
# ---------------------------------------------------------------------------
col_izq, col_der = st.columns(2)

with col_izq:
    st.subheader("Ocupación de camas por servicio")
    df_ocup = ocupacion_por_servicio()
    fig = go.Figure()
    fig.add_bar(name="Ocupadas", x=df_ocup["servicio"], y=df_ocup["ocupadas"], marker_color=SERIE_1)
    fig.add_bar(name="Capacidad estimada", x=df_ocup["servicio"], y=df_ocup["capacidad"], marker_color=SERIE_2)
    fig.update_layout(barmode="group", xaxis_tickangle=-30)
    st.plotly_chart(_apply_chart_theme(fig), width="stretch")

with col_der:
    st.subheader("Espera promedio en urgencias")
    df_espera = espera_promedio_por_triage(dias=7)
    if df_espera.empty:
        st.info("Sin datos de urgencias en los últimos 7 días.")
    else:
        df_espera["triage"] = "Triage " + df_espera["nivel_triage"].astype(str)
        fig = go.Figure()
        fig.add_bar(x=df_espera["triage"], y=df_espera["minutos_espera_prom"], marker_color=SERIE_1)
        fig.update_layout(yaxis_title="Minutos")
        st.plotly_chart(_apply_chart_theme(fig), width="stretch")

col_izq2, col_der2 = st.columns(2)

with col_izq2:
    st.subheader("Uso de quirófanos")
    df_cir = cirugias_programadas_por_semana(semanas=12)
    if df_cir.empty:
        st.info("Sin cirugías programadas en el rango.")
    else:
        fig = go.Figure()
        fig.add_scatter(x=df_cir["semana"], y=df_cir["n_cirugias"], mode="lines+markers", line=dict(color=SERIE_1, width=2))
        st.plotly_chart(_apply_chart_theme(fig), width="stretch")

with col_der2:
    st.subheader("Inventario de medicamentos")
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
        df_show = df_show.rename(
            columns={"medicamento": "Medicamento", "dias_inventario": "Días", "consumo_diario_prom": "Consumo/día", "estado": "Estado"}
        )
        st.write(
            df_show[["Medicamento", "Días", "Consumo/día", "Estado"]].head(10).to_html(escape=False, index=False),
            unsafe_allow_html=True,
        )

st.divider()

# ---------------------------------------------------------------------------
# Chat con el agente
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Notas metodológicas — agrupadas y colapsadas: transparentes para quien
# las busca (equipo, jurado), fuera del camino para quien solo opera.
# ---------------------------------------------------------------------------
with st.expander("ℹ️ Notas del prototipo"):
    st.markdown(
        f"""
- **"Hoy" = {fecha_corte_demo()}**: el dataset es histórico y fijo (no se actualiza en vivo).
- **Capacidad de camas** = camas distintas observadas en el histórico, no la capacidad física real del hospital.
- **Stock de medicamentos = simulado** para este prototipo (el consumo diario sí es real). Ver `DECISIONS.md`.
- **Notificación automática**: `scripts/check_alerts.py` reconsulta estos mismos umbrales y puede programarse
  (cron / Programador de tareas de Windows) para avisar por webhook — ver `README.md`.
        """
    )
