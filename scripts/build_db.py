"""Carga los archivos crudos de Insumos Hackaton/Datos/*.txt a una base SQLite.

Uso:
    python scripts/build_db.py

Genera data/hackaton.db (ignorado por git). Es idempotente: si ya existe, la
reemplaza por completo para evitar datos duplicados o desincronizados.

Nota de negocio importante (ver memoria del proyecto / cuaderno NotebookLM
"hackaton-fup"): Ingresos.txt no trae una fecha de alta/egreso, solo
FechaIngreso (llegada) y FechaHospitalizacion (asignación de cama). Como el
set de datos es histórico y fijo (2026-05-01 a 2026-09-21), se define una
fecha de corte fija que representa "hoy" para las preguntas de la demo
("¿cuántas camas de UCI están ocupadas hoy?"). Se guarda en la tabla `meta`
para que el agente NL2SQL y el dashboard lean el mismo valor en vez de tener
la fecha repetida y hardcodeada en varios lugares.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "Insumos Hackaton" / "Datos"
DB_PATH = ROOT / "data" / "hackaton.db"

# Fecha de corte fija usada como "hoy" para las preguntas de la demo.
# Es la fecha máxima observada en Ingresos.FechaIngreso / FechaHospitalizacion.
FECHA_CORTE_DEMO = "2026-09-21"

# Semilla fija para que el stock simulado sea reproducible entre corridas.
STOCK_SEED = 42

# archivo -> (nombre de tabla, columnas de fecha a parsear)
TABLES: dict[str, tuple[str, list[str]]] = {
    "Paciente.txt": ("paciente", ["FechaNacimiento"]),
    "Ingresos.txt": ("ingresos", ["FechaIngreso", "FechaHospitalizacion"]),
    "Atencion.txt": ("atencion", ["FechaAtencion"]),
    "Triage.txt": ("triage", ["FechaTriage"]),
    "ProgramacionCirugia.txt": ("programacion_cirugia", []),
    "Servicios.txt": ("servicios", ["FechaPrestacion"]),
    "MedicamentoInsumo.txt": ("medicamento_insumo", ["FechaPrestacion"]),
}

# Índices por tabla: columnas usadas como llave foránea o filtro frecuente.
INDEXES: dict[str, list[str]] = {
    "ingresos": ["IdPaciente", "OidTriageA", "NombreGrupoCama", "FechaIngreso", "FechaHospitalizacion"],
    "atencion": ["OidIngreso"],
    "triage": ["IdPaciente2", "ClasificacionTriage"],
    "programacion_cirugia": ["IdPaciente", "OidIngreso", "CodigoServicio"],
    "servicios": ["OidIngreso", "CodigoServicio", "AreaServicio"],
    "medicamento_insumo": ["OidIngreso", "CodigoServicio", "AreaServicio"],
}


def load_table(conn: sqlite3.Connection, filename: str, table: str, date_cols: list[str]) -> int:
    path = RAW_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"No se encontró {path}")
    # quoting=QUOTE_NONE: los campos de texto libre (p. ej. MotivoConsulta en
    # Triage.txt) traen comillas dobles sueltas como texto literal, no como
    # delimitador CSV. Con el quoting por defecto, pandas las interpreta como
    # inicio de una celda citada y fusiona varias filas en una sola de forma
    # silenciosa (sin error), corrompiendo los datos. Se verificó fila por
    # fila con `wc -l` que este modo sí conserva el conteo real de registros.
    df = pd.read_csv(
        path, sep="|", dtype=str, encoding="utf-8",
        keep_default_na=False, na_values=[""], quoting=csv.QUOTE_NONE,
    )
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    with path.open("r", encoding="utf-8") as fh:
        expected_rows = sum(1 for _ in fh) - 1  # menos encabezado
    if len(df) != expected_rows:
        raise ValueError(
            f"{filename}: se leyeron {len(df)} filas pero el archivo tiene "
            f"{expected_rows} (según conteo de líneas). Posible corrupción "
            "al parsear — revisar antes de continuar."
        )

    df.to_sql(table, conn, if_exists="replace", index=False)
    return len(df)


def build_stock_simulado(conn: sqlite3.Connection) -> int:
    """Crea `stock_medicamentos`: NO son datos reales del HIS.

    No existe ninguna tabla de inventario/stock en el dataset entregado (solo
    hay consumo). Para poder responder la pregunta obligatoria de la demo
    ("medicamentos con menos de 5 días de inventario") se simula un stock
    inicial por medicamento a partir de su consumo diario promedio real,
    con una semilla fija (reproducible) para que el mismo medicamento no
    cambie de resultado entre corridas. Cada fila queda marcada `simulado=1`
    y el propio nombre de la tabla lo deja explícito para el dashboard, el
    agente y el jurado.
    """
    df = pd.read_sql(
        """
        SELECT CodigoServicio AS codigo_servicio,
               MAX(NombreServicio) AS nombre_servicio,
               SUM(CAST(Cantidad AS REAL)) AS total_consumido,
               MIN(FechaPrestacion) AS primera_fecha,
               MAX(FechaPrestacion) AS ultima_fecha
        FROM medicamento_insumo
        GROUP BY CodigoServicio
        """,
        conn,
    )
    dias = (pd.to_datetime(df["ultima_fecha"]) - pd.to_datetime(df["primera_fecha"])).dt.days.clip(lower=1) + 1
    df["consumo_promedio_diario"] = df["total_consumido"] / dias

    rng = np.random.default_rng(STOCK_SEED)
    # Autonomía simulada entre ~1 y ~20 días de consumo, a propósito por
    # debajo y por encima del umbral de la demo (5 días) para que la
    # consulta "menos de 5 días" tenga resultados no triviales.
    autonomia_dias = rng.uniform(1, 20, size=len(df))
    df["stock_actual"] = (df["consumo_promedio_diario"] * autonomia_dias).round().astype(int)
    df["simulado"] = 1

    out = df[["codigo_servicio", "nombre_servicio", "consumo_promedio_diario", "stock_actual", "simulado"]]
    out.to_sql("stock_medicamentos", conn, if_exists="replace", index=False)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_stock_medicamentos_codigo ON stock_medicamentos (codigo_servicio)")
    return len(out)


def build_capacidad_camas(conn: sqlite3.Connection) -> int:
    """Crea `capacidad_camas`: capacidad estimada (no simulada) por servicio.

    A diferencia del stock de medicamentos, esto SÍ se deriva de datos reales:
    cuenta camas (CodigoCama) distintas observadas en todo el histórico de
    Ingresos para cada NombreGrupoCama. Es una capacidad "instalada
    observada", no la capacidad física real del hospital (que no está en
    el dataset), y así se documenta.
    """
    conn.execute("DROP TABLE IF EXISTS capacidad_camas")
    conn.execute(
        """
        CREATE TABLE capacidad_camas AS
        SELECT NombreGrupoCama AS nombre_grupo_cama,
               COUNT(DISTINCT CodigoCama) AS capacidad_estimada
        FROM ingresos
        WHERE CodigoCama IS NOT NULL AND CodigoCama != ''
        GROUP BY NombreGrupoCama
        """
    )
    return conn.execute("SELECT COUNT(*) FROM capacidad_camas").fetchone()[0]


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    try:
        print(f"Construyendo {DB_PATH} ...")
        for filename, (table, date_cols) in TABLES.items():
            n = load_table(conn, filename, table, date_cols)
            print(f"  {table:<22} {n:>8} filas  <- {filename}")

        for table, cols in INDEXES.items():
            for col in cols:
                idx_name = f"idx_{table}_{col.lower()}"
                conn.execute(f'CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ("{col}")')

        n_stock = build_stock_simulado(conn)
        print(f"  {'stock_medicamentos':<22} {n_stock:>8} filas  <- SIMULADO (ver docstring build_stock_simulado)")
        n_cap = build_capacidad_camas(conn)
        print(f"  {'capacidad_camas':<22} {n_cap:>8} filas  <- estimado de Ingresos (camas distintas observadas)")

        conn.execute("DROP TABLE IF EXISTS meta")
        conn.execute("CREATE TABLE meta (clave TEXT PRIMARY KEY, valor TEXT)")
        conn.executemany(
            "INSERT INTO meta (clave, valor) VALUES (?, ?)",
            [
                ("fecha_corte_demo", FECHA_CORTE_DEMO),
                ("umbral_dias_inventario_bajo", "5"),
                ("stock_medicamentos_simulado", "true"),
            ],
        )
        conn.commit()
        print(f"\nListo. fecha_corte_demo = {FECHA_CORTE_DEMO}")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - script de línea de comandos
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
