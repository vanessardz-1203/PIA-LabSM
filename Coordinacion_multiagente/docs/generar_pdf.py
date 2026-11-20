"""
Genera ``Coordinacion_multiagente/docs/integrante_3_explicacion.pdf``.

Requiere ``reportlab``, que NO está en ``requirements.txt`` a propósito: el PDF
es material de estudio, no parte de la simulación. Para regenerarlo:

    python -m venv venv_pdf
    venv_pdf/Scripts/python -m pip install reportlab      (Windows)
    venv_pdf/Scripts/python Coordinacion_multiagente/docs/generar_pdf.py

Los fragmentos de código se extraen del código fuente real (con ``ast``) y las
tablas se leen del CSV de resultados, así el PDF no se desactualiza a mano.
"""
from __future__ import annotations

import ast
import csv
import re
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph,
    Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle,
)

RAIZ = Path(__file__).resolve().parents[1]
FUENTE = RAIZ / "simulacion" / "coordinacion.py"
ADAPTADOR = RAIZ / "simulacion" / "dron_coordinado.py"
PRUEBAS = RAIZ / "tests" / "test_coordinacion.py"
RESUMEN = RAIZ / "resultados" / "comparacion_coordinacion.csv"
GRAFICAS = RAIZ / "resultados" / "graficas"
SALIDA = RAIZ / "docs" / "integrante_3_explicacion.pdf"

AZUL, NARANJA, GRIS = colors.HexColor("#2a78d6"), colors.HexColor("#eb6834"), colors.HexColor("#52514e")
FONDO_CODIGO = colors.HexColor("#f4f4f2")


