"""Valida y ejecuta con límites el SQL que genera el modelo.

El agente NL2SQL escribe la consulta; esto es la barrera de seguridad antes
de que toque la base de datos real. Capas de defensa (todas necesarias,
ninguna sola es suficiente):

1. Aquí: solo se permite una única sentencia SELECT/WITH de lectura, sin
   palabras clave de escritura/DDL/PRAGMA, sin múltiples sentencias.
2. app/db.py: la conexión se abre en modo `mode=ro` (SQLite la rechaza a
   nivel de archivo si de algún modo esto se saltara).
3. Aquí también: se fuerza un LIMIT de filas y un timeout de ejecución, para
   que una consulta cara (o un bucle del agente) no cuelgue el proceso.
"""
from __future__ import annotations

import re
import sqlite3
import threading

from app.config import MAX_SQL_ROWS, SQL_TIMEOUT_SECONDS
from app.db import read_only_connection

_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|ATTACH|DETACH|PRAGMA|VACUUM|"
    r"REPLACE|REINDEX|TRIGGER|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)
_ALLOWED_START = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_HAS_LIMIT = re.compile(r"\bLIMIT\s+\d+\b", re.IGNORECASE)


class SqlGuardError(ValueError):
    """El SQL propuesto no pasó la validación de seguridad."""


def validate_readonly_sql(sql: str) -> str:
    sql = sql.strip()
    if not sql:
        raise SqlGuardError("La consulta SQL está vacía.")

    if "--" in sql or "/*" in sql:
        raise SqlGuardError("No se permiten comentarios dentro del SQL generado.")

    # Solo una sentencia: se permite un único ';' final, ninguno en medio.
    stripped = sql[:-1] if sql.endswith(";") else sql
    if ";" in stripped:
        raise SqlGuardError("Solo se permite una sentencia SQL por consulta.")

    if not _ALLOWED_START.match(stripped):
        raise SqlGuardError("Solo se permiten consultas SELECT o WITH (CTE) de solo lectura.")

    if _FORBIDDEN_KEYWORDS.search(stripped):
        raise SqlGuardError("La consulta contiene una palabra clave no permitida (escritura/DDL/PRAGMA).")

    if not _HAS_LIMIT.search(stripped):
        stripped = f"{stripped}\nLIMIT {MAX_SQL_ROWS}"

    return stripped


def execute_readonly_sql(sql: str) -> tuple[list[str], list[tuple]]:
    """Valida, ejecuta con timeout y devuelve (columnas, filas)."""
    safe_sql = validate_readonly_sql(sql)

    with read_only_connection() as conn:
        timer = threading.Timer(SQL_TIMEOUT_SECONDS, conn.interrupt)
        timer.start()
        try:
            cursor = conn.execute(safe_sql)
            columns = [d[0] for d in cursor.description] if cursor.description else []
            rows = cursor.fetchmany(MAX_SQL_ROWS)
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc).lower():
                raise SqlGuardError(
                    f"La consulta tardó más de {SQL_TIMEOUT_SECONDS}s y fue cancelada. "
                    "Intenta con filtros más específicos."
                ) from exc
            raise SqlGuardError(f"Error al ejecutar la consulta: {exc}") from exc
        finally:
            timer.cancel()

    return columns, rows
