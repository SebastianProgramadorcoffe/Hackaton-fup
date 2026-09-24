"""Página: Agente — conversación con el asistente NL2SQL/RAG.

Inspirada en el patrón de agentes tipo "Beam" (tarjeta de bienvenida +
panel lateral con el detalle de la ejecución): a la derecha se expone el
razonamiento del agente (qué herramienta usó, qué SQL ejecutó, qué le
devolvió la base) en vez de ocultarlo — útil para que el equipo y el
jurado vean que las respuestas vienen de datos reales, no de texto
inventado.
"""
from __future__ import annotations

import requests
import streamlit as st

from dashboard.theme import API_URL

EJEMPLOS = [
    "¿Cuántas camas de UCI están ocupadas hoy?",
    "¿Qué medicamentos tienen menos de 5 días de inventario?",
    "¿Cuál es el tiempo de espera promedio en urgencias esta semana?",
    "¿Qué es un código CIE-10?",
]

TOOL_META = {
    "consultar_sql": ("🗄️", "Consulta a la base de datos"),
    "buscar_glosario": ("📖", "Búsqueda en el glosario / diccionario"),
}


def _render_hero() -> None:
    st.markdown(
        """
        <div class="agent-hero">
          <div class="agent-hero-avatar">🩺</div>
          <div class="agent-hero-title">Asistente del HIS</div>
          <div class="agent-hero-desc">
            Pregunta en lenguaje natural sobre ocupación de camas, tiempos de espera,
            inventario de medicamentos o conceptos como CIE-10 y CUPS. El agente
            traduce la pregunta a SQL sobre los datos reales del hospital, o busca
            en el glosario cuando la pregunta es conceptual.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns(len(EJEMPLOS))
    for col, ejemplo in zip(cols, EJEMPLOS):
        if col.button(ejemplo, key=f"ejemplo-{ejemplo}", width="stretch", help=ejemplo):
            st.session_state["pregunta_sugerida"] = ejemplo
            st.rerun()


def _preguntar(pregunta: str) -> None:
    st.session_state.chat.append({"role": "user", "content": pregunta})
    try:
        resp = requests.post(f"{API_URL}/ask", json={"question": pregunta}, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        respuesta = data["answer"]
        st.session_state.last_trace = {
            "pregunta": pregunta,
            "turns": data.get("turns"),
            "tool_calls": data.get("tool_calls", []),
            "elapsed_seconds": data.get("elapsed_seconds"),
            "llm_seconds": data.get("llm_seconds"),
            "tools_seconds": data.get("tools_seconds"),
        }
    except requests.RequestException as exc:
        respuesta = f"No pude contactar al agente ({exc}). ¿Está corriendo `uvicorn app.api:app`?"
        st.session_state.last_trace = {"pregunta": pregunta, "turns": None, "tool_calls": []}
    st.session_state.chat.append({"role": "assistant", "content": respuesta})


def _render_trace_panel() -> None:
    st.subheader("Detalle del agente")
    trace = st.session_state.get("last_trace")
    if not trace:
        st.markdown('<div class="trace-empty">Haz una pregunta para ver aquí qué herramientas usó el agente y qué consultó.</div>', unsafe_allow_html=True)
        return

    elapsed = trace.get("elapsed_seconds")
    if elapsed is not None:
        # st.metric trunca sin avisar en columnas angostas como esta (ver
        # DECISIONS.md / historial del proyecto) -- una línea de texto es
        # mas robusta aqui que 3 columnas de metric.
        st.markdown(
            f"⏱️ **{elapsed:.1f}s** en total &nbsp;·&nbsp; "
            f"{trace.get('llm_seconds', 0):.1f}s modelo &nbsp;·&nbsp; "
            f"{trace.get('tools_seconds', 0):.2f}s herramientas",
            help="El modelo (llamadas a la API de Claude) es casi siempre el cuello de botella, no el SQL.",
        )

    with st.expander("🗨️ Pregunta", expanded=True):
        st.write(trace["pregunta"])

    tool_calls = trace["tool_calls"]
    with st.expander(f"🛠️ Herramientas usadas ({len(tool_calls)})", expanded=True):
        if not tool_calls:
            st.caption("El agente respondió sin consultar ninguna herramienta.")
        for i, tc in enumerate(tool_calls, start=1):
            icon, label = TOOL_META.get(tc["tool"], ("⚙️", tc["tool"]))
            estado = "❌ error" if tc.get("error") else "✅ ok"
            duracion = tc.get("duration_ms")
            sufijo = f" · {duracion:.0f} ms" if duracion is not None else ""
            st.markdown(f"{icon} **{i}. {label}** — {estado}{sufijo}")

    sql_calls = [tc for tc in tool_calls if tc["tool"] == "consultar_sql"]
    if sql_calls:
        with st.expander(f"🗄️ SQL ejecutado ({len(sql_calls)})"):
            for tc in sql_calls:
                st.code(tc["input"].get("sql", ""), language="sql")

    glosario_calls = [tc for tc in tool_calls if tc["tool"] == "buscar_glosario"]
    if glosario_calls:
        with st.expander(f"📖 Búsquedas en el glosario ({len(glosario_calls)})"):
            for tc in glosario_calls:
                st.write(f"Consulta: *{tc['input'].get('consulta', '')}*")

    if tool_calls:
        with st.expander("📤 Resultado crudo de las herramientas"):
            for tc in tool_calls:
                st.json(tc["output"], expanded=False)

    if trace.get("turns"):
        st.caption(f"{trace['turns']} paso(s) de razonamiento.")


def render() -> None:
    if "chat" not in st.session_state:
        st.session_state.chat = []
    if "last_trace" not in st.session_state:
        st.session_state.last_trace = None

    col_chat, col_trace = st.columns([2.3, 1], gap="large")

    with col_chat:
        st.markdown('<div class="marca-eyebrow">Modo conversación</div>', unsafe_allow_html=True)
        st.title("💬 Agente HIS")

        if not st.session_state.chat:
            _render_hero()

        for msg in st.session_state.chat:
            with st.chat_message(msg["role"]):
                st.write(msg["content"])

    with col_trace:
        _render_trace_panel()

    pregunta_sugerida = st.session_state.pop("pregunta_sugerida", None)
    pregunta = st.chat_input("Escribe tu pregunta sobre el HIS...")
    pregunta_final = pregunta_sugerida or pregunta
    if pregunta_final:
        _preguntar(pregunta_final)
        st.rerun()
