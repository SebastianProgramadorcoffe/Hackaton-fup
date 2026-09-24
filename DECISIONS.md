# Decisiones de datos e ingeniería

Registro corto de supuestos que no vienen dados por el reto, para que el equipo
y el jurado sepan qué es dato real del HIS y qué es un supuesto de ingeniería.
Se generan y aplican en [`scripts/build_db.py`](scripts/build_db.py).

## 1. Bug de parseo corregido: comillas sueltas en texto libre

`Triage.txt` (y potencialmente otros archivos) tiene comillas dobles (`"`)
como texto literal dentro de `MotivoConsulta` (p. ej. `MOTIVO: "ACCIDENTE..."`),
no como delimitador CSV. Con la configuración por defecto de `pandas.read_csv`,
esto fusionaba varias filas en una sola **sin lanzar ningún error** (17.781
filas reales quedaban en 17.721). Se corrigió con `quoting=csv.QUOTE_NONE` y
se agregó una verificación automática que compara el número de filas cargadas
contra el número de líneas del archivo, y falla ruidosamente si no coinciden.

## 2. Fecha de corte fija ("hoy" para la demo)

El dataset es histórico y fijo: va del 2026-05-01 al 2026-09-21. No existe
campo de fecha de alta/egreso en `Ingresos.txt` (solo `FechaIngreso` y
`FechaHospitalizacion`, que es la asignación de cama, confirmado con el
Diccionario_Datos_HIS.pdf vía el cuaderno de NotebookLM del proyecto).

Se fija `fecha_corte_demo = 2026-09-21` (máxima fecha observada) en la tabla
`meta`. El agente NL2SQL debe traducir "hoy" / "actualmente" a esa fecha en
vez de usar `CURRENT_DATE`, y "ocupada" se interpreta como
`date(FechaHospitalizacion) = fecha_corte_demo`.

## 3. Stock de medicamentos: SIMULADO, no viene del HIS

`MedicamentoInsumo.txt` solo registra consumo (qué se dispensó y cuándo), no
existe ninguna tabla de inventario/stock en los materiales del reto
(confirmado con el cuaderno). Para responder la pregunta obligatoria de la
demo ("medicamentos con menos de 5 días de inventario") se creó la tabla
`stock_medicamentos` con un stock inicial **simulado** por medicamento:

```
stock_actual = consumo_promedio_diario_real × autonomía_aleatoria(1–20 días)
```

con semilla fija (`STOCK_SEED = 42`) para que sea reproducible. Cada fila
queda marcada `simulado = 1`. **Esto debe decirse explícitamente en la demo**
("el stock inicial es un dato simulado para efectos del prototipo; el
consumo promedio diario sí es real, calculado sobre el histórico").

## 4. Capacidad de camas: estimada, no simulada

No hay tabla de capacidad física de camas por servicio. `capacidad_camas` sí
se deriva de datos reales: cuenta camas (`CodigoCama`) distintas observadas
en todo el histórico de `Ingresos` por `NombreGrupoCama`. Es una capacidad
"instalada observada", probablemente menor a la capacidad física real del
hospital, y así debe presentarse.

## 5. Calidad de datos conocida

- ~1.675 de 17.781 filas de `Triage.txt` (~9.4%) tienen `OidTriage` vacío.
  No se puede hacer join por ese id en esas filas; si se necesitan, usar
  `IdPaciente2` en su lugar.
- `triage.ClasificacionTriage` no es una categoría limpia: mezcla ubicación,
  tipo de consulta y color (ej. `"PEDIATRIA URGENCIAS CONSULTORIO UNO-
  TRIAGE 2 (AMARILLO)"`), con ~18 valores distintos para solo 4 niveles
  reales (1 a 4). Agrupar por el texto crudo da una gráfica y respuestas
  ilegibles. El nivel se extrae con
  `CAST(substr(ClasificacionTriage, instr(ClasificacionTriage,'TRIAGE')+7, 1) AS INTEGER)`
  — ya aplicado en `dashboard/queries.py` y en las reglas del agente NL2SQL.
- **`programacion_cirugia` enlaza mal con `ingresos` y `paciente`** (ver
  [docs/MODELO_RELACIONAL.md](docs/MODELO_RELACIONAL.md) para el detalle
  verificado por consulta, no por inspección visual): solo el **25.1%** de
  sus filas (3.277 de 13.046) tiene un `OidIngreso` que existe en
  `ingresos`, y solo el **34.4%** (4.492) tiene un `IdPaciente` que existe
  en `paciente`. Desglose de por qué:
  - 2.404 filas (18.4%) tienen `OidIngreso` vacío.
  - 4.896 filas (37.5%) referencian un `OidIngreso` **anterior al mínimo**
    de `Ingresos.txt` — `ProgramacionCirugia.txt` cubre una ventana de
    fechas más amplia que `Ingresos.txt`, que parece recortado.
  - 2.469 filas (18.9%) están dentro del mismo rango de ids pero aun así
    no hacen match — hueco real, no explicado por la ventana de fechas.
  - **Implicación para casos de uso:** cualquier consulta que necesite el
    paciente o la fecha de una cirugía programada (uniendo con `ingresos`
    o `paciente`) solo cubre ~una cuarta parte de los registros. La
    gráfica "Uso de quirófanos" del dashboard hereda esta limitación
    porque `programacion_cirugia` no trae su propia fecha — depende del
    `JOIN` con `ingresos.FechaIngreso` para poder agrupar por semana.
- `programacion_cirugia` no tiene una llave de una sola columna: 
  `ConsecutivoProgramacion` se repite (6.156 valores distintos en 13.046
  filas) porque una misma cirugía programada puede incluir varios códigos
  de procedimiento (CUPS). La llave real, verificada, es la compuesta
  **(ConsecutivoProgramacion, CodigoServicio)** — 13.046/13.046 única.
