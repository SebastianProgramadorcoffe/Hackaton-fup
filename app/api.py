"""API del agente conversacional. Ejecutar con:

    uvicorn app.api:app --reload --port 8000
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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

    return AskResponse(answer=result.answer, turns=result.turns, tool_calls=result.tool_calls)
