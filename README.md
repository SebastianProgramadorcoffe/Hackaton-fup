# hackaton-fup

Prototipo (MVP) para la **Hackatón de Programación 2026 — Campus Party FUP /
Hospital Susana López de Valencia**. Agente conversacional NL2SQL + RAG sobre
los datos del Sistema de Información Hospitalaria (HIS), más un dashboard
interactivo con KPIs y alertas.

Ver [DECISIONS.md](DECISIONS.md) para los supuestos de datos (fecha de corte,
stock simulado, capacidad estimada, calidad de datos) — léelo antes de la demo.

## Arquitectura

```
Insumos Hackaton/Datos/*.txt  →  scripts/build_db.py  →  data/hackaton.db (SQLite)
Insumos Hackaton/*.pdf        →  scripts/build_glossary_index.py  →  tabla glosario_fts (RAG)

data/hackaton.db  →  app/api.py (FastAPI)  →  dashboard/streamlit_app.py
                        │
                        └─ app/nl2sql_agent.py: agente con tool-use de Claude
                           (consultar_sql + buscar_glosario), validado por
                           app/sql_guard.py antes de tocar la base
```

- **Backend** (`app/`): FastAPI + agente NL2SQL/RAG sobre Claude (Anthropic API).
- **Dashboard** (`dashboard/`): Streamlit + Plotly, lee la base directo (sin
  pasar por el agente) para las gráficas, y usa la API solo para el chat.
- **Base de datos**: SQLite generada localmente, nunca se versiona (`data/`
  está en `.gitignore`).

## Requisitos

- Python 3.11+
- Una `ANTHROPIC_API_KEY` con crédito disponible (console.anthropic.com)

## Puesta en marcha

> ⚠️ **Este repo usa Git LFS** para `Servicios.txt` y `MedicamentoInsumo.txt`
> (>85MB cada uno). Si después de clonar esos dos archivos pesan ~130 bytes
> en vez de ~90MB, quedaron como punteros sin resolver — instala
> [git-lfs](https://git-lfs.com/) y corre `git lfs pull` una vez.

```bash
# 0) Solo la primera vez que usas git-lfs en esta máquina
git lfs install
git lfs pull

# 1) Entorno virtual e instalación
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2) Variables de entorno
cp .env.example .env
# Edita .env y pega tu ANTHROPIC_API_KEY. Nunca la pegues en .env.example
# (ese sí se sube a git; .env no).

# 3) Construir la base de datos y el índice del glosario (una sola vez,
#    o cada vez que cambien los archivos crudos)
python scripts/build_db.py
python scripts/build_glossary_index.py

# 4) Levantar la API (una terminal)
uvicorn app.api:app --reload --port 8000

# 5) Levantar el dashboard (otra terminal)
streamlit run dashboard/streamlit_app.py
```

Dashboard: http://localhost:8501 · API: http://localhost:8000/docs

## Verificar que todo funciona

```bash
curl http://localhost:8000/health
# {"status":"ok","db_ok":true}
```

Preguntas obligatorias de la demo (probadas, ver DECISIONS.md por el
significado de "hoy" y del stock simulado):

- ¿Cuántas camas de UCI están ocupadas hoy?
- ¿Cuáles son los medicamentos con menos de 5 días de inventario?
- ¿Cuál es el tiempo de espera promedio en urgencias en la última semana?
- ¿Qué servicio tiene más pacientes ingresados este mes?

## Seguridad

- El SQL que genera el agente pasa por `app/sql_guard.py`: solo se permite
  una sentencia `SELECT`/`WITH`, sin palabras clave de escritura/DDL/PRAGMA,
  sin comentarios, con `LIMIT` y timeout forzados.
- La conexión a la base desde el backend es siempre de solo lectura
  (`mode=ro` en la URI SQLite), como segunda barrera independiente del guard.
- El texto libre del dataset (p. ej. `MotivoConsulta`) se trata como dato,
  nunca como instrucción — está explícito en el system prompt del agente.
- Nunca commitear `.env`, credenciales, ni los instaladores/`.zip` que trae
  Windows por defecto (`.gitignore` ya los cubre).

## Estructura del repo

| Ruta | Qué es |
|---|---|
| `Insumos Hackaton/` | Datos crudos del reto (no editar a mano) |
| `scripts/build_db.py` | ETL: `.txt` → SQLite |
| `scripts/build_glossary_index.py` | PDFs → índice FTS5 (RAG) |
| `app/` | Backend: agente NL2SQL/RAG + API |
| `dashboard/` | Dashboard Streamlit |
| `data/` | Generado, no versionado |
| `DECISIONS.md` | Supuestos de datos e ingeniería, para el equipo y el jurado |
