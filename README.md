# hackaton-fup

Prototipo (MVP) para la **Hackatón de Programación 2026 — Campus Party FUP /
Hospital Susana López de Valencia**. Agente conversacional NL2SQL + RAG sobre
los datos del Sistema de Información Hospitalaria (HIS), más un dashboard
interactivo con KPIs y alertas.

Ver [DECISIONS.md](DECISIONS.md) para los supuestos de datos (fecha de corte,
stock simulado, capacidad estimada, calidad de datos) — léelo antes de la demo.

📚 **Documentación:**
- [docs/modelo-relacional.md](docs/modelo-relacional.md) — diagrama entidad-relación
  y diccionario de datos completo, con la integridad referencial de cada
  relación verificada por consulta (no asumida). Punto de partida obligatorio
  para diseñar casos de uso.
- [DECISIONS.md](DECISIONS.md) — supuestos de ingeniería y hallazgos de calidad
  de datos.

## Arquitectura

```
Insumos Hackaton/Datos/*.txt  →  scripts/build_db.py  →  data/hackaton.db (SQLite)
Insumos Hackaton/*.pdf        →  scripts/build_glossary_index.py  →  tabla glosario_fts (RAG)

data/hackaton.db  →  app/api.py (FastAPI)  →  dashboard/main.py
                        │
                        └─ app/nl2sql_agent.py: agente con tool-use de Claude
                           (consultar_sql + buscar_glosario), validado por
                           app/sql_guard.py antes de tocar la base
```

- **Backend** (`app/`): FastAPI + agente NL2SQL/RAG sobre Claude (Anthropic API).
- **Dashboard** (`dashboard/`): Streamlit multipágina con navegación en la
  barra lateral — **Resumen** (KPIs/gráficas/alertas, lee la base directo) y
  **Agente** (chat que usa la API, con panel de detalle mostrando el SQL
  real que ejecutó el agente para cada respuesta).
- **Base de datos**: SQLite generada localmente, nunca se versiona (`data/`
  está en `.gitignore`).

## Stack técnico

| Capa | Librería | Para qué se usa |
|---|---|---|
| ETL | `pandas` | Leer los `.txt` delimitados por `|`, parsear fechas, cargar a SQLite (`scripts/build_db.py`) |
| ETL | `numpy` | Generador aleatorio con semilla fija para simular el stock de medicamentos |
| RAG | `pypdf` | Extraer texto de los PDFs (diccionario de datos, glosario de salud) |
| RAG | `sqlite3` (FTS5, stdlib) | Índice de texto completo en español (`tokenize='unicode61 remove_diacritics 2'`), sin embeddings ni costo de API |
| Agente | `anthropic` | SDK oficial, tool-use (function calling) con Claude |
| API | `fastapi` + `uvicorn` | Backend HTTP (`/ask`, `/health`, `/alerts`) |
| API | `pydantic` | Validación de request/response (`AskRequest`, `AskResponse`) |
| Config | `python-dotenv` | Carga `.env` sin exponer la key en el código |
| Dashboard | `streamlit` | UI multipágina (`st.navigation`), estado de sesión, chat |
| Dashboard | `plotly` | Gráficas interactivas (ocupación, espera en triage, cirugías) |
| Alertas | `requests` | Webhook saliente (Slack/Discord/Teams) en `scripts/check_alerts.py` |

## Cómo funciona cada pieza (para exposición)

**1. ETL — `scripts/build_db.py`**
Lee cada `.txt` con `pandas.read_csv(sep="|", quoting=csv.QUOTE_NONE, dtype=str)`.
`QUOTE_NONE` es la decisión clave: los campos de texto libre (p. ej.
`MotivoConsulta`) traen comillas dobles sueltas como texto literal, no como
delimitador CSV — con el modo por defecto de pandas esto fusionaba filas en
silencio (17.781 filas reales quedaban en 17.721, ver [DECISIONS.md](DECISIONS.md)).
`load_table()` además verifica que el número de filas cargadas coincida con
`wc -l` del archivo original y aborta si no coincide. `build_stock_simulado()`
y `build_capacidad_camas()` generan las dos tablas derivadas (una simulada
con semilla fija, otra estimada de datos reales — la diferencia está
documentada y expuesta al usuario). `reportar_llaves_primarias()` verifica
empíricamente cada llave primaria candidata (cuenta valores distintos vs.
totales) en vez de asumirla por el nombre de la columna.

**2. RAG — `scripts/build_glossary_index.py` + `app/glossary.py`**
Sin embeddings ni vector DB: `chunk_text()` trocea cada PDF en fragmentos de
900 caracteres con 150 de solapamiento, y se indexan en una tabla virtual
`FTS5` de SQLite (`content_rowid`, tokenizer `unicode61` con soporte de
español). `search_glossary()` convierte la pregunta del usuario en una
consulta `MATCH` (cada palabra entre comillas para que un guion como en
"CIE-10" no se interprete como operador) y ordena por `rank` de FTS5. Para
dos documentos de referencia cortos (24 fragmentos), texto completo es más
rápido y barato que embeddings, y cero dependencias extra.

