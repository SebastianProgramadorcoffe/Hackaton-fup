"""Punto de entrada del dashboard — hackaton-fup.

Ejecutar localmente (con la API corriendo aparte en :8000):
    streamlit run dashboard/main.py

En Streamlit Community Cloud (despliegue gratuito de un solo servicio) no
hay un segundo proceso donde correr `uvicorn app.api:app`, así que este
archivo la arranca internamente en un hilo (ver `_start_api`) la primera
vez que el contenedor procesa una petición — el dashboard le sigue hablando
por `dashboard.theme.API_URL` (http://localhost:8000 por defecto) sin saber
que está en el mismo proceso. Ver README.md → "Despliegue" para el paso a
paso completo (secrets, Git LFS, etc.).

Navegación real en la barra lateral (Streamlit multipage), en vez de una
sola página larga: Resumen (KPIs/gráficas/alertas) y Agente (chat con
panel de razonamiento). Ver dashboard/theme.py para la paleta y el CSS
compartido, y DECISIONS.md para los supuestos de datos.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

# --- Puente de secretos: TIENE que ir antes de cualquier import de
# dashboard.* / app.* -------------------------------------------------------
# Streamlit Community Cloud inyecta lo que pegas en "Secrets" como
# `st.secrets`, NO como variables de entorno del proceso. Pero app/config.py
# (importado transitivamente en cuanto se importa dashboard.views más abajo)
# lee la key con `os.environ.get(...)` al cargarse el módulo, una sola vez.
# Si este puente corriera después de ese import, ya habría leído "".
for _key in ("ANTHROPIC_API_KEY", "CLAUDE_MODEL", "ALERTS_WEBHOOK_URL", "API_URL"):
    if not os.environ.get(_key):
        try:
            if _key in st.secrets:
                os.environ[_key] = str(st.secrets[_key])
        except Exception:
            pass  # sin secrets.toml (desarrollo local con .env, o Secrets vacío): ignorar

from dashboard.theme import API_URL, inject_css, sidebar_brand
from dashboard.views import agente, resumen

DB_PATH = ROOT / "data" / "hackaton.db"


@st.cache_resource(show_spinner="Preparando la base de datos (solo la primera vez)...")
def _ensure_db() -> None:
    """Construye data/hackaton.db si no existe (p. ej. contenedor nuevo en Cloud).

    Local: normalmente ya corriste scripts/build_db.py a mano y esto no
    hace nada. En Streamlit Community Cloud el contenedor arranca desde
    cero cada vez que se redespliega, así que se construye aquí una sola
    vez por contenedor (@st.cache_resource) a partir de los .txt crudos que
    sí van en el repo.
    """
    if DB_PATH.exists():
        return
    for script in ("scripts/build_db.py", "scripts/build_glossary_index.py"):
        resultado = subprocess.run(
            [sys.executable, script], cwd=ROOT, capture_output=True, text=True,
        )
        if resultado.returncode != 0:
            salida = (resultado.stdout + "\n" + resultado.stderr).strip()
            pista = ""
            if "puntero de Git LFS" in salida:
                pista = (
                    "\n\nEsto casi siempre significa que Git LFS no se resolvió al "
                    "clonar el repo en este servidor (Servicios.txt / MedicamentoInsumo.txt "
                    "quedaron como punteros de texto, no el archivo real). Ver README.md → "
                    "Despliegue → 'Git LFS en la plataforma'."
                )
            raise RuntimeError(f"Fallo construyendo la base de datos ({script}):\n{salida}{pista}")


@st.cache_resource(show_spinner=False)
def _start_api() -> bool:
    """Arranca app.api (FastAPI) en un hilo del mismo proceso, una sola vez.

    Alternativa a desplegar la API como servicio aparte: en el free tier de
    Streamlit Community Cloud solo hay un proceso, así que en vez de partir
    la arquitectura dashboard/API en dos hosts gratuitos coordinados, se
    corre el mismo `app.api:app` de siempre pero en un hilo interno. El
    dashboard sigue hablándole por HTTP a través de dashboard.theme.API_URL
    exactamente igual que en local — no hay atajos que se salten la capa de
    guardas de app/sql_guard.py.
    """
    import threading

    import requests
    import uvicorn

    try:
        # Ya hay algo respondiendo en API_URL: desarrollo local con la API
        # en su propia terminal (README → "Puesta en marcha"), u otro
        # despliegue que sí separa los dos servicios. No arrancar una
        # segunda API interna que competiría por el mismo puerto.
        requests.get(f"{API_URL}/health", timeout=0.5)
        return True
    except requests.RequestException:
        pass

    def _run() -> None:
        uvicorn.run("app.api:app", host="127.0.0.1", port=8000, log_level="warning")

    threading.Thread(target=_run, daemon=True, name="api-interna").start()

    # Espera a que el server realmente esté escuchando antes de devolver el
    # control: sin esto, la primera página que llama a /ask o /health puede
    # llegar antes de que uvicorn termine de arrancar.
    for _ in range(50):  # ~5s máx
        try:
            requests.get(f"{API_URL}/health", timeout=0.5)
            return True
        except requests.RequestException:
            time.sleep(0.1)
    return False  # sigue sin responder; las páginas mostrarán su propio error de conexión


try:
    _ensure_db()
    if not _start_api():
        st.warning(
            "La API interna no respondió a tiempo al arrancar. Si el chat del agente "
            "falla, recarga la página — en frío puede tardar unos segundos más."
        )
except Exception as exc:
    st.error(f"No se pudo inicializar el backend: {exc}")
    st.stop()

st.set_page_config(page_title="HIS · hackaton-fup", layout="wide", page_icon="🏥")
inject_css()
sidebar_brand()

pagina = st.navigation(
    [
        st.Page(resumen.render, title="Resumen", icon="📊", url_path="resumen", default=True),
        st.Page(agente.render, title="Agente", icon="💬", url_path="agente"),
    ]
)
pagina.run()
