"""API del agente conversacional. Ejecutar con:

    uvicorn app.api:app --reload --port 8000
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.alerts import alertas_activas_dict
from app.db import DB_PATH, read_only_connection
from app.nl2sql_agent import answer_question

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hackaton-fup")

app = FastAPI(title="Agente HIS — hackaton-fup", version="0.1.0")

# CORS abierto solo para desarrollo local (dashboard de Streamlit en otro puerto).
# Restringir origins si esto llega a exponerse fuera de localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class AskResponse(BaseModel):
    answer: str
    turns: int
    tool_calls: list[dict]
    elapsed_seconds: float
    llm_seconds: float
    tools_seconds: float


@app.get("/health")
def health() -> dict:
    db_ok = DB_PATH.exists()
    if db_ok:
        try:
            with read_only_connection() as conn:
                conn.execute("SELECT 1").fetchone()
        except Exception:
            db_ok = False
    return {"status": "ok" if db_ok else "degraded", "db_ok": db_ok}


@app.get("/alerts")
def alerts() -> dict:
    """Alertas activas: saturación de camas y desabastecimiento de medicamentos.

    Pensado para que scripts/check_alerts.py (o cualquier scheduler externo)
    lo consuma y decida si notifica, sin duplicar la lógica de umbrales.
    """
    activas = alertas_activas_dict()
    counts = {"critical": 0, "warning": 0}
    for a in activas:
        counts[a["nivel"]] += 1
    return {"alerts": activas, "counts": counts}


@app.post("/ask", response_model=AskResponse)
def ask(payload: AskRequest) -> AskResponse:
    try:
        result = answer_question(payload.question)
    except RuntimeError as exc:
        # p. ej. falta ANTHROPIC_API_KEY: es un error de configuración, no del usuario.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception:
        logger.exception("Fallo inesperado respondiendo la pregunta: %r", payload.question)
        raise HTTPException(status_code=500, detail="Error interno procesando la pregunta.") from None

    logger.info(
        "ask: %.2fs total (%.2fs LLM, %.2fs herramientas, %d turnos) - %r",
        result.elapsed_seconds, result.llm_seconds, result.tools_seconds,
        result.turns, payload.question,
    )
    return AskResponse(
        answer=result.answer, turns=result.turns, tool_calls=result.tool_calls,
        elapsed_seconds=round(result.elapsed_seconds, 3),
        llm_seconds=round(result.llm_seconds, 3),
        tools_seconds=round(result.tools_seconds, 3),
    )
