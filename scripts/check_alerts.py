"""Notificación automática de alertas: saturación de camas y desabastecimiento.

Uso manual:
    python scripts/check_alerts.py

Para que sea "automático" de verdad, este script está pensado para
programarse con el scheduler del sistema operativo (no reinventa un cron
propio dentro del proyecto):

    # cron (Linux/Mac), cada 15 minutos
    */15 * * * * cd /ruta/al/repo && .venv/bin/python scripts/check_alerts.py

    # Windows: Programador de tareas -> Crear tarea básica -> Acción:
    #   .venv\\Scripts\\python.exe scripts\\check_alerts.py

Si se define ALERTS_WEBHOOK_URL en .env (acepta webhooks entrantes de Slack
o Discord/Teams con el mismo formato {"text": ...}), además envía la
notificación ahí. Si no está configurado, solo imprime en consola/log —
sigue siendo útil para revisar el estado o para que el scheduler capture
la salida en un archivo de log.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# En Windows, ejecutado sin consola (Task Scheduler) o con la consola en su
# codepage cp1252 por defecto, un simple print() con emoji (✅🔴🟡) revienta
# con UnicodeEncodeError y el chequeo de alertas falla en silencio -- justo
# cuando nadie está mirando para notarlo. Se fuerza UTF-8 en stdout/stderr
# antes de imprimir nada.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="backslashreplace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from dotenv import load_dotenv

from app.alerts import Alerta, alertas_activas

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

WEBHOOK_URL = os.environ.get("ALERTS_WEBHOOK_URL", "")

ICONOS = {"critical": "🔴", "warning": "🟡"}


def _formatear(alertas: list[Alerta]) -> str:
    if not alertas:
        return "✅ Sin alertas activas de camas ni de inventario."
    lineas = [f"{len(alertas)} alerta(s) activa(s) — hackaton-fup HIS:"]
    for a in alertas:
        icono = ICONOS.get(a.nivel, "•")
        lineas.append(f"{icono} [{a.tipo}] {a.servicio_o_medicamento}: {a.detalle}")
    return "\n".join(lineas)


def _notificar_webhook(mensaje: str) -> None:
    if not WEBHOOK_URL:
        return
    try:
        resp = requests.post(WEBHOOK_URL, json={"text": mensaje}, timeout=10)
        resp.raise_for_status()
        print(f"[check_alerts] Notificación enviada a ALERTS_WEBHOOK_URL (status {resp.status_code}).")
    except requests.RequestException as exc:
        # Un webhook caído no debe romper el chequeo: se reporta y se sigue.
        print(f"[check_alerts] No se pudo enviar el webhook: {exc}", file=sys.stderr)


def main() -> None:
    alertas = alertas_activas()
    mensaje = _formatear(alertas)
    print(mensaje)

    hay_alertas = bool(alertas)
    if hay_alertas:
        if WEBHOOK_URL:
            _notificar_webhook(mensaje)
        else:
            print(
                "[check_alerts] ALERTS_WEBHOOK_URL no está configurado en .env: "
                "no se envía notificación externa, solo este log.",
                file=sys.stderr,
            )


if __name__ == "__main__":
    main()