**3. Agente NL2SQL — `app/nl2sql_agent.py`**
`answer_question()` implementa el loop de *tool-use* de Claude a mano
(sin frameworks tipo LangChain): manda la pregunta + 2 herramientas
(`consultar_sql`, `buscar_glosario`) a `client.messages.create()`; si
`stop_reason == "tool_use"`, ejecuta la(s) herramienta(s), añade el
resultado como `tool_result` al historial de mensajes y vuelve a llamar al
modelo — hasta `MAX_AGENT_TOOL_TURNS` (6) turnos o hasta que el modelo
responda texto final. Cada turno mide por separado el tiempo de LLM vs. el
de herramientas (`time.perf_counter()`), expuesto en la respuesta
(`llm_seconds`, `tools_seconds`) y visible en el dashboard.

**4. Guardas de seguridad — `app/sql_guard.py` + `app/db.py`**
El SQL que escribe el modelo nunca se ejecuta a ciegas: `validate_readonly_sql()`
exige que empiece por `SELECT`/`WITH`, rechaza una lista de palabras clave de
escritura/DDL (`INSERT`, `DROP`, `PRAGMA`, ...) por regex, rechaza comentarios
y múltiples sentencias, y fuerza un `LIMIT`. `execute_readonly_sql()` además
corre con un `threading.Timer` que interrumpe la consulta a los 5s. Como
segunda barrera independiente, la conexión se abre con `mode=ro` en la URI
de SQLite (`app/db.py`), así que aunque algo se saltara el guard, el archivo
en sí rechaza escrituras a nivel de sistema operativo.

**5. API — `app/api.py`**
Tres endpoints FastAPI: `GET /health` (verifica que la DB existe y responde),
`GET /alerts` (reexpone `app/alerts.py` para que `scripts/check_alerts.py` u
otro scheduler externo no duplique la lógica de umbrales) y `POST /ask`
(valida el body con Pydantic, llama `answer_question()`, traduce
`RuntimeError` de configuración a HTTP 503 y cualquier otro error a 500 sin
filtrar detalles internos al cliente).

**6. Dashboard — `dashboard/`**
`dashboard/queries.py` centraliza el SQL de solo lectura para los KPIs
(`ocupacion_por_servicio`, `espera_promedio_por_triage`,
`cirugias_programadas_por_semana`, `medicamentos_bajo_inventario`), todas
relativas a `fecha_corte_demo` (nunca `CURRENT_DATE`, porque el dataset es
histórico y fijo). `dashboard/views/agente.py` maneja el chat con estado de
sesión de Streamlit (`_encolar_pregunta`, `_procesar_pendiente`) y un panel
de trazabilidad (`_render_trace_panel`) que muestra el SQL real ejecutado
por el agente en cada respuesta — clave para defender en la exposición que
el agente no "alucina" números, los calcula.

**7. Mitigación de sesgos en el agente**
El `system_prompt()` del agente (`app/nl2sql_agent.py`) no solo describe el
esquema: codifica reglas de negocio para evitar conclusiones engañosas —
usar `fecha_corte_demo` en vez de la fecha real, aclarar cuando un dato es
simulado (stock) o estimado (capacidad de camas), excluir diagnósticos
vacíos de los rankings, advertir que el último mes del dataset está
incompleto antes de comparar volúmenes mensuales, y aclarar que
`programacion_cirugia` solo cruza de forma confiable con ~25-34% de sus
filas. Son reglas explícitas, no algo que el modelo infiere solo.

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
streamlit run dashboard/main.py
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

## Despliegue (gratis) — Streamlit Community Cloud

El free tier de Streamlit Community Cloud solo corre **un** proceso, así que
`dashboard/main.py` arranca `app.api:app` (FastAPI) en un hilo interno la
primera vez que alguien abre la app — el dashboard le sigue hablando por
HTTP a `http://localhost:8000` exactamente igual que en local, solo que
ambos viven en el mismo contenedor. En local con dos terminales (API +
dashboard, como en "Puesta en marcha") esto no cambia nada: `main.py`
detecta que la API ya está respondiendo y no levanta una segunda.

**1. Pushear los cambios** (el repo ya tiene remoto configurado):

```bash
git push origin main
```

