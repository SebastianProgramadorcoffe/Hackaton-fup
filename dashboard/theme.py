"""Tema compartido por todas las páginas del dashboard: paleta, CSS y helpers.

Un solo lugar para que /resumen y /agente (y cualquier página futura) se vean
consistentes. Paleta: superficie oscura + un único acento dorado — ver
DECISIONS.md/README para el porqué. Los colores de gráficas y alertas son la
variante de superficie oscura de la paleta ya validada del skill dataviz;
el dorado es puramente decorativo (chrome), nunca dato.
"""
from __future__ import annotations

import os

import plotly.graph_objects as go
import streamlit as st

ACCENT = "#c9a15e"           # acento de lujo — solo chrome, nunca dato
ACCENT_SOFT = "rgba(201, 161, 94, 0.18)"
SERIE_1 = "#3987e5"          # azul (dark) — serie principal, paleta dataviz
SERIE_2 = "#d95926"          # naranja (dark) — segunda serie categórica
STATUS = {"good": "#0ca30c", "warning": "#fab219", "serious": "#ec835a", "critical": "#d03b3b"}
SURFACE = "#1a1a19"          # superficie de gráfica (dark)
PAGE = "#0d0d0d"             # plano de página (dark)
INK_PRIMARY = "#ffffff"
INK_SECONDARY = "#c3c2b7"
INK_MUTED = "#898781"
GRIDLINE = "#2c2c2a"

API_URL = os.environ.get("API_URL", "http://localhost:8000")


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif;
        }}

        /* Quitar chrome de Streamlit que el usuario final no necesita ver */
        #MainMenu, footer, [data-testid="stDecoration"], [data-testid="stToolbar"] {{
            visibility: hidden; height: 0;
        }}

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
            border: 1px solid {ACCENT_SOFT};
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
            border: 1px solid {ACCENT_SOFT};
            border-radius: 12px;
        }}

        /* Marca en la barra lateral (arriba de la navegación) */
        .sidebar-brand {{
            display: flex; align-items: center; gap: 0.6rem;
            padding: 0.5rem 0.2rem 1rem;
            border-bottom: 1px solid {ACCENT_SOFT};
            margin-bottom: 0.6rem;
        }}
        .sidebar-brand-icon {{
            width: 34px; height: 34px; border-radius: 10px;
            background: radial-gradient(circle at 30% 30%, #e8c98a, {ACCENT} 60%, #7a5c2e 100%);
            display: flex; align-items: center; justify-content: center;
            font-size: 1.05rem; flex-shrink: 0;
        }}
        .sidebar-brand-text {{ line-height: 1.15; }}
        .sidebar-brand-title {{ font-weight: 700; font-size: 0.85rem; color: {INK_PRIMARY}; }}
        .sidebar-brand-sub {{ font-size: 0.7rem; color: {INK_MUTED}; }}

        /* Tarjeta "hero" del agente (estado vacío del chat) */
        .agent-hero {{
            text-align: center;
            padding: 2.5rem 1.5rem;
            border: 1px solid {ACCENT_SOFT};
            border-radius: 20px;
            background: {SURFACE};
            margin-bottom: 1.2rem;
        }}
        .agent-hero-avatar {{
            width: 64px; height: 64px; border-radius: 18px;
            margin: 0 auto 1rem;
            background: radial-gradient(circle at 30% 25%, #f0dcae, {ACCENT} 55%, #5f461f 100%);
            display: flex; align-items: center; justify-content: center;
            font-size: 1.8rem;
            box-shadow: 0 8px 24px -8px rgba(201, 161, 94, 0.45);
        }}
        .agent-hero-title {{ font-size: 1.3rem; font-weight: 700; color: {INK_PRIMARY}; margin-bottom: 0.5rem; }}
        .agent-hero-desc {{ font-size: 0.9rem; color: {INK_SECONDARY}; max-width: 460px; margin: 0 auto; line-height: 1.5; }}

        .trace-empty {{ color: {INK_MUTED}; font-size: 0.85rem; padding: 1rem 0; }}

        /* Tarjetas de sección (st.container(border=True)): separación clara
           entre bloques y superficie propia, en vez de que todo flote sobre
           el fondo de página. */
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            background: {SURFACE};
            border-color: {ACCENT_SOFT} !important;
            border-radius: 16px !important;
        }}

        /* Que tablas y dataframes nunca desborden la página: scroll propio
           en vez de romper el layout en pantallas angostas. */
        [data-testid="stDataFrame"], [data-testid="stTable"] {{
            max-width: 100%;
            overflow-x: auto;
        }}

        /* Franja de estado (KPI) bajo cada métrica */
        .kpi-status {{
            display: inline-flex; align-items: center; gap: 0.35rem;
            font-size: 0.75rem; font-weight: 600; margin-top: 0.3rem;
        }}

        /* --- Adaptabilidad: pantallas medianas (tablet / ventana angosta) ---
           Streamlit no reparte columnas en 2x2 por sí solo entre el ancho de
           escritorio y el punto de quiebre móvil: se van encogiendo hasta
           volverse ilegibles. Se fuerza wrap con un ancho mínimo por columna. */
        @media (max-width: 900px) {{
            [data-testid="stHorizontalBlock"] {{
                flex-wrap: wrap !important;
                row-gap: 0.9rem;
            }}
            [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
                min-width: 46% !important;
                flex: 1 1 46% !important;
            }}
        }}

        /* --- Adaptabilidad: móvil --- */
        @media (max-width: 560px) {{
            [data-testid="stHorizontalBlock"] > [data-testid="column"] {{
                min-width: 100% !important;
                flex: 1 1 100% !important;
            }}
            [data-testid="stMetric"] {{ padding: 0.75rem 0.85rem 0.6rem; }}
            [data-testid="stMetricValue"] {{ font-size: 1.4rem; }}
            .agent-hero {{ padding: 1.5rem 1rem; }}
            h1 {{ font-size: 1.5rem; }}
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def sidebar_brand() -> None:
    st.sidebar.markdown(
        """
        <div class="sidebar-brand">
          <div class="sidebar-brand-icon">🏥</div>
          <div class="sidebar-brand-text">
            <div class="sidebar-brand-title">Hospital Susana López</div>
            <div class="sidebar-brand-sub">HIS · Prototipo de hackatón</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def apply_chart_theme(fig: go.Figure) -> go.Figure:
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
