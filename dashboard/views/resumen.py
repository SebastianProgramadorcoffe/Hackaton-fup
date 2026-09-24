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
    umbrales_ocupacion,
)
from dashboard.theme import SERIE_1, SERIE_2, STATUS, apply_chart_theme

CHART_HEIGHT = 320


def _kpi_status(pct: float | None, alerta: float, critico: float) -> tuple[str, str] | None:
    """(color, etiqueta) para un % de ocupación, o None si no aplica."""
    if pct is None:
        return None
    if pct >= critico:
        return STATUS["critical"], "Crítico"
    if pct >= alerta:
        return STATUS["warning"], "Atención"
    return STATUS["good"], "Normal"


def _status_caption(status: tuple[str, str] | None) -> None:
    if status is None:
        return
    color, etiqueta = status
    st.markdown(
        f'<div class="kpi-status" style="color:{color};">● {etiqueta}</div>',
        unsafe_allow_html=True,
    )


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

    with st.container(border=True):
        st.subheader("Alertas activas")
        if not todas_las_alertas:
            st.success("Sin alertas de camas ni de inventario en este momento.")
        else:
            st.markdown(
                f'<span class="kpi-status" style="color:{STATUS["critical"]};">● {n_criticas} crítica(s)</span>'
                f'&nbsp;&nbsp;<span class="kpi-status" style="color:{STATUS["warning"]};">● {n_atencion} de atención</span>',
                unsafe_allow_html=True,
            )
            st.caption("Ordenadas por severidad dentro de cada grupo — las críticas requieren acción hoy mismo.")
            st.write("")

            # Agrupadas por tipo (en vez de una lista mezclada): así "camas"
            # y "medicamentos" no compiten por los primeros puestos del top,
            # y cada grupo se lee con su propio contexto.
            camas = [a for a in todas_las_alertas if a.tipo == "ocupacion_camas"]
            meds = [a for a in todas_las_alertas if a.tipo == "inventario_medicamento"]

            if camas:
                st.markdown("**🛏️ Ocupación de camas**")
                for a in camas[:3]:
                    texto = f"**{a.servicio_o_medicamento.title()}** — {a.detalle}"
                    (st.error if a.nivel == "critical" else st.warning)(texto)
                if len(camas) > 3:
                    st.caption(f"+ {len(camas) - 3} servicio(s) más con ocupación por encima del umbral.")

            if meds:
                st.markdown("**💊 Inventario de medicamentos** · stock simulado, consumo real")
                for a in meds[:3]:
                    texto = f"**{a.servicio_o_medicamento.title()}** — {a.detalle}"
                    (st.error if a.nivel == "critical" else st.warning)(texto)
                if len(meds) > 3:
                    st.caption(f"+ {len(meds) - 3} medicamento(s) más — ver tabla de inventario más abajo.")

    st.write("")

    kpis = resumen_kpis()
    umbral_alerta_pct, umbral_critico_pct = umbrales_ocupacion()

    with st.container(border=True):
        st.subheader("Indicadores clave")
        # Etiquetas cortas a propósito: con la barra de navegación el área
        # principal es más angosta, y Streamlit trunca la etiqueta con "..."
        # sin exponer un selector CSS estable para desactivarlo. El detalle
        # (rango, umbral, servicio) va en el tooltip de ayuda, no en el título.
        c1, c2, c3, c4 = st.columns(4)

        with c1:
            capacidad = kpis["camas_uci_capacidad"]
            pct_uci = (100.0 * kpis["camas_uci_ocupadas"] / capacidad) if capacidad else None
            st.metric("Camas UCI", f"{kpis['camas_uci_ocupadas']} / {capacidad}", help="Ocupadas / capacidad estimada, hoy")
            _status_caption(_kpi_status(pct_uci, umbral_alerta_pct, umbral_critico_pct))

        with c2:
            espera = kpis["espera_prom_urgencias_min"]
            c2.metric("Espera urgencias", f"{espera:.0f} min" if espera is not None else "s/d", help="Promedio de los últimos 7 días")

        with c3:
            n_meds = kpis["medicamentos_en_alerta"]
            c3.metric("Medicamentos", n_meds, help="Con menos del umbral configurado de días de inventario (simulado)")
            if n_meds:
                _status_caption((STATUS["warning"], "Revisar inventario"))

        with c4:
            top = kpis["servicio_mas_ocupado_pct"]
            c4.metric(
                "Servicio pico",
                f"{top['pct_ocupacion']}%" if top else "s/d",
                help=f"{top['servicio'].title()} — % de ocupación actual, no es una tendencia." if top else "",
            )
            if top:
                _status_caption(_kpi_status(top["pct_ocupacion"], umbral_alerta_pct, umbral_critico_pct))

    st.write("")

    col_izq, col_der = st.columns(2)

    with col_izq:
        with st.container(border=True):
            st.subheader("Ocupación de camas por servicio")
            df_ocup = ocupacion_por_servicio()
            fig = go.Figure()
            fig.add_bar(
                name="Ocupadas", x=df_ocup["servicio"], y=df_ocup["ocupadas"], marker_color=SERIE_1,
                text=df_ocup["pct_ocupacion"].map(lambda v: f"{v:.0f}%"), textposition="outside",
                hovertemplate="%{x}<br>Ocupadas: %{y}<br>%{text} de la capacidad<extra></extra>",
            )
            fig.add_bar(
                name="Capacidad estimada", x=df_ocup["servicio"], y=df_ocup["capacidad"], marker_color=SERIE_2,
                hovertemplate="%{x}<br>Capacidad: %{y}<extra></extra>",
            )
            fig.update_layout(barmode="group", xaxis_tickangle=-30, height=CHART_HEIGHT)
            st.plotly_chart(apply_chart_theme(fig), width="stretch")
            with st.expander("Ver datos"):
                st.dataframe(
                    df_ocup.rename(columns={
                        "servicio": "Servicio", "ocupadas": "Ocupadas",
                        "capacidad": "Capacidad", "pct_ocupacion": "% ocupación",
                    }),
                    hide_index=True, width="stretch",
                )

    with col_der:
        with st.container(border=True):
            st.subheader("Espera promedio en urgencias")
            df_espera = espera_promedio_por_triage(dias=7)
            if df_espera.empty:
                st.info("Sin datos de urgencias en los últimos 7 días.")
            else:
                df_espera["triage"] = "Triage " + df_espera["nivel_triage"].astype(str)
                fig = go.Figure()
                fig.add_bar(
                    x=df_espera["triage"], y=df_espera["minutos_espera_prom"], marker_color=SERIE_1,
                    text=df_espera["minutos_espera_prom"], texttemplate="%{text:.0f} min", textposition="outside",
                    hovertemplate="%{x}<br>%{y:.1f} min promedio<br>%{customdata} casos<extra></extra>",
                    customdata=df_espera["n_casos"],
                )
                fig.update_layout(yaxis_title="Minutos", height=CHART_HEIGHT)
                st.plotly_chart(apply_chart_theme(fig), width="stretch")
                with st.expander("Ver datos"):
                    st.dataframe(
                        df_espera.rename(columns={
                            "triage": "Triage", "minutos_espera_prom": "Min. promedio", "n_casos": "Casos",
                        })[["Triage", "Min. promedio", "Casos"]],
                        hide_index=True, width="stretch",
                    )

    col_izq2, col_der2 = st.columns(2)

    with col_izq2:
        with st.container(border=True):
            st.subheader("Uso de quirófanos")
            df_cir = cirugias_programadas_por_semana(semanas=12)
            if df_cir.empty:
                st.info("Sin cirugías programadas en el rango.")
            else:
                fig = go.Figure()
                fig.add_scatter(
                    x=df_cir["semana"], y=df_cir["n_cirugias"], mode="lines+markers",
                    line=dict(color=SERIE_1, width=2), marker=dict(size=8),
                    hovertemplate="Semana %{x}<br>%{y} cirugías<extra></extra>",
                )
                fig.update_layout(height=CHART_HEIGHT)
                st.plotly_chart(apply_chart_theme(fig), width="stretch")
                st.caption(
                    "Cubre solo el ~25% de programacion_cirugia que sí enlaza con un ingreso "
                    "(esa tabla no trae fecha propia — ver docs/modelo-relacional.md)."
                )

    with col_der2:
        with st.container(border=True):
            st.subheader("Inventario de medicamentos")
            df_alertas = medicamentos_bajo_inventario()
            if df_alertas.empty:
                st.success("Sin medicamentos por debajo del umbral de inventario.")
            else:
                df_show = df_alertas.rename(columns={
                    "medicamento": "Medicamento",
                    "dias_inventario": "Días de inventario",
                    "consumo_diario_prom": "Consumo/día",
                }).copy()
                df_show["Estado"] = df_show["Días de inventario"].apply(
                    lambda d: "🔴 Crítico" if d < 2 else "🟡 Alerta"
                )

                def _color_dias(val: float) -> str:
                    color = STATUS["critical"] if val < 2 else STATUS["warning"]
                    return f"color: {color}; font-weight: 600;"

                def _color_estado(val: str) -> str:
                    color = STATUS["critical"] if "Crítico" in val else STATUS["warning"]
                    return f"color: {color}; font-weight: 600;"

                cols = ["Medicamento", "Días de inventario", "Consumo/día", "Estado"]
                styler = (
                    df_show[cols].head(10).style
                    .map(_color_dias, subset=["Días de inventario"])
                    .map(_color_estado, subset=["Estado"])
                    .format({"Días de inventario": "{:.1f}", "Consumo/día": "{:.2f}"})
                )
                st.dataframe(styler, hide_index=True, width="stretch")
                if len(df_show) > 10:
                    st.caption(f"+ {len(df_show) - 10} medicamento(s) más por debajo del umbral.")
                st.caption("Stock simulado para este prototipo — el consumo/día sí es real. Ver DECISIONS.md.")

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