**2. Crear la app en [share.streamlit.io](https://share.streamlit.io)**
(entrar con la cuenta de GitHub que tiene acceso al repo):

- **Repository**: tu repo · **Branch**: `main`
- **Main file path**: `dashboard/main.py`
- **Python version**: 3.11 (en "Advanced settings")

**3. Secrets** (en el mismo diálogo de "Advanced settings", o después en
Settings → Secrets de la app ya creada) — pega esto con tu key real:

```toml
ANTHROPIC_API_KEY = "sk-ant-..."
CLAUDE_MODEL = "claude-sonnet-5"
```

`dashboard/main.py` copia estos valores a variables de entorno antes de
importar cualquier módulo de `app/`, así que `app/config.py` los ve igual
que si vinieran de `.env`. **Nunca** pegues la key en `.env.example` ni en
un commit — solo en el campo Secrets de Streamlit Cloud (no queda en git).

**4. Git LFS en la plataforma — el único riesgo real:** `Servicios.txt` y
`MedicamentoInsumo.txt` (>85MB cada uno) van por Git LFS. Si Streamlit Cloud
clona el repo sin resolver LFS, `dashboard/main.py` construye la base de
datos en frío al primer arranque (`scripts/build_db.py` +
`scripts/build_glossary_index.py`, cacheado después) y va a fallar con un
error explícito en pantalla mencionando "puntero de Git LFS sin resolver"
en vez de fallar en silencio — si ves ese mensaje, la base no se pudo
construir por esto. Si pasa: la alternativa más simple es construir
`data/hackaton.db` localmente y commitearlo directo por Git LFS (pesa
~330MB, cabe en la cuota gratis de 1GB), así el contenedor no necesita
tocar los `.txt` crudos en absoluto.

**5. Primer arranque:** puede tardar 1-2 min (construye la base si hace
falta + instala dependencias). El free tier además "duerme" la app tras un
rato sin visitas — la primera carga después de eso tarda ~30-50s en
despertar. Normal, no es un error.

## Observabilidad

- Cada respuesta del agente trae el tiempo que tomó, desglosado: `elapsed_seconds`
  (total), `llm_seconds` (llamadas a la API de Claude) y `tools_seconds` (SQL +
  glosario) — visible en el panel "Detalle del agente" del dashboard y en el log
  del servidor (`uvicorn`) en cada request a `/ask`. En la práctica el modelo es
  el cuello de botella (segundos), no la base de datos (milisegundos).
- `GET /alerts` expone las mismas alertas de camas/inventario que ve el
  dashboard, para que `scripts/check_alerts.py` (o cualquier monitor externo)
  las consuma sin duplicar la lógica de umbrales.

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

## Skills de diseño (Claude Code / Codex / Cursor)

El dashboard se diseñó con las skills de `redesign-existing-projects` y
`high-end-visual-design` (paquete `emilkowalski/skills` + `taste-skill`). Su
contenido vive en `.agents/skills/` (versionado); los symlinks que cada
herramienta de IA necesita (`.claude/skills/`, etc.) NO se versionan porque
en Windows sin symlinks (`core.symlinks=false`) git los guardaría rotos.
Después de clonar, si vas a pedirle a un agente que toque el diseño:

```bash
npx skills experimental_install
```

## Estructura del repo

| Ruta | Qué es |
|---|---|
| `Insumos Hackaton/` | Datos crudos del reto (no editar a mano) |
| `scripts/build_db.py` | ETL: `.txt` → SQLite (índices + verificación de llaves primarias) |
| `scripts/build_glossary_index.py` | PDFs → índice FTS5 (RAG) |
| `scripts/check_alerts.py` | Notificación automática de alertas (cron / Task Scheduler) |
| `app/config.py` | Variables de entorno, límites de seguridad (`MAX_SQL_ROWS`, `SQL_TIMEOUT_SECONDS`, `MAX_AGENT_TOOL_TURNS`) |
| `app/db.py` | Conexión de solo lectura (`mode=ro`) y descripción del esquema para el prompt del agente |
| `app/sql_guard.py` | Valida y ejecuta con límites el SQL que genera el agente (whitelist SELECT/WITH, timeout) |
| `app/glossary.py` | Búsqueda RAG (FTS5) sobre el diccionario de datos y el glosario de salud |
| `app/nl2sql_agent.py` | Loop de tool-use de Claude: `consultar_sql` + `buscar_glosario`, system prompt con reglas de negocio |
| `app/alerts.py` | Umbrales de ocupación de camas y desabastecimiento de medicamentos |
| `app/api.py` | Endpoints FastAPI: `/health`, `/alerts`, `/ask` |
| `dashboard/main.py` | Punto de entrada (navegación en la barra lateral) |
| `dashboard/theme.py` | Paleta y CSS compartidos por todas las páginas |
| `dashboard/views/` | Una página por archivo: `resumen.py`, `agente.py` |
| `.streamlit/config.toml` | Tema oscuro + acento dorado del dashboard |
| `data/` | Generado, no versionado |
| `DECISIONS.md` | Supuestos de datos e ingeniería, para el equipo y el jurado |
| `docs/modelo-relacional.md` | Diagrama ER + diccionario de datos, para casos de uso |
| `docs/modelo-relacional.drawio` | Mismo modelo, estilo clásico editable en draw.io |