# ---- fuentes (Unicode completo si hay TTF disponibles) ----------------------
def registrar_fuentes() -> tuple[str, str, str]:
    candidatos = {
        "Texto": ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
        "TextoNegrita": ["C:/Windows/Fonts/arialbd.ttf",
                         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
        "Codigo": ["C:/Windows/Fonts/consola.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"],
    }
    elegidas = {}
    for nombre, rutas in candidatos.items():
        for ruta in rutas:
            if Path(ruta).exists():
                pdfmetrics.registerFont(TTFont(nombre, ruta))
                elegidas[nombre] = nombre
                break
    if len(elegidas) == 3:
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily("Texto", normal="Texto", bold="TextoNegrita",
                           italic="Texto", boldItalic="TextoNegrita")
        return "Texto", "TextoNegrita", "Codigo"
    return "Helvetica", "Helvetica-Bold", "Courier"


TEXTO, NEGRITA, CODIGO = registrar_fuentes()
base = getSampleStyleSheet()
E_TITULO = ParagraphStyle("t", parent=base["Title"], fontName=NEGRITA, fontSize=20, leading=24)
E_H1 = ParagraphStyle("h1", parent=base["Heading1"], fontName=NEGRITA, fontSize=15,
                      leading=19, spaceBefore=6, spaceAfter=8, textColor=colors.HexColor("#1b4f8f"))
E_H2 = ParagraphStyle("h2", parent=base["Heading2"], fontName=NEGRITA, fontSize=11.5,
                      leading=15, spaceBefore=8, spaceAfter=4)
E_P = ParagraphStyle("p", parent=base["BodyText"], fontName=TEXTO, fontSize=10,
                     leading=14, alignment=TA_JUSTIFY, spaceAfter=6)
E_NOTA = ParagraphStyle("nota", parent=E_P, fontSize=8.5, leading=11, textColor=GRIS)
E_CELDA = ParagraphStyle("celda", parent=E_P, fontSize=8, leading=10, alignment=0, spaceAfter=0)
E_COD = ParagraphStyle("cod", fontName=CODIGO, fontSize=8, leading=9.8)


def _nbsp(texto: str) -> str:
    # evita que "12 %" se parta entre dos líneas
    return texto.replace(" %", " %")


def P(texto: str) -> Paragraph:
    return Paragraph(_nbsp(texto), E_P)


def H1(texto: str) -> Paragraph:
    return Paragraph(texto, E_H1)


def H2(texto: str) -> Paragraph:
    return Paragraph(texto, E_H2)


def nota(texto: str) -> Paragraph:
    return Paragraph(texto, E_NOTA)


def vinetas(items: list[str]) -> ListFlowable:
    return ListFlowable([ListItem(Paragraph(_nbsp(t), E_P), leftIndent=12) for t in items],
                        bulletType="bullet", start="•", leftIndent=12, bulletFontName=TEXTO)


def codigo(texto: str) -> Table:
    """Bloque de código con fondo gris (tabla de una celda)."""
    t = Table([[Preformatted(texto.rstrip(), E_COD, maxLineLength=100)]], colWidths=[17 * cm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), FONDO_CODIGO),
                           ("BOX", (0, 0), (-1, -1), 0.4, colors.HexColor("#d5d4cf")),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    t.spaceBefore, t.spaceAfter = 4, 10
    return t


def tabla(filas: list[list], anchos: list[float], encabezado: bool = True) -> Table:
    datos = [[Paragraph(str(c), E_CELDA) for c in fila] for fila in filas]
    t = Table(datos, colWidths=anchos, repeatRows=1 if encabezado else 0)
    estilo = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d5d4cf")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if encabezado:
        estilo += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef7"))]
    t.setStyle(TableStyle(estilo))
    return t


# ---- fragmentos de código reales ---------------------------------------------
def fragmento(ruta: Path, nombre: str, quitar_docstring: bool = True,
              max_lineas: int | None = None) -> str:
    """Código fuente de una clase/función (``Clase.metodo`` también vale)."""
    fuente = ruta.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    partes = nombre.split(".")
    nodos = arbol.body
    nodo = None
    for parte in partes:
        nodo = next(n for n in nodos if getattr(n, "name", None) == parte)
        nodos = getattr(nodo, "body", [])
    lineas = fuente.splitlines()
    inicio = nodo.lineno - 1
    if getattr(nodo, "decorator_list", None):
        inicio = nodo.decorator_list[0].lineno - 1
    bloque = lineas[inicio:nodo.end_lineno]
    sangria = len(bloque[0]) - len(bloque[0].lstrip())
    bloque = [l[sangria:] for l in bloque]
    texto = "\n".join(bloque)
    if quitar_docstring:
        texto = re.sub(r'\n(\s*)"""(.|\n)*?"""\n', r"\n\1# (docstring omitido; ver el archivo)\n",
                       texto, count=1)
    if max_lineas is not None:
        filas = texto.splitlines()
        if len(filas) > max_lineas:
            texto = "\n".join(filas[:max_lineas] + ["    ...  # (continúa en el archivo)"])
    return texto


# ---- diagrama de arquitectura -------------------------------------------------
def _flecha(d: Drawing, x1, y1, x2, y2, color=GRIS) -> None:
    d.add(Line(x1, y1, x2, y2, strokeColor=color, strokeWidth=1.2))
    import math
    ang = math.atan2(y2 - y1, x2 - x1)
    a, l = 0.45, 7
    d.add(Polygon([x2, y2,
                   x2 - l * math.cos(ang - a), y2 - l * math.sin(ang - a),
                   x2 - l * math.cos(ang + a), y2 - l * math.sin(ang + a)],
                  fillColor=color, strokeColor=color))


def _caja(d: Drawing, x, y, w, h, titulo, subtitulo="", color=AZUL) -> None:
    d.add(Rect(x, y, w, h, rx=6, ry=6, fillColor=colors.white, strokeColor=color, strokeWidth=1.4))
    d.add(String(x + w / 2, y + h - 14, titulo, fontName=NEGRITA, fontSize=8.5,
                 textAnchor="middle"))
    for i, linea in enumerate(subtitulo.split("\n") if subtitulo else []):
        d.add(String(x + w / 2, y + h - 26 - i * 10, linea, fontName=TEXTO, fontSize=7,
                     textAnchor="middle", fillColor=GRIS))


def diagrama_arquitectura() -> Drawing:
    d = Drawing(17 * cm, 10.2 * cm)
    _caja(d, 10, 225, 150, 55, "Ciclo de simulación", "motor del Integrante 5\n(hoy: el experimento)", GRIS)
    _caja(d, 190, 225, 150, 55, "Drones (Integrante 2)", "id, posicion,\nestado_operativo", GRIS)
    _caja(d, 370, 225, 105, 55, "Relevos (Int. 4)", "decide cuándo\ny quién", GRIS)

    _caja(d, 120, 120, 250, 72, "CoordinadorBase (API común)",
          "paso(t, drones) · asignacion_de(id)\nsectores_libres · ultima_vigilancia\n"
          "solicitar/confirmar/rechazar_relevo · recibir")
    _caja(d, 10, 20, 150, 66, "CoordinadorPizarron", "1 tabla compartida\n1 copia por mensaje\n"
          "lectura consistente", AZUL)
    _caja(d, 330, 20, 150, 66, "CoordinadorMensajeria", "1 tabla + buzón por dron\nN-1 copias por difusión\n"
          "visiones distintas", NARANJA)
    _caja(d, 185, 20, 120, 66, "CanalComunicacion", "retraso · pérdida\nsemilla · métricas\nhook_perdida", GRIS)

    _flecha(d, 85, 225, 190, 192)          # ciclo -> coordinador
    _flecha(d, 265, 225, 255, 192)         # drones (lectura de estado)
    _flecha(d, 422, 225, 340, 192)         # relevos -> API
    _flecha(d, 190, 120, 100, 86, AZUL)    # base -> pizarrón
    _flecha(d, 300, 120, 390, 86, NARANJA) # base -> mensajería
    _flecha(d, 160, 53, 185, 53)           # pizarrón <-> canal
    _flecha(d, 330, 53, 305, 53)
    d.add(String(272, 208, "lee estado (no modifica)", fontName=TEXTO, fontSize=6.8,
                 fillColor=GRIS, textAnchor="start"))
    d.add(String(245, 6, "ambos mecanismos usan el MISMO canal y la MISMA regla elegir_sector()",
                 fontName=TEXTO, fontSize=7, textAnchor="middle", fillColor=GRIS))
    return d


# ---- resultados -----------------------------------------------------------------
def leer_resumen() -> list[dict]:
    with open(RESUMEN, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _num(v: str, dec: int = 2) -> str:
    return "" if v in ("", None) else f"{float(v):.{dec}f}"


def buscar(resumen, mecanismo, drones, retraso="", perdida=""):
    for f in resumen:
        if (f["mecanismo"] == mecanismo and int(f["drones"]) == drones
                and (retraso == "" or (f["retraso"] != "" and int(f["retraso"]) == retraso))
                and (perdida == "" or (f["perdida"] != "" and float(f["perdida"]) == perdida))):
            return f
    raise KeyError((mecanismo, drones, retraso, perdida))


def tabla_resultados(resumen, drones: int) -> Table:
    filas = [["Mecanismo", "Ret.", "Pérd.", "Redund. evitable", "Conv. (pasos)",
              "Recup. falla", "% pasos válidos", "Cob. inst. %", "Cob. redund. %", "Msj/ paso"]]
    nombres = {"pizarron": "Pizarrón", "mensajeria_directa": "Mensajería"}
    for retraso in (0, 2, 5, 10):
        for perdida in (0.0, 0.1, 0.3):
            for mec in ("pizarron", "mensajeria_directa"):
                f = buscar(resumen, mec, drones, retraso, perdida)
                filas.append([nombres[mec], retraso, f"{int(perdida * 100)} %",
                              _num(f["duplicados_evitables_medio"], 3),
                              _num(f["pasos_convergencia"], 1), _num(f["recuperacion_falla"], 1),
                              _num(f["pasos_asignacion_valida_pct"], 1),
                              _num(f["cobertura_inst_media_pct"]),
                              _num(f["redundancia_cobertura_pct"]), _num(f["mensajes_por_paso"])])
    base = buscar(resumen, "sin_coordinacion", drones)
    filas.append(["Sin coordinación", "-", "-", "-", "-", "-", "-",
                  _num(base["cobertura_inst_media_pct"]), _num(base["redundancia_cobertura_pct"]), "0"])
    anchos = [2.3 * cm, 1.3 * cm, 1.3 * cm, 1.8 * cm, 1.6 * cm, 1.6 * cm, 1.7 * cm,
              1.6 * cm, 1.7 * cm, 1.5 * cm]
    return tabla(filas, anchos)


def tabla_escalabilidad(resumen) -> Table:
    filas = [["Drones", "Msj/paso pizarrón", "Msj/paso mensajería", "Razón",
              "Cob. inst. sin coord.", "Cob. inst. pizarrón*", "Cob. inst. mensajería*"]]
    for n in sorted({int(f["drones"]) for f in resumen}):
        piz = buscar(resumen, "pizarron", n, 0, 0.0)
        men = buscar(resumen, "mensajeria_directa", n, 0, 0.0)
        base = buscar(resumen, "sin_coordinacion", n)
        piz2 = buscar(resumen, "pizarron", n, 2, 0.1)
        men2 = buscar(resumen, "mensajeria_directa", n, 2, 0.1)
        razon = float(men["mensajes_por_paso"]) / float(piz["mensajes_por_paso"])
        filas.append([n, _num(piz["mensajes_por_paso"]), _num(men["mensajes_por_paso"]),
                      f"{razon:.1f}x", _num(base["cobertura_inst_media_pct"]),
                      _num(piz2["cobertura_inst_media_pct"]), _num(men2["cobertura_inst_media_pct"])])
    return tabla(filas, [1.4 * cm, 2.4 * cm, 2.6 * cm, 1.4 * cm, 2.6 * cm, 2.6 * cm, 2.8 * cm])


def imagen(ruta: Path, ancho_cm: float = 17.0) -> Image:
    from reportlab.lib.utils import ImageReader
    w, h = ImageReader(str(ruta)).getSize()
    ancho = ancho_cm * cm
    return Image(str(ruta), width=ancho, height=ancho * h / w)


def pie_de_pagina(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont(TEXTO, 8)
    canvas.setFillColor(GRIS)
    canvas.drawString(2 * cm, 1.2 * cm, "PIA Sistemas Multiagente · Integrante 3: comunicación y coordinación")
    canvas.drawRightString(letter[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
    canvas.restoreState()


# ---- contenido ----------------------------------------------------------------
def construir_historia(resumen: list[dict]) -> list:
    h: list = []
    F = lambda nombre, **kw: codigo(fragmento(FUENTE, nombre, **kw))  # noqa: E731

    # ---------------------------------------------------------------- portada
    h += [Spacer(1, 3 * cm),
          Paragraph("Comunicación y coordinación multiagente", E_TITULO),
          Spacer(1, 0.3 * cm),
          Paragraph("Integrante 3 · Práctica 2 · PIA de Sistemas Multiagente", E_H2),
          Spacer(1, 0.6 * cm),
          P("Sistema multiagente de vigilancia inteligente mediante drones cooperativos con "
            "patrullaje y relevos autónomos."),
          P("Este documento explica, de forma ordenada y sin rodeos, qué hace el módulo "
            "<font name='%s'>Coordinacion_multiagente</font>, por qué se diseñó así, cómo se "
            "probó, qué resultados dio el experimento y cómo defenderlo." % CODIGO),
          Spacer(1, 0.5 * cm),
          tabla([["Sección", "Contenido"],
                 ["1", "Qué es el proyecto y qué parte me toca"],
                 ["2", "Conceptos base"],
                 ["3", "Arquitectura del módulo (diagrama)"],
                 ["4", "El código, pieza por pieza"],
                 ["5", "Conexión con los demás integrantes y qué falta pedirles"],
                 ["6", "Pruebas y qué verifican"],
                 ["7", "Experimento: método, tablas, gráficas y análisis"],
                 ["8", "Limitaciones"],
                 ["9", "Preguntas de defensa"],
                 ["10", "Cómo ejecutar todo"]], [2 * cm, 13 * cm]),
          PageBreak()]

    # ---------------------------------------------------------------- (a)
    h += [H1("1. El proyecto y mi parte"),
          P("El proyecto simula en Python varios <b>drones autónomos</b> que vigilan una "
            "instalación industrial representada como una cuadrícula de 40×30 celdas, dividida "
            "en <b>4 sectores</b> (2×2). Los sectores 0 y 3 son <b>prioritarios</b> (peso 2.0). "
            "El objetivo es <b>maximizar la cobertura y reducir los puntos ciegos</b>; no se busca "
            "vigilancia perfecta."),
          P("El trabajo se reparte en cinco etapas, una carpeta por integrante:"),
          tabla([["Integrante", "Etapa", "Carpeta"],
                 ["1", "Entorno y cobertura", "Construccion_de_entorno/"],
                 ["2", "Agentes y patrullaje (Práctica 1)", "Programacion_de_agentes/"],
                 ["<b>3 (yo)</b>", "<b>Comunicación y coordinación (Práctica 2)</b>",
                  "<b>Coordinacion_multiagente/</b>"],
                 ["4", "Batería y relevos", "(pendiente)"],
                 ["5", "Robustez e integración (motor)", "(pendiente)"]],
                [2.5 * cm, 7 * cm, 6.5 * cm]),
          Spacer(1, 0.3 * cm),
          P("<b>Mi responsabilidad:</b> que los drones se comuniquen y se coordinen. En concreto:"),
          vinetas(["Un <b>pizarrón compartido</b> y una <b>mensajería directa</b> (dos formas de "
                   "comunicarse) con la misma interfaz.",
                   "Compartir qué sectores se están vigilando.",
                   "Asignar sectores de forma coordinada, <b>evitando asignaciones redundantes</b> "
                   "(dos drones en el mismo sector mientras otro está vacío).",
                   "Transportar <b>solicitudes y confirmaciones de relevo</b>. Ojo: cuándo hace "
                   "falta un relevo y quién es el sustituto lo decide el Integrante 4; yo solo "
                   "llevo los mensajes.",
                   "Simular y medir <b>retrasos</b> y <b>pérdida de mensajes</b> (el Integrante 5 "
                   "los usará para probar la robustez).",
                   "Un experimento que responde la <b>pregunta secundaria 2</b>: ¿qué mecanismo, "
                   "pizarrón o mensajería directa, reduce más los recorridos redundantes y los "
                   "conflictos de asignación?"]),
          P("<b>Restricción importante:</b> los drones del Integrante 2 todavía no reciben un "
            "sector ni mensajes, y aún no existe el motor de simulación. Por eso el módulo es "
            "<b>independiente</b>: se llama desde cualquier ciclo de simulación y <b>solo lee</b> "
            "el estado de los drones, sin modificar su código."),
          PageBreak()]

    # ---------------------------------------------------------------- (b)
    h += [H1("2. Conceptos base"),
          tabla([
              ["Concepto", "Qué significa aquí"],
              ["Agente", "Entidad que percibe su entorno y actúa de forma autónoma. Cada dron es un "
               "agente: percibe (qué celdas ve), decide (a dónde moverse) y actúa (se mueve)."],
              ["Sistema multiagente", "Varios agentes que comparten un entorno. El reto es que "
               "cooperen sin estorbarse: aquí, que no vigilen todos lo mismo."],
              ["Mensaje", "Unidad de información que un agente envía a otro: quién lo envía "
               "(emisor), a quién (receptor o todos), de qué tipo es, qué dice (contenido) y "
               "cuándo se envió (paso)."],
              ["Difusión (broadcast)", "Mensaje para todos (receptor = None)."],
              ["Pizarrón compartido", "Comunicación <b>indirecta y centralizada</b>: hay una "
               "estructura común; los agentes escriben en ella y la leen. Es como el pizarrón de "
               "un salón: escribes una vez y todos lo ven."],
              ["Mensajería directa", "Comunicación <b>directa y distribuida</b>: cada agente "
               "tiene un buzón y los mensajes van de agente a agente. Para avisar a todos hay que "
               "mandar una copia a cada uno (N-1 copias)."],
              ["Retraso", "Tiempo (en pasos) entre que se envía y se recibe un mensaje. Hace que "
               "los agentes decidan con información vieja."],
              ["Pérdida", "Un mensaje que nunca llega. Se simula con una probabilidad por copia "
               "y una semilla, para que sea reproducible."],
              ["Semilla", "Número que fija la secuencia aleatoria: la misma semilla produce "
               "exactamente los mismos resultados."],
              ["Asignación", "Qué sector vigila cada dron."],
              ["Redundancia", "Esfuerzo duplicado. <b>Asignación redundante evitable</b>: dos "
               "drones en el mismo sector mientras otro está vacío. <b>Cobertura redundante</b>: "
               "celdas que ven dos o más drones a la vez."],
              ["Conflicto", "Dos drones reclaman el mismo sector al mismo tiempo (porque aún no "
               "se enteraban el uno del otro)."],
              ["Latido (heartbeat)", "Mensaje periódico que dice \"sigo vivo\". Si deja de "
               "llegar durante un tiempo (timeout), se asume que el agente falló."],
              ["Consistencia", "Que todos los agentes sepan lo mismo. El pizarrón es consistente "
               "por construcción; la mensajería no, si se pierden mensajes."],
          ], [3.5 * cm, 12.5 * cm]),
          PageBreak()]

    # ---------------------------------------------------------------- (c)
    h += [H1("3. Arquitectura del módulo"),
          P("El módulo está en capas. Abajo está el <b>canal</b> (por donde viajan los mensajes), "
            "en medio los dos <b>mecanismos</b> y arriba una <b>API común</b> que usan el ciclo "
            "de simulación y el módulo de relevos. Los drones no se modifican: el coordinador "
            "solo lee su estado."),
          diagrama_arquitectura(),
          Spacer(1, 0.3 * cm),
          tabla([["Archivo", "Qué contiene"],
                 ["simulacion/coordinacion.py", "TipoMensaje, Mensaje, CanalComunicacion, "
                  "TablaReclamos, elegir_sector, evaluar_asignacion, CoordinadorBase, "
                  "PizarronCompartido, CoordinadorPizarron, CoordinadorMensajeria, crear_coordinador"],
                 ["simulacion/dron_coordinado.py", "Adaptador temporal: dron que obedece "
                  "sector_asignado (para el experimento)"],
                 ["config.py", "Parámetros del protocolo y del experimento, con semillas fijas"],
                 ["tests/test_coordinacion.py", "44 pruebas con pytest"],
                 ["experimentos/", "experimento_coordinacion.py y graficas.py"],
                 ["resultados/", "CSV resumen, CSV por réplica y gráficas PNG"]],
                [5 * cm, 11 * cm]),
          Spacer(1, 0.3 * cm),
          P("<b>Idea central del diseño:</b> los dos mecanismos usan <b>el mismo canal</b> y "
            "<b>la misma regla de asignación</b>. Lo único que cambia es <i>dónde se guarda</i> "
            "lo que se sabe: una tabla central (pizarrón) o una tabla por dron (mensajería). "
            "Así, cuando el experimento muestra una diferencia, se debe al mecanismo y no a "
            "otro detalle del algoritmo."),
          PageBreak()]

    # ---------------------------------------------------------------- (d)
    h += [H1("4. El código, pieza por pieza"),
          H2("4.1 Tipos de mensaje y la clase Mensaje"),
          P("El enunciado pide cuatro tipos (reclamar, liberar, solicitar relevo, confirmar "
            "relevo). Agregué dos, con justificación:"),
          vinetas(["<b>INFORME_SECTOR</b>: informe periódico \"sigo vigilando el sector X\". "
                   "Con un solo mensaje se <b>comparte la información de sectores vigilados</b> "
                   "y se envía un <b>latido</b>. Sin latido no hay forma de saber que un dron se "
                   "cayó, porque un dron caído no puede avisar.",
                   "<b>RECHAZAR_RELEVO</b>: para que quien pidió relevo no espere para siempre "
                   "(caso \"no hay sustituto disponible\")."]),
          F("Mensaje"),
          P("<b>¿Por qué inmutable?</b> En la mensajería directa la misma instancia llega a "
            "varios buzones. Si un receptor pudiera cambiarla, alteraría lo que leen los demás. "
            "Por eso es <font name='%s'>frozen=True</font> y el contenido se envuelve en un "
            "<font name='%s'>MappingProxyType</font> (diccionario de solo lectura), copiándolo "
            "antes para que modificar el diccionario original tampoco lo afecte." % (CODIGO, CODIGO)),

          H2("4.2 El canal: retraso, pérdida y métricas"),
          P("Cada destinatario recibe una <b>copia independiente</b>, que se pierde con "
            "probabilidad <font name='%s'>prob_perdida</font>. Las que no se pierden se programan "
            "para llegar en <font name='%s'>paso_envio + retraso</font>." % (CODIGO, CODIGO)),
          F("CanalComunicacion.enviar"),
          P("Detalle fino: el número aleatorio se sortea <b>siempre</b>, aunque la pérdida sea 0. "
            "Así la secuencia aleatoria no cambia al variar la configuración. El "
            "<font name='%s'>hook_perdida</font> permite al Integrante 5 provocar pérdidas "
            "dirigidas (por ejemplo, aislar a un dron)." % CODIGO),
          F("CanalComunicacion.entregar"),

          H2("4.3 La tabla de reclamos: \"quién vigila qué\""),
          P("Un <b>Reclamo</b> dice \"el dron X vigila el sector S desde el paso t\". La "
            "<b>TablaReclamos</b> guarda lo que un observador sabe. En el pizarrón hay <b>una</b> "
            "tabla; en la mensajería, <b>una por dron</b>."),
          F("TablaReclamos.aplicar", max_lineas=34),
          P("Tres decisiones importantes en este método:"),
          vinetas(["Se ignoran los mensajes más viejos que el último conocido de ese emisor: si "
                   "llegan desordenados, un \"reclamar\" viejo no pisa un \"liberar\" nuevo.",
                   "Un reclamo nuevo <b>reemplaza</b> al anterior, porque un dron solo vigila un "
                   "sector. Si se pierde el \"liberar\" al cambiar de sector, no queda basura.",
                   "Se guarda el paso de <b>llegada</b> (no el de envío) para medir el tiempo sin "
                   "noticias. La primera versión usaba el de envío y, con retraso 10, un solo "
                   "informe perdido producía una falsa alarma. El experimento lo reveló "
                   "(72 cambios de sector por réplica) y se corrigió (ver la pregunta 8 de la sección 9)."]),
          F("TablaReclamos.expirar"),

          H2("4.4 La regla de asignación: evitar redundancias y resolver conflictos"),
          P("Cada sector se puntúa con <font name='%s'>clave_sector</font>; <b>menor es mejor</b>:"
            % CODIGO),
          F("clave_sector"),
          P("El primer término reparte los drones <b>en proporción al peso</b>: un sector "
            "prioritario (peso 2) con un dron tiene clave (1+1)/2 = 1.0, igual que un sector "
            "normal vacío (0+1)/1 = 1.0. El segundo término desempata a favor del <b>vacío</b>. "
            "Resultado con el mapa real: con 4 drones queda uno por sector; con 6, dos en cada "
            "prioritario y uno en cada normal."),
          P("Los <b>conflictos</b> se resuelven con una <b>precedencia</b> que todos calculan "
            "igual, sin negociar:"),
          codigo(fragmento(FUENTE, "Reclamo.precedencia")),
          F("elegir_sector"),
          P("En el sector <b>actual</b> solo cuentan los drones con más precedencia. Así, si dos "
            "drones están en el mismo sector, el que llegó antes (o el de id menor) lo ve "
            "\"libre\" y se queda, y el otro lo ve ocupado y busca otro mejor. La "
            "<b>histéresis</b> (cambiar solo si hay algo <i>estrictamente</i> mejor) evita que un "
            "dron oscile entre sectores equivalentes. Es una <b>función pura</b>: no guarda "
            "estado, así que se prueba de forma aislada."),

          H2("4.5 El ciclo por paso del coordinador"),
          F("CoordinadorBase.paso"),
          F("CoordinadorBase._actualizar_dron"),
          P("Cómo trata cada estado del dron (los estados son del Integrante 2):"),
          vinetas(["<b>INACTIVO</b> (o batería 0): no hace nada. Simula una falla: el dron no "
                   "puede avisar y los demás lo detectan por su silencio (timeout).",
                   "<b>Operativo</b>: reevalúa su sector. Si cambia, envía RECLAMAR; si no, "
                   "envía un INFORME cada <font name='%s'>periodo_informe</font> pasos." % CODIGO,
                   "<b>EN_RECARGA / RESERVA / EN_RELEVO</b>: envía LIBERAR una vez (salida "
                   "ordenada), salvo que tenga una asignación fija de relevo."]),
          P("Las decisiones son <b>simultáneas</b>: todos deciden con lo que sabían al empezar "
            "el paso, como agentes concurrentes reales. Por eso al arrancar puede haber "
            "conflictos, y desaparecen en cuanto llega la información."),

          H2("4.6 Pizarrón vs. mensajería: lo único que cambia"),
          P("Cada subclase implementa los mismos cinco métodos abstractos. Así se ve la "
            "diferencia central:"),
          codigo(fragmento(FUENTE, "CoordinadorPizarron._publicar") + "\n\n" +
                 fragmento(FUENTE, "CoordinadorPizarron._vista") + "\n\n# --- mensajería ---\n" +
                 fragmento(FUENTE, "CoordinadorMensajeria._publicar") + "\n\n" +
                 fragmento(FUENTE, "CoordinadorMensajeria._vista")),
          P("El pizarrón envía <b>una</b> copia y todos leen la <b>misma</b> tabla. La mensajería "
            "envía <b>N-1</b> copias y cada dron lee <b>su</b> tabla. Con pérdida, la primera "
            "opción pierde la información para todos o para nadie (consistente); la segunda, "
            "solo para algunos (visiones distintas). El pizarrón además puede \"caerse\" "
            "(<font name='%s'>pizarron.disponible = False</font>): es su punto débil." % CODIGO),

          H2("4.7 Relevos: solo transporte"),
          P("El Integrante 4 decide <i>cuándo</i> y <i>quién</i>. Yo ofrezco "
            "<font name='{0}'>solicitar_relevo</font>, <font name='{0}'>confirmar_relevo</font>, "
            "<font name='{0}'>rechazar_relevo</font> y <font name='{0}'>recibir</font>, que viajan "
            "por el mismo canal (con retraso y pérdida). Al confirmar, su módulo llama a "
            "<font name='{0}'>fijar_sector(sustituto, sector, paso)</font>: una asignación fija "
            "tiene la máxima precedencia, así que los demás le ceden el sector.".format(CODIGO)),
          F("CoordinadorBase.fijar_sector"),

          H2("4.8 Cómo se mide la calidad: evaluar_asignacion"),
          P("Mira la asignación \"desde fuera\" (con la verdad) y cuenta los "
            "<b>duplicados evitables</b> = min(drones sobrantes en sectores compartidos, sectores "
            "vacíos). Dos drones en un prioritario no son un error si no hay sectores vacíos. "
            "La asignación es <b>válida</b> si no hay duplicados evitables, nadie se queda sin "
            "sector y no hay un prioritario vacío que se pudiera haber cubierto."),
          F("evaluar_asignacion", max_lineas=28),

          H2("4.9 El adaptador DronCoordinado"),
          P("Los drones del Integrante 2 aún no aceptan un sector. Para el experimento creé una "
            "<b>subclase</b> en mi carpeta (no modifiqué su código). Con "
            "<font name='%s'>sector_asignado = None</font> se comporta <b>exactamente</b> igual "
            "que el original (hay una prueba que lo verifica). Con un sector asignado, va a la "
            "celda del sector que lleva más tiempo sin ver, usando la ruta más corta (BFS del "
            "Integrante 2)." % CODIGO),
          codigo(fragmento(ADAPTADOR, "DronCoordinado.decidir")),
          PageBreak()]

    # ---------------------------------------------------------------- (e)
    h += [H1("5. Conexión con los demás integrantes"),
          tabla([
              ["De quién", "Qué uso", "Cómo"],
              ["Integrante 1", "Entorno, Sector (id, celdas, prioritario, peso), "
               "generar_mapa_industrial, colocar_drones_aleatorios",
               "Import por paquete completo; los sectores definen qué se asigna y el peso decide "
               "el reparto"],
              ["Integrante 2", "EstadoOperativo, DronBase (id, posicion, estado_operativo, "
               "esta_operativo), crear_dron, DronBasadoEnModelos, BFS",
               "Solo lectura del estado; subclase propia para el experimento"],
          ], [2.6 * cm, 7 * cm, 6.4 * cm]),
          Spacer(1, 0.3 * cm),
          H2("Qué hay que pedirle a cada uno"),
          tabla([
              ["Integrante", "Petición"],
              ["1", "Corregir el import de Construccion_de_entorno/tests/test_entorno.py "
               "(<font name='%s'>from simulacion...</font> en lugar de "
               "<font name='%s'>from Construccion_de_entorno.simulacion...</font>). Desde la raíz "
               "falla con ModuleNotFoundError; solo pasa en Docker porque el Dockerfile agrega "
               "/app/Construccion_de_entorno al PYTHONPATH." % (CODIGO, CODIGO)],
              ["2", "Agregar a DronBase un atributo <b>sector_asignado: int | None = None</b> y "
               "que la estrategia basada en modelos limite sus objetivos a ese sector cuando no "
               "sea None (como hace DronCoordinado). Con eso el adaptador sobra."],
              ["4", "Usar solicitar/confirmar/rechazar_relevo y recibir para el diálogo, y "
               "fijar_sector al confirmar. Poner al saliente en EN_RECARGA libera su sector "
               "automáticamente. Ojo: EN_RELEVO no es \"operativo\" en DronBase, así que el "
               "sustituto solo conserva el sector si se fijó."],
              ["5", "En el motor: coord.paso(t, drones) antes de mover a los drones. Fallas: "
               "estado_operativo = INACTIVO. Red: canal.retraso, canal.prob_perdida, "
               "canal.hook_perdida. Caída del pizarrón: coord.pizarron.disponible = False. "
               "Agregar mi carpeta al Dockerfile y al CI (abajo)."],
          ], [2.2 * cm, 13.8 * cm]),
          H2("Líneas exactas para Docker y CI (no se modificaron)"),
          P("En <b>Dockerfile</b>, después de "
            "<font name='%s'>COPY Programacion_de_agentes /app/Programacion_de_agentes</font>:"
            % CODIGO),
          codigo("COPY Coordinacion_multiagente /app/Coordinacion_multiagente"),
          P("En <b>.github/workflows/ci.yml</b>, paso \"Verificar sintaxis de todas las etapas\":"),
          codigo("run: docker run --rm pia-drones:ci python -m compileall -q "
                 "Construccion_de_entorno Programacion_de_agentes Coordinacion_multiagente"),
          P("pytest descubre mis pruebas automáticamente. También convendría un "
            "<b>.gitignore</b> con __pycache__/ y .pytest_cache/ (el repo no tiene uno)."),
          PageBreak()]

    # ---------------------------------------------------------------- (f)
    h += [H1("6. Pruebas y qué verifican"),
          P("44 pruebas con pytest, todas aprobadas "
            "(<font name='%s'>python -m pytest Coordinacion_multiagente/tests -v</font>). Usan un "
            "<b>DronFalso</b> mínimo para aislar cada pieza y, al final, drones y mapa reales "
            "sin modificarlos." % CODIGO),
          tabla([
              ["Grupo", "Qué se verifica"],
              ["Mensaje", "Campos, difusión, inmutabilidad, copia defensiva del contenido, "
               "validación del paso y del tipo"],
              ["Canal", "Retraso fijo exacto; retraso variable dentro del rango; pérdida "
               "reproducible con semilla y cercana a la probabilidad; enviados = entregados + "
               "perdidos + pendientes; pérdida 100 %; hook_perdida; validación"],
              ["Tabla", "Reclamar, cambiar y liberar; mensajes desordenados; información de "
               "vigilancia; expiración exacta desde la llegada"],
              ["Regla", "Prefiere prioritarios; reparte según el peso; conflicto resuelto por "
               "precedencia (antigüedad e id); histéresis; asignación fija"],
              ["Evaluación", "Detecta duplicados evitables y prioritarios vacíos; acepta "
               "duplicar prioritarios cuando sobran drones"],
              ["Pizarrón", "Escritura con retraso, una sola tabla para todos, una copia por "
               "mensaje, pizarrón caído"],
              ["Mensajería", "N-1 copias por difusión, tabla por dron, visiones distintas con "
               "pérdida"],
              ["Coordinación", "Conflicto inicial (4 drones en la misma esquina) resuelto sin "
               "duplicados con retraso 0 y 3; 6 drones = 2/1/1/2; reasignación cuando un dron "
               "queda INACTIVO (no antes del timeout, sí después); liberación al recargar; "
               "convergencia con 30 % de pérdida; regresión del timeout con retraso alto"],
              ["Relevos", "Solicitud por difusión, confirmación y rechazo dirigidos, el emisor "
               "no recibe lo suyo, leer consume; fijar_sector gana el sector aunque el dron esté "
               "EN_RELEVO"],
              ["Integración", "Coordinador con crear_dron y el mapa real; el adaptador patrulla "
               "su sector y, sin sector, repite exactamente las posiciones del dron original"],
          ], [3 * cm, 13 * cm]),
          Spacer(1, 0.3 * cm),
          P("Casi todas las pruebas de coordinación se ejecutan con <b>ambos</b> mecanismos "
            "(<font name='%s'>@pytest.mark.parametrize</font>). Ejemplo:" % CODIGO),
          codigo(fragmento(PRUEBAS, "test_conflicto_inicial_se_resuelve_sin_duplicados",
                           quitar_docstring=False)),
          PageBreak()]

    # ---------------------------------------------------------------- (g)
    base4 = buscar(resumen, "sin_coordinacion", 4)
    piz4 = buscar(resumen, "pizarron", 4, 0, 0.0)
    h += [H1("7. Experimento: pizarrón vs. mensajería directa"),
          H2("7.1 Método"),
          vinetas([
              "Mapa oficial del Integrante 1 (40×30, 4 sectores, prioritarios 0 y 3 con peso 2).",
              "Factores: mecanismo × drones {3, 4, 6, 8} × retraso {0, 2, 5, 10} pasos × pérdida "
              "{0, 10, 30} %. <b>10 réplicas</b> por configuración, 150 pasos cada una "
              "(1000 simulaciones en total).",
              "<b>Mismas condiciones:</b> en la réplica r, ambos mecanismos usan las mismas "
              "posiciones iniciales, las mismas semillas de los drones y la misma semilla del "
              "canal.",
              "<b>Falla:</b> en el paso 75 cae (INACTIVO) el dron de menor id que vigila un sector "
              "prioritario, para medir la reasignación.",
              "<b>Línea base:</b> los mismos drones sin coordinador (= dron basado en modelos "
              "original).",
          ]),
          tabla([
              ["Métrica", "Significado"],
              ["Redundancia evitable", "Media por paso de drones de más en sectores compartidos "
               "mientras hay sectores vacíos (asignaciones redundantes)"],
              ["Convergencia", "Primer paso con asignación válida (efecto de los conflictos "
               "iniciales)"],
              ["Recuperación", "Pasos desde la falla hasta volver a una asignación válida"],
              ["% pasos válidos", "Porcentaje del tiempo con asignación válida"],
              ["Cobertura inst. / redundante", "% del mapa visto en cada paso / visto por 2 o "
               "más drones (recorridos duplicados)"],
              ["Mensajes por paso", "Copias enviadas por paso (costo de comunicación)"],
          ], [4 * cm, 12 * cm]),

          H2("7.2 Resultado 1: coordinar mejora la vigilancia"),
          P("Con cualquiera de los dos mecanismos (retraso 0, sin pérdida), la cobertura "
            "instantánea sube alrededor de <b>12 %%</b> frente a no coordinar y la cobertura "
            "redundante baja mucho. Con 4 drones: cobertura instantánea %s %% → %s %%, cobertura "
            "redundante %s %% → %s %% y cobertura acumulada %s %% → %s %%." % (
                _num(base4["cobertura_inst_media_pct"]), _num(piz4["cobertura_inst_media_pct"]),
                _num(base4["redundancia_cobertura_pct"]), _num(piz4["redundancia_cobertura_pct"]),
                _num(base4["cobertura_acum_pct"], 1), _num(piz4["cobertura_acum_pct"], 1))),
          P("La tabla también muestra el <b>costo</b>: la mensajería envía N-1 veces más "
            "mensajes (* cobertura con retraso 2 y 10 % de pérdida):"),
          tabla_escalabilidad(resumen),
          Spacer(1, 0.2 * cm),
          imagen(GRAFICAS / "escalabilidad_mensajes.png", 16),
          nota("Izquierda: costo en mensajes (el pizarrón crece de forma lineal, la mensajería "
               "de forma cuadrática). Centro y derecha: con retraso 5 y 30 % de pérdida."),
          PageBreak(),

          H2("7.3 Resultado 2: sin pérdida, ambos mecanismos dan la misma coordinación"),
          P("Con la misma regla y el mismo retraso, todos los drones reciben la misma "
            "información en el mismo paso, tanto si la leen del pizarrón como de su buzón. Por "
            "eso los números son <b>idénticos</b> (en las gráficas, la línea azul de 0 % queda "
            "debajo de la naranja). El mecanismo solo importa cuando la red pierde mensajes."),
          H2("7.4 Resultado 3: el retraso es lo que más afecta"),
          P("Con 4 drones y sin pérdida, de retraso 0 a 10: la redundancia evitable pasa de "
            "0.03 a 0.28; la convergencia, de 2.8 a 19 pasos; la recuperación tras la falla, de "
            "13 a 32 pasos; y el tiempo con asignación válida baja de 90 %% a 67 %%. Aun así, la "
            "cobertura instantánea casi no cambia (19.0 %% → 18.9 %%): los drones siguen "
            "vigilando, solo que con algo más de duplicación temporal.".replace("%%", "%")),
          imagen(GRAFICAS / "coordinacion_vs_retraso_4_drones.png"),
          nota("4 drones (= número de sectores, el caso más exigente). Color = mecanismo; tipo "
               "de línea y marcador = pérdida. Línea gris discontinua = sin coordinación."),
          PageBreak(),
          H2("Tabla completa con 4 drones"),
          tabla_resultados(resumen, 4),
          nota("Medias de 10 réplicas. Redund. evitable = drones de más por paso. Conv. = pasos "
               "hasta la primera asignación válida. Recup. = pasos desde la falla hasta volver a "
               "una asignación válida."),
          PageBreak(),

          H2("7.5 Resultado 4: con pérdida, ningún mecanismo domina"),
          P("Como ambos mecanismos usan las mismas semillas, se compararon <b>réplica contra "
            "réplica</b>. La mayoría de las diferencias son menores que su error estándar. Las "
            "pocas claras (más de 2 errores estándar) apuntan en direcciones distintas:"),
          vinetas([
              "<b>4 drones, retraso 5-10, pérdida 30 %: la mensajería se recupera unos 10 pasos "
              "antes</b> de la falla (14.3 vs. 24.0 y 24.0 vs. 34.0 pasos). En la mensajería hay "
              "N-1 observadores independientes y basta con que <b>uno</b> note el silencio para "
              "moverse a cubrir el sector; en el pizarrón hay un solo observador.",
              "<b>6 drones, retraso 5-10, pérdida 30 %: el pizarrón mantiene más tiempo una "
              "asignación válida</b> (94.1 % vs. 89.7 % y 91.1 % vs. 84.6 %). En la mensajería "
              "cada dron tiene una visión distinta y hay más cambios de sector (16.0 vs. 11.2 con "
              "retraso 5).",
              "La mensajería suma más expiraciones en total (8 drones, 30 %: 36 vs. 4.7), pero "
              "tiene 7 tablas en vez de 1: por observador son similares (4-5).",
          ]),
          P("Con 10 réplicas y 32 comparaciones por métrica cabe esperar 1 o 2 diferencias "
            "\"significativas\" por azar. Por eso <b>no</b> se afirma una ventaja general de "
            "ninguno en calidad de coordinación."),
          imagen(GRAFICAS / "coordinacion_vs_retraso_6_drones.png", 14.5),
          nota("6 drones: más drones que sectores. La recuperación es casi 0 porque, al caer uno "
               "de los dos drones de un prioritario, la asignación sigue siendo válida."),
          H2("7.6 Conclusión del experimento (pregunta secundaria 2)"),
          P("En este modelo, <b>ambos mecanismos reducen igual las asignaciones redundantes "
            "cuando la red es confiable</b>, y ambos superan claramente a no coordinar. Con "
            "pérdida, las diferencias son pequeñas y dependen del escenario. <b>El pizarrón logra "
            "lo mismo con N-1 veces menos mensajes</b>, por lo que es la opción más eficiente. Su "
            "debilidad (ser un punto único de falla) no se midió aquí; queda el gancho "
            "<font name='%s'>pizarron.disponible</font> para el Integrante 5. La mensajería es más "
            "cara, pero no depende de un componente central y detecta antes las fallas con pocos "
            "drones y mucha pérdida." % CODIGO),
          P("Respecto a la pregunta general: la coordinación sí <b>maximiza la cobertura y "
            "reduce los puntos ciegos</b> (+12 % de cobertura instantánea; con 4 drones la "
            "cobertura acumulada pasa de 88.6 % a 100 %), y la reasignación automática "
            "recupera la vigilancia de un sector prioritario tras la falla de un dron en todas "
            "las réplicas."),
          PageBreak()]

    # ---------------------------------------------------------------- (h)
    h += [H1("8. Limitaciones"),
          vinetas([
              "Los drones de la Etapa 2 aún no aceptan sector; el experimento usa el adaptador "
              "DronCoordinado (subclase propia).",
              "El adaptador planea rutas con el plano completo de la planta (simplificación).",
              "La batería no influye: 150 pasos × 0.5 = 75 % de consumo, nadie se descarga. Los "
              "relevos solo se probaron con pruebas unitarias, porque su lógica es del "
              "Integrante 4.",
              "En el experimento el retraso es fijo (el canal soporta retraso variable).",
              "No se simuló la caída del pizarrón ni particiones de red (hay ganchos para el "
              "Integrante 5).",
              "Solo hay 4 sectores; con más sectores la diferencia de costo sería mayor.",
              "Con 3 drones, el sector normal que queda sin dron casi no se visita: la regla "
              "prioriza los sectores prioritarios (la cobertura acumulada no mejora).",
              "Es un modelo de tiempo discreto, no una red real; 10 réplicas por configuración.",
          ]),
          PageBreak()]

    # ---------------------------------------------------------------- (i)
    preguntas = [
        ("¿Qué diferencia hay entre pizarrón y mensajería directa?",
         "El pizarrón es una estructura central: se escribe una vez y todos leen lo mismo. En la "
         "mensajería cada dron tiene su buzón y su tabla, y avisar a todos cuesta N-1 mensajes."),
        ("¿Cuál es mejor?",
         "En calidad de coordinación son equivalentes sin pérdida y parecidos con pérdida. El "
         "pizarrón es más barato (N-1 veces menos mensajes); la mensajería no tiene punto único de "
         "falla."),
        ("¿Por qué dan exactamente lo mismo sin pérdida?",
         "Porque usan la misma regla y el mismo canal: con el mismo retraso, todos reciben la "
         "misma información en el mismo paso. Fue diseñado así para aislar el efecto del "
         "mecanismo."),
        ("¿Cómo evitan que dos drones vigilen el mismo sector?",
         "Cada dron elige el sector con menor (ocupantes+1)/peso y, en un conflicto, se queda el "
         "de mayor precedencia (quien llegó antes; si empatan, el id menor). El otro ve su sector "
         "ocupado y se va."),
        ("¿Y si hay más drones que sectores?",
         "La fórmula divide entre el peso: los prioritarios (peso 2) admiten un segundo dron "
         "antes que los normales. Con 6 drones: 2, 1, 1, 2."),
        ("¿Cómo se sabe que un dron falló?",
         "Cada dron envía un INFORME cada 5 pasos (latido). Si no llega nada suyo en 15 pasos, su "
         "reclamo se borra y el sector queda libre."),
        ("¿Por qué 15 pasos?",
         "Son 3 periodos: una falsa alarma exige perder 3 informes seguidos (2.7 % con 30 % de "
         "pérdida). Más corto da falsas alarmas; más largo, detección lenta."),
        ("¿Qué error encontraron y cómo lo corrigieron?",
         "El timeout se medía desde el envío; con retraso 10 el margen real era de 5 pasos y un "
         "solo informe perdido causaba falsas alarmas (72 cambios de sector por réplica). Se "
         "cambió a medir desde la llegada y se agregó una prueba de regresión."),
        ("¿Ustedes deciden los relevos?",
         "No. El Integrante 4 decide cuándo y quién. Yo transporto solicitar, confirmar y rechazar, "
         "y ofrezco fijar_sector para concretar el cambio."),
        ("¿Por qué el Mensaje es inmutable?",
         "Porque la misma instancia llega a varios buzones; si alguien la cambiara, afectaría a "
         "los demás receptores."),
        ("¿Modificaste el código de otros integrantes?",
         "No. El coordinador solo lee el estado de los drones; para el experimento usé una "
         "subclase en mi carpeta que, sin sector, se comporta exactamente igual que el original."),
        ("¿Cómo garantizas una comparación justa?",
         "Mismas posiciones, semillas de drones y semilla del canal en ambos mecanismos para cada "
         "réplica, y comparación réplica contra réplica."),
        ("¿Cómo puede el Integrante 5 inyectar fallas de red?",
         "Cambiando canal.retraso o canal.prob_perdida en cualquier paso, con canal.hook_perdida "
         "para pérdidas dirigidas, y con pizarron.disponible = False para tirar el pizarrón."),
        ("¿Qué pasa con retraso 0?",
         "Los mensajes llegan en el mismo paso, pero las decisiones son simultáneas: al inicio "
         "puede haber un conflicto que se resuelve en el paso siguiente."),
    ]
    h += [H1("9. Posibles preguntas de defensa")]
    for i, (q, r) in enumerate(preguntas, 1):
        h.append(KeepTogether([Paragraph(f"<b>{i}. {q}</b>", E_P), P(r)]))
    h.append(PageBreak())

    # ---------------------------------------------------------------- (j)
    h += [H1("10. Cómo ejecutar todo"),
          P("Todos los comandos se ejecutan desde la <b>raíz del repositorio</b>."),
          H2("Pruebas"),
          codigo("python -m pytest Coordinacion_multiagente/tests -v"),
          H2("Experimento (genera CSV y gráficas en Coordinacion_multiagente/resultados/)"),
          codigo("python -m Coordinacion_multiagente.experimentos.experimento_coordinacion\n"
                 "# secuencial (más lento, mismos resultados):\n"
                 "python -m Coordinacion_multiagente.experimentos.experimento_coordinacion --procesos 1"),
          H2("Con Docker (cuando se agreguen las líneas del Dockerfile)"),
          codigo("docker build -t pia-drones:dev .\n"
                 "docker run --rm pia-drones:dev pytest Coordinacion_multiagente/tests -v\n"
                 "docker run --rm -v \"$PWD/Coordinacion_multiagente/resultados:"
                 "/app/Coordinacion_multiagente/resultados\" \\\n"
                 "  pia-drones:dev python -m Coordinacion_multiagente.experimentos.experimento_coordinacion"),
          H2("Regenerar este PDF (reportlab no está en requirements.txt)"),
          codigo("python -m venv venv_pdf\n"
                 "venv_pdf/Scripts/python -m pip install reportlab\n"
                 "venv_pdf/Scripts/python Coordinacion_multiagente/docs/generar_pdf.py"),
          H2("Uso mínimo desde un ciclo de simulación"),
          codigo("from Coordinacion_multiagente.simulacion.coordinacion import (\n"
                 "    CanalComunicacion, crear_coordinador)\n\n"
                 "coord = crear_coordinador(\"pizarron\", entorno.sectores,\n"
                 "                          CanalComunicacion(retraso=2, prob_perdida=0.1, semilla=7))\n"
                 "for paso in range(1, pasos + 1):\n"
                 "    coord.paso(paso, drones)\n"
                 "    for dron in drones:\n"
                 "        sector = coord.asignacion_de(dron.id)\n"
                 "        dron.ejecutar_paso(entorno, paso)"),
          ]
    return h


def main() -> None:
    resumen = leer_resumen()
    doc = SimpleDocTemplate(str(SALIDA), pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm,
                            topMargin=2 * cm, bottomMargin=2 * cm,
                            title="Integrante 3 - Comunicación y coordinación",
                            author="Integrante 3 (PIA Sistemas Multiagente)")
    historia = construir_historia(resumen)
    doc.build(historia, onFirstPage=pie_de_pagina, onLaterPages=pie_de_pagina)
    print(f"PDF generado: {SALIDA}")


if __name__ == "__main__":
    main()
