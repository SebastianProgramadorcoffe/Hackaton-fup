"""Consultas SQL para el dashboard. Separadas de la presentación (Streamlit)
para poder probarlas sin levantar la UI. Todas usan la conexión de solo
lectura de app.db; ninguna acepta SQL externo (a diferencia del agente, aquí
las consultas son fijas, escritas por nosotros).
"""
from __future__ import annotations

import pandas as pd

from app.db import read_only_connection

FECHA_CORTE_SQL = "(SELECT valor FROM meta WHERE clave='fecha_corte_demo')"
UMBRAL_INVENTARIO_SQL = "(SELECT CAST(valor AS REAL) FROM meta WHERE clave='umbral_dias_inventario_bajo')"


def _query(sql: str, params: tuple = ()) -> pd.DataFrame:
    with read_only_connection() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def fecha_corte_demo() -> str:
    with read_only_connection() as conn:
        return conn.execute("SELECT valor FROM meta WHERE clave='fecha_corte_demo'").fetchone()[0]


def ocupacion_por_servicio() -> pd.DataFrame:
    """Camas ocupadas hoy y capacidad estimada, por NombreGrupoCama."""
    sql = f"""
        SELECT cc.nombre_grupo_cama AS servicio,
               COALESCE(o.ocupadas, 0) AS ocupadas,
               cc.capacidad_estimada AS capacidad,
               ROUND(100.0 * COALESCE(o.ocupadas, 0) / cc.capacidad_estimada, 1) AS pct_ocupacion
        FROM capacidad_camas cc
        LEFT JOIN (
            SELECT NombreGrupoCama, COUNT(*) AS ocupadas
            FROM ingresos
            WHERE date(FechaHospitalizacion) = {FECHA_CORTE_SQL}
            GROUP BY NombreGrupoCama
        ) o ON o.NombreGrupoCama = cc.nombre_grupo_cama
        ORDER BY pct_ocupacion DESC
    """
    return _query(sql)


def espera_promedio_por_triage(dias: int = 7) -> pd.DataFrame:
    """Minutos promedio entre FechaIngreso y FechaAtencion en Urgencias, por nivel de triage.

    triage.ClasificacionTriage NO es una categoría limpia: mezcla ubicación,
    tipo de consulta y color (p. ej. "PEDIATRIA URGENCIAS CONSULTORIO UNO-
    TRIAGE 2 (AMARILLO)"). El nivel (1-4) siempre aparece como "TRIAGE <n>",
    así que se extrae con substr/instr en vez de agrupar por el texto crudo
    (que da ~18 categorías inservibles para una gráfica o una respuesta).
    """
    sql = f"""
        SELECT CAST(substr(t.ClasificacionTriage, instr(t.ClasificacionTriage, 'TRIAGE') + 7, 1) AS INTEGER) AS nivel_triage,
               ROUND(AVG((julianday(a.FechaAtencion) - julianday(i.FechaIngreso)) * 24 * 60), 1) AS minutos_espera_prom,
               COUNT(*) AS n_casos
        FROM ingresos i
        JOIN atencion a ON a.OidIngreso = i.OidIngreso
        JOIN triage t ON t.OidTriage = i.OidTriageA
        WHERE i.NombreGrupoCama = 'URGENCIAS'
          AND t.ClasificacionTriage LIKE '%TRIAGE%'
          AND date(i.FechaIngreso) >= date({FECHA_CORTE_SQL}, ?)
        GROUP BY nivel_triage
        ORDER BY nivel_triage
    """
    return _query(sql, (f"-{dias} days",))


def cirugias_programadas_por_semana(semanas: int = 12) -> pd.DataFrame:
    """Conteo semanal de cirugías programadas (proxy de uso de quirófanos)."""
    sql = f"""
        SELECT strftime('%Y-%W', i.FechaIngreso) AS semana,
               COUNT(*) AS n_cirugias
        FROM programacion_cirugia pc
        JOIN ingresos i ON i.OidIngreso = pc.OidIngreso
        WHERE date(i.FechaIngreso) >= date({FECHA_CORTE_SQL}, ?)
        GROUP BY semana
        ORDER BY semana
    """
    return _query(sql, (f"-{semanas * 7} days",))


def medicamentos_bajo_inventario(umbral_dias: float | None = None) -> pd.DataFrame:
    """Medicamentos con menos de `umbral_dias` de autonomía (stock SIMULADO, ver DECISIONS.md)."""
    umbral_clause = "?" if umbral_dias is not None else UMBRAL_INVENTARIO_SQL
    sql = f"""
        SELECT nombre_servicio AS medicamento,
               stock_actual,
               ROUND(consumo_promedio_diario, 2) AS consumo_diario_prom,
               ROUND(stock_actual / NULLIF(consumo_promedio_diario, 0), 1) AS dias_inventario
        FROM stock_medicamentos
        WHERE consumo_promedio_diario > 0
          AND stock_actual / consumo_promedio_diario < {umbral_clause}
        ORDER BY dias_inventario ASC
        LIMIT 30
    """
    params = (umbral_dias,) if umbral_dias is not None else ()
    return _query(sql, params)


def resumen_kpis() -> dict:
    ocup = ocupacion_por_servicio()
    uci = ocup.loc[ocup["servicio"] == "UNIDAD DE CUIDADO INTENSIVO"]
    espera = espera_promedio_por_triage()
    bajo_inventario = medicamentos_bajo_inventario()
    return {
        "camas_uci_ocupadas": int(uci["ocupadas"].iloc[0]) if not uci.empty else 0,
        "camas_uci_capacidad": int(uci["capacidad"].iloc[0]) if not uci.empty else 0,
        "espera_prom_urgencias_min": float(espera["minutos_espera_prom"].mean()) if not espera.empty else None,
        "medicamentos_en_alerta": len(bajo_inventario),
        "servicio_mas_ocupado_pct": ocup.iloc[0].to_dict() if not ocup.empty else None,
    }
