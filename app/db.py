"""Acceso a la base de datos: siempre en modo solo-lectura.

La base la construye scripts/build_db.py; esta capa nunca escribe en ella.
Abrir la conexión con `mode=ro` en la URI es una segunda barrera (además de
sql_guard.py) contra que una consulta generada por el modelo modifique datos:
incluso si sql_guard tuviera un hueco, SQLite rechaza cualquier escritura a
nivel de sistema de archivos sobre esta conexión.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.config import DB_PATH


def _check_db_exists() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"No existe {DB_PATH}. Ejecuta primero: "
            "python scripts/build_db.py && python scripts/build_glossary_index.py"
        )


@contextmanager
def read_only_connection() -> Iterator[sqlite3.Connection]:
    """Abre una conexión SQLite en modo solo-lectura (`mode=ro` en la URI)."""
    _check_db_exists()
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        yield conn
    finally:
        conn.close()


def get_schema_description() -> str:
    """Describe tablas y columnas reales para dárselo al modelo como contexto.

    Se genera desde la base (no a mano) para que nunca quede desactualizada
    si build_db.py cambia.
    """
    lines: list[str] = []
    with read_only_connection() as conn:
        # glosario_chunks/_fts son para la herramienta buscar_glosario (RAG),
        # no para que el agente les escriba SQL directo.
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "AND name NOT LIKE '%_fts%' AND name != 'glosario_chunks' ORDER BY name"
            )
        ]
        for table in tables:
            cols = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            col_desc = ", ".join(f"{c[1]} {c[2]}" for c in cols)
            n_rows = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            lines.append(f"- {table} ({n_rows} filas): {col_desc}")

        meta_rows = conn.execute("SELECT clave, valor FROM meta").fetchall()
        lines.append("\nValores de configuración (tabla meta):")
        for clave, valor in meta_rows:
            lines.append(f"  {clave} = {valor}")
    return "\n".join(lines)
