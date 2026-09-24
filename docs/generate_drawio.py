# -*- coding: utf-8 -*-
"""Genera modelo-relacional.drawio (estilo clasico: cajas naranjas,
encabezado en negrita subrayado, PK en negrita, FK en cursiva) a partir del
mismo esquema verificado que modelo-relacional.mmd. Abrir el .drawio en
https://app.diagrams.net (gratis, sin instalar nada) o en la app de
escritorio de draw.io. Si el esquema de la base cambia, edita las listas
TABLES/EDGES de este script (mantenerlas iguales a modelo-relacional.mmd) y
vuelve a correr:

    python generate_drawio.py > modelo-relacional.drawio
"""
import html

# (nombre_tabla, ancho, [(columna, tag)])  tag: "PK", "FK", ""
TABLES = [
    ("PACIENTE", 220, [
        ("IdPaciente", "PK"), ("TipoDocumento", ""), ("NombrePaciente", ""),
        ("FechaNacimiento", ""), ("Sexo", ""), ("Asegurador", ""),
        ("Regimen", ""), ("Departamento", ""), ("Municipio", ""), ("Zona", ""),
    ]),
    ("INGRESOS", 260, [
        ("OidIngreso", "PK"), ("ConsecutivoIngreso", ""), ("IdPaciente", "FK"),
        ("ClaseIngreso", ""), ("ViaIngreso", ""), ("TipoRiesgo", ""),
        ("FechaIngreso", ""), ("FechaHospitalizacion", ""), ("OidTriageA", "FK"),
        ("CodigoCama", ""), ("NombreCama", ""), ("NombreGrupoCama", ""),
        ("NombreSubgrupoCama", ""), ("CodigoDiagnostico", ""), ("NombreDiagnostico", ""),
    ]),
    ("ATENCION", 200, [
        ("OidIngreso", "PK/FK"), ("FechaAtencion", ""),
    ]),
    ("TRIAGE", 240, [
        ("OidTriage", "PK"), ("FechaTriage", ""), ("MotivoConsulta", ""),
        ("TensionArterial", ""), ("FrecuenciaCardiaca", ""), ("FrecuenciaRespiratoria", ""),
        ("Temperatura", ""), ("IdPaciente2", "FK"), ("CodigoTriage", ""),
        ("ClasificacionTriage", ""),
    ]),
    ("PROGRAMACION_CIRUGIA", 240, [
        ("ConsecutivoProgramacion", "PK"), ("IdPaciente", "FK"),
        ("OidIngreso", "FK"), ("CodigoServicio", "PK"),
    ]),
    ("SERVICIOS", 220, [
        ("OidS", "PK"), ("OidIngreso", "FK"), ("CodigoServicio", ""),
        ("NombreServicio", ""), ("Cantidad", ""), ("FechaPrestacion", ""),
        ("CodigoAreaServicio", ""), ("AreaServicio", ""), ("Especialidad", ""),
    ]),
    ("MEDICAMENTO_INSUMO", 220, [
        ("OidMI", "PK"), ("OidIngreso", "FK"), ("CodigoServicio", ""),
        ("NombreServicio", ""), ("Cantidad", ""), ("FechaPrestacion", ""),
        ("AreaServicio", ""), ("Especialidad", ""),
    ]),
    ("STOCK_MEDICAMENTOS", 220, [
        ("codigo_servicio", "PK"), ("nombre_servicio", ""),
        ("consumo_promedio_diario", ""), ("stock_actual", ""), ("simulado", ""),
    ]),
    ("CAPACIDAD_CAMAS", 200, [
        ("nombre_grupo_cama", "PK"), ("capacidad_estimada", ""),
    ]),
    ("META", 160, [
        ("clave", "PK"), ("valor", ""),
    ]),
]

