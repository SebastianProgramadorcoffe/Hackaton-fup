"""Búsqueda RAG (FTS5) sobre el diccionario de datos y el glosario de salud.

Los fragmentos se generan con scripts/build_glossary_index.py. Sin
embeddings: para dos documentos de referencia cortos, texto completo (FTS5)
da resultados suficientemente buenos con cero dependencias externas.
"""
from __future__ import annotations

import re

from app.db import read_only_connection

_WORD = re.compile(r"[\wÁÉÍÓÚÑáéíóúñ-]+", re.UNICODE)


def _to_fts_query(user_query: str) -> str:
    """Convierte texto libre a una expresión MATCH segura.

    Cada palabra se envuelve en comillas dobles para que FTS5 la trate como
    literal (evita que un guion, p. ej. en "CIE-10", se interprete como
    operador de la sintaxis de consulta de FTS5) y se combinan con OR para
    priorizar recall sobre un corpus tan pequeño (24 fragmentos).
    """
    words = _WORD.findall(user_query)
    if not words:
        return '""'
    quoted = [f'"{w}"' for w in words]
    return " OR ".join(quoted)


def search_glossary(query: str, limit: int = 5) -> list[dict]:
    fts_query = _to_fts_query(query)
    sql = """
        SELECT c.fuente, c.pagina, c.texto
        FROM glosario_fts f
        JOIN glosario_chunks c ON c.id = f.rowid
        WHERE glosario_fts MATCH ?
        ORDER BY rank
        LIMIT ?
    """
    with read_only_connection() as conn:
        rows = conn.execute(sql, (fts_query, limit)).fetchall()
    return [{"fuente": f, "pagina": p, "texto": t} for f, p, t in rows]
