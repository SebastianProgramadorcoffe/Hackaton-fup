"""Extrae texto de los PDFs de referencia y los indexa en SQLite FTS5 para RAG.

Uso:
    python scripts/build_glossary_index.py

Requiere que data/hackaton.db ya exista (ejecutar antes scripts/build_db.py).
No usa embeddings: para dos PDFs de referencia (diccionario de datos y
glosario de salud), una búsqueda de texto completo (FTS5, con soporte de
español vía tokenizer unicode61) es suficiente, más rápida, sin costo de API
ni dependencias extra, y perfectamente defendible en una demo de 8 horas.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from pypdf import PdfReader

# Ver build_db.py: la consola por defecto de Windows (cp1252) revienta con
# UnicodeEncodeError si algún print() trae un carácter fuera de ese codepage.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "hackaton.db"

SOURCES = {
    "diccionario_datos": ROOT / "Insumos Hackaton" / "Diccionario_Datos_HIS.pdf",
    "glosario_salud": ROOT / "Insumos Hackaton" / "Glosario_Terminos_Salud_HIS.pdf",
}

CHUNK_SIZE = 900
CHUNK_OVERLAP = 150


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    text = " ".join(text.split())  # normaliza espacios/saltos de línea
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


def extract_pdf_chunks(path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(str(path))
    chunks: list[tuple[int, str]] = []
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for chunk in chunk_text(text):
            chunks.append((page_num, chunk))
    return chunks


def main() -> None:
    if not DB_PATH.exists():
        print(f"ERROR: no existe {DB_PATH}. Ejecuta antes scripts/build_db.py", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DROP TABLE IF EXISTS glosario_chunks")
        conn.execute(
            """
            CREATE TABLE glosario_chunks (
                id INTEGER PRIMARY KEY,
                fuente TEXT NOT NULL,
                pagina INTEGER NOT NULL,
                texto TEXT NOT NULL
            )
            """
        )
        conn.execute("DROP TABLE IF EXISTS glosario_fts")
        conn.execute(
            """
            CREATE VIRTUAL TABLE glosario_fts USING fts5(
                texto, content='glosario_chunks', content_rowid='id',
                tokenize='unicode61 remove_diacritics 2'
            )
            """
        )

        total = 0
        for fuente, path in SOURCES.items():
            if not path.exists():
                raise FileNotFoundError(f"No se encontró {path}")
            chunks = extract_pdf_chunks(path)
            for pagina, texto in chunks:
                conn.execute(
                    "INSERT INTO glosario_chunks (fuente, pagina, texto) VALUES (?, ?, ?)",
                    (fuente, pagina, texto),
                )
            total += len(chunks)
            print(f"  {fuente:<20} {len(chunks):>4} fragmentos  <- {path.name}")

        conn.execute("INSERT INTO glosario_fts (rowid, texto) SELECT id, texto FROM glosario_chunks")
        conn.commit()
        print(f"\nListo. {total} fragmentos indexados en glosario_fts.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
