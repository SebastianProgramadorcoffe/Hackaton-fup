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
