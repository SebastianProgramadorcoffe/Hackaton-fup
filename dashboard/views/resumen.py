"""Página: Resumen — KPIs, gráficas y alertas activas."""
from __future__ import annotations

import plotly.express as px
import plotly.graph_objects as go
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
from dashboard.theme import SERIE_1, SERIE_2, STATUS, apply_chart_theme


def render() -> None:
    st.markdown('<div class="marca-eyebrow">Hospital Susana López de Valencia</div>', unsafe_allow_html=True)
    st.title("🏥 Panel de operación hospitalaria")
    st.markdown(
        f'<span class="badge">Hoy · {fecha_corte_demo()}</span>'
        '<span class="badge">Prototipo de hackatón</span>',
        unsafe_allow_html=True,
    )
    st.write("")

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

    kpis = resumen_kpis()
    # Etiquetas cortas a propósito: con la barra de navegación el área
    # principal es más angosta, y Streamlit trunca la etiqueta con "..."
    # sin exponer un selector CSS estable para desactivarlo. El detalle
    # (rango, umbral, servicio) va en el tooltip de ayuda, no en el título.
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Camas UCI", f"{kpis['camas_uci_ocupadas']} / {kpis['camas_uci_capacidad']}", help="Ocupadas / capacidad estimada, hoy")
    espera = kpis["espera_prom_urgencias_min"]
    c2.metric("Espera urgencias", f"{espera:.0f} min" if espera is not None else "s/d", help="Promedio de los últimos 7 días")
    c3.metric("Medicamentos", kpis["medicamentos_en_alerta"], help="Con menos del umbral configurado de días de inventario (simulado)")
    top = kpis["servicio_mas_ocupado_pct"]
    c4.metric(
        "Servicio pico",
        f"{top['pct_ocupacion']}%" if top else "s/d",
        help=f"{top['servicio'].title()} — % de ocupación actual, no es una tendencia." if top else "",
    )

    st.write("")

    col_izq, col_der = st.columns(2)

    with col_izq:
        st.subheader("Ocupación de camas por servicio")
        df_ocup = ocupacion_por_servicio()
        fig = go.Figure()
        fig.add_bar(name="Ocupadas", x=df_ocup["servicio"], y=df_ocup["ocupadas"], marker_color=SERIE_1)
        fig.add_bar(name="Capacidad estimada", x=df_ocup["servicio"], y=df_ocup["capacidad"], marker_color=SERIE_2)
        fig.update_layout(barmode="group", xaxis_tickangle=-30)
        st.plotly_chart(apply_chart_theme(fig), width="stretch")

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
            st.plotly_chart(apply_chart_theme(fig), width="stretch")

    col_izq2, col_der2 = st.columns(2)

    with col_izq2:
        st.subheader("Uso de quirófanos")
        df_cir = cirugias_programadas_por_semana(semanas=12)
        if df_cir.empty:
            st.info("Sin cirugías programadas en el rango.")
        else:
            fig = go.Figure()
            fig.add_scatter(x=df_cir["semana"], y=df_cir["n_cirugias"], mode="lines+markers", line=dict(color=SERIE_1, width=2))
            st.plotly_chart(apply_chart_theme(fig), width="stretch")
            st.caption(
                "Cubre solo el ~25% de programacion_cirugia que sí enlaza con un ingreso "
                "(esa tabla no trae fecha propia — ver docs/modelo-relacional.md)."
            )

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
