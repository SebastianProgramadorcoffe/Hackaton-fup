"""Configuración centralizada. Lee variables de entorno desde .env (no versionado)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB_PATH = ROOT / "data" / "hackaton.db"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
# Modelo por defecto: rápido y barato, suficiente para NL2SQL + RAG sobre
# un esquema acotado. Configurable por si se quiere probar con otro.
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")

# Límites de seguridad para las consultas que genera el agente.
MAX_SQL_ROWS = 200
SQL_TIMEOUT_SECONDS = 5
MAX_AGENT_TOOL_TURNS = 6
