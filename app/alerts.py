"""Lógica de alertas: saturación de camas y desabastecimiento de medicamentos.

Centralizada aquí (no en el dashboard ni duplicada en el agente) para que la
API, el dashboard y scripts/check_alerts.py usen exactamente los mismos
umbrales y la misma clasificación de severidad.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from app.db import read_only_connection

FECHA_CORTE_SQL = "(SELECT valor FROM meta WHERE clave='fecha_corte_demo')"


@dataclass
class Alerta:
    tipo: str  # "ocupacion_camas" | "inventario_medicamento"
    nivel: str  # "warning" | "critical"
    servicio_o_medicamento: str
    detalle: str
    valor: float


def _meta_float(conn, clave: str) -> float:
    row = conn.execute("SELECT valor FROM meta WHERE clave = ?", (clave,)).fetchone()
    if row is None:
        raise KeyError(f"No existe la clave de configuración '{clave}' en meta. Ejecuta build_db.py de nuevo.")
    return float(row[0])


def alertas_ocupacion_camas() -> list[Alerta]:
    with read_only_connection() as conn:
        umbral_warning = _meta_float(conn, "umbral_ocupacion_alerta_pct")
        umbral_critical = _meta_float(conn, "umbral_ocupacion_critica_pct")
        rows = conn.execute(
            f"""
            SELECT cc.nombre_grupo_cama,
                   COALESCE(o.ocupadas, 0) AS ocupadas,
                   cc.capacidad_estimada,
                   100.0 * COALESCE(o.ocupadas, 0) / cc.capacidad_estimada AS pct
            FROM capacidad_camas cc
            LEFT JOIN (
                SELECT NombreGrupoCama, COUNT(*) AS ocupadas
                FROM ingresos
                WHERE date(FechaHospitalizacion) = {FECHA_CORTE_SQL}
                GROUP BY NombreGrupoCama
            ) o ON o.NombreGrupoCama = cc.nombre_grupo_cama
            WHERE cc.capacidad_estimada > 0
            """
        ).fetchall()

    alertas = []
    for servicio, ocupadas, capacidad, pct in rows:
        if pct >= umbral_critical:
            nivel = "critical"
            umbral_cruzado = umbral_critical
            etiqueta_umbral = "crítico"
        elif pct >= umbral_warning:
            nivel = "warning"
            umbral_cruzado = umbral_warning
            etiqueta_umbral = "de atención"
        else:
            continue
        alertas.append(
            Alerta(
                tipo="ocupacion_camas",
                nivel=nivel,
                servicio_o_medicamento=servicio,
                detalle=(
                    f"{ocupadas}/{capacidad} camas ocupadas ({pct:.0f}%) — supera el umbral "
                    f"{etiqueta_umbral} de {umbral_cruzado:.0f}%. Riesgo de no tener cama disponible "
                    "para el próximo ingreso de este servicio."
                ),
                valor=round(pct, 1),
            )
        )
    return sorted(alertas, key=lambda a: a.valor, reverse=True)


def alertas_inventario_medicamentos(umbral_critico_dias: float = 2.0) -> list[Alerta]:
    with read_only_connection() as conn:
        umbral_bajo = _meta_float(conn, "umbral_dias_inventario_bajo")
        rows = conn.execute(
            """
            SELECT nombre_servicio, stock_actual, consumo_promedio_diario,
                   stock_actual / consumo_promedio_diario AS dias
            FROM stock_medicamentos
            WHERE consumo_promedio_diario > 0 AND stock_actual / consumo_promedio_diario < ?
            """,
            (umbral_bajo,),
        ).fetchall()

    alertas = []
    for nombre, stock, consumo, dias in rows:
        nivel = "critical" if dias < umbral_critico_dias else "warning"
        urgencia = "se agota en menos de 2 días" if nivel == "critical" else f"por debajo del umbral de {umbral_bajo:.0f} días"
        alertas.append(
            Alerta(
                tipo="inventario_medicamento",
                nivel=nivel,
                servicio_o_medicamento=nombre,
                detalle=(
                    f"{dias:.1f} días de inventario restante ({urgencia}). "
                    f"Consumo real de {consumo:.1f} unidades/día, stock inicial SIMULADO ({stock:.0f} unidades) "
                    "para este prototipo."
                ),
                valor=round(dias, 1),
            )
        )
    return sorted(alertas, key=lambda a: a.valor)


def alertas_activas() -> list[Alerta]:
    camas = alertas_ocupacion_camas()
    medicamentos = alertas_inventario_medicamentos()
    orden_nivel = {"critical": 0, "warning": 1}
    return sorted(camas + medicamentos, key=lambda a: orden_nivel[a.nivel])


def alertas_activas_dict() -> list[dict]:
    return [asdict(a) for a in alertas_activas()]