# posiciones (x, y) elegidas a mano para que se parezcan a la referencia:
# entidad principal (INGRESOS) al centro, las que dependen de ella alrededor.
POS = {
    "PACIENTE": (40, 40),
    "META": (400, 40),
    "TRIAGE": (620, 260),
    "INGRESOS": (620, 560),
    "ATENCION": (40, 900),
    "PROGRAMACION_CIRUGIA": (360, 900),
    "SERVICIOS": (940, 900),
    "MEDICAMENTO_INSUMO": (1220, 900),
    "CAPACIDAD_CAMAS": (1500, 560),
    "STOCK_MEDICAMENTOS": (1500, 900),
}

# (tabla_origen, tabla_destino, etiqueta)  -- origen = lado "muchos" (FK)
EDGES = [
    ("INGRESOS", "PACIENTE", "IdPaciente 100%"),
    ("INGRESOS", "TRIAGE", "OidTriageA 90.6%"),
    ("ATENCION", "INGRESOS", "OidIngreso 97.7%"),
    ("TRIAGE", "PACIENTE", "IdPaciente2 90.6%"),
    ("PROGRAMACION_CIRUGIA", "PACIENTE", "IdPaciente debil 34.4%"),
    ("PROGRAMACION_CIRUGIA", "INGRESOS", "OidIngreso debil 25.1%"),
    ("SERVICIOS", "INGRESOS", "OidIngreso 100%"),
    ("MEDICAMENTO_INSUMO", "INGRESOS", "OidIngreso 100%"),
    ("MEDICAMENTO_INSUMO", "STOCK_MEDICAMENTOS", "CodigoServicio (agregado)"),
    ("INGRESOS", "CAPACIDAD_CAMAS", "NombreGrupoCama (agregado)"),
]

FILL = "#F8CBA0"
STROKE = "#B36A26"
ROW_H = 20
HEADER_H = 30

def esc(s):
    return html.escape(s, quote=True)


def entity_label(name, cols):
    rows_html = "".join(
        f'<tr><td style="text-align:left;padding:1px 6px;">{esc(c)}</td>'
        f'<td style="text-align:right;padding:1px 6px;">'
        f'{"<b>" + tag + "</b>" if tag == "PK" or tag == "PK/FK" else ("<i>" + tag + "</i>" if tag else "")}'
        f'</td></tr>'
        for c, tag in cols
    )
    return (
        f'<div style="text-align:center;"><b><u>{esc(name)}</u></b></div>'
        f'<table style="width:100%;border-collapse:collapse;font-size:11px;">{rows_html}</table>'
    )


def main():
    cid = 2
    id_of = {}
    print('<mxfile host="app.diagrams.net">')
    print('  <diagram name="Modelo relacional hackaton-fup">')
    print('    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1700" pageHeight="1400" math="0" shadow="0">')
    print('      <root>')
    print('        <mxCell id="0" />')
    print('        <mxCell id="1" parent="0" />')

    for name, width, cols in TABLES:
        this_id = str(cid); cid += 1
        id_of[name] = this_id
        x, y = POS[name]
        height = HEADER_H + ROW_H * len(cols) + 10
        label = html.escape(entity_label(name, cols), quote=True)
        style = (
            f"rounded=1;whiteSpace=wrap;html=1;fillColor={FILL};strokeColor={STROKE};"
            f"strokeWidth=2;verticalAlign=top;align=left;spacing=6;fontSize=12;"
        )
        print(f'        <mxCell id="{this_id}" value="{label}" style="{style}" vertex="1" parent="1">')
        print(f'          <mxGeometry x="{x}" y="{y}" width="{width}" height="{height}" as="geometry" />')
        print('        </mxCell>')

    for src, dst, lbl in EDGES:
        this_id = str(cid); cid += 1
        style = "edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;endArrow=block;endFill=1;strokeColor=#555555;fontSize=10;"
        print(f'        <mxCell id="{this_id}" value="{esc(lbl)}" style="{style}" edge="1" parent="1" source="{id_of[src]}" target="{id_of[dst]}">')
        print('          <mxGeometry relative="1" as="geometry" />')
        print('        </mxCell>')

    print('      </root>')
    print('    </mxGraphModel>')
    print('  </diagram>')
    print('</mxfile>')


if __name__ == "__main__":
    main()
