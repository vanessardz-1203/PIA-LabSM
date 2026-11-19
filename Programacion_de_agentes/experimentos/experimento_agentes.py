"""
Integrante 2 · Experimento comparativo de arquitecturas de agentes (Etapa 2)

Pregunta de investigación (Secundaria 1):
    ¿Qué arquitectura de agente, reactiva o basada en modelos, permite una mejor
    exploración y administración de los sectores vigilados?

Metodología:
    - Se emplea exactamente el mismo mapa industrial reproducible de la Etapa 1.
    - Para cada combinación ``(arquitectura, número de drones)`` se ejecutan
      ``REPLICAS_AGENTES`` simulaciones de ``PASOS_EXPERIMENTO_AGENTES`` pasos
      partiendo de las **mismas posiciones iniciales** y semillas equivalentes.
    - Los drones operan de forma autónoma sin coordinación inter-dron (etapa 3)
      ni relevos automáticos (etapa 4), aislando así el impacto de la arquitectura.

Uso (dentro de Docker desde la raíz del repositorio):
    python -m Programacion_de_agentes.experimentos.experimento_agentes
"""
from __future__ import annotations

import csv
import random
import statistics
from dataclasses import dataclass
from pathlib import Path

from Construccion_de_entorno import config as config_entorno
from Construccion_de_entorno.simulacion.cobertura import (
    calcular_cobertura,
    cobertura_prioritaria,
    colocar_drones_aleatorios,
)
from Construccion_de_entorno.simulacion.entorno import (
    Celda,
    Entorno,
    generar_mapa_industrial,
)

from Programacion_de_agentes import config as config_agentes
from Programacion_de_agentes.experimentos.graficas import (
    graficar_comparacion_arquitecturas,
)
from Programacion_de_agentes.simulacion.agentes import DronBase, crear_dron

RAIZ_ETAPA_2 = Path(__file__).resolve().parent.parent
RESULTADOS = RAIZ_ETAPA_2 / "resultados"

ARQUITECTURAS = ("reactivo", "basado_en_modelos")


@dataclass
class ResultadoSimulacionAgentes:
    """Resumen de métricas de una réplica de patrullaje multiagente."""

    arquitectura: str
    num_drones: int
    pasos: int
    cobertura_instantanea_media_pct: float
    cobertura_acumulada_pct: float
    cobertura_prioritaria_media_pct: float
    cobertura_prioritaria_acumulada_pct: float
    redundancia_media_pct: float
    tiempo_sin_vigilancia_medio: float
    eficiencia_patrullaje_pct: float
    curva_cobertura_acumulada: list[float]


def simular_patrullaje(
    entorno: Entorno,
    drones: list[DronBase],
    pasos: int,
    usar_linea_de_vista: bool = True,
) -> ResultadoSimulacionAgentes:
    """Ejecuta ``pasos`` iteraciones de patrullaje y calcula métricas globales.

    En cada paso:
    1. Todos los drones perciben, deciden y ejecutan su movimiento.
    2. Se evalúa la cobertura conjunta de los drones operativos en ese instante.
    3. Se actualiza la última observación global por celda para medir el tiempo
       que los sectores permanecen sin supervisión.

    Args:
        entorno: Mapa industrial sobre el que patrullan los drones.
        drones: Lista de agentes instanciados (todos de la misma arquitectura).
        pasos: Número de pasos discretos a simular (> 0).
        usar_linea_de_vista: Si ``True``, los edificios bloquean la visibilidad.

    Returns:
        Instancia de :class:`ResultadoSimulacionAgentes` con métricas agregadas
        y la curva temporal de cobertura acumulada.
    """
    if pasos <= 0:
        raise ValueError("pasos debe ser mayor a 0")
    if not drones:
        raise ValueError("Debe existir al menos un dron en la simulación")

    transitables = entorno.celdas_transitables()
    prioritarias = entorno.celdas_prioritarias()
    total_transitables = len(transitables)
    total_prioritarias = len(prioritarias)

    ultima_vista: dict[Celda, int] = {}
    cubiertas_acumuladas: set[Celda] = set()
    prioritarias_acumuladas: set[Celda] = set()

    coberturas_inst: list[float] = []
    coberturas_prio: list[float] = []
    redundancias: list[float] = []
    antiguedades_paso: list[float] = []
    curva_acumulada: list[float] = []

    radio = drones[0].radio_observacion

    for paso in range(1, pasos + 1):
        for dron in drones:
            dron.ejecutar_paso(entorno, paso=paso, usar_linea_de_vista=usar_linea_de_vista)

        posiciones_activas = [d.posicion for d in drones if d.esta_operativo]
        res = calcular_cobertura(
            entorno,
            posiciones_activas,
            radio=radio,
            usar_linea_de_vista=usar_linea_de_vista,
        )

        cubiertas_ahora = res.cubiertas
        cubiertas_acumuladas.update(cubiertas_ahora)
        if prioritarias:
            prioritarias_acumuladas.update(cubiertas_ahora & prioritarias)

        for celda in cubiertas_ahora:
            ultima_vista[celda] = paso

        suma_antiguedad = sum(
            (paso - ultima_vista[c]) if c in ultima_vista else paso
            for c in transitables
        )
        antiguedad_media = suma_antiguedad / total_transitables if total_transitables else 0.0

        coberturas_inst.append(res.cobertura * 100.0)
        coberturas_prio.append(cobertura_prioritaria(entorno, res) * 100.0)
        redundancias.append(res.cobertura_redundante * 100.0)
        antiguedades_paso.append(antiguedad_media)
        curva_acumulada.append(
            (len(cubiertas_acumuladas) / total_transitables * 100.0)
            if total_transitables
            else 0.0
        )

    posiciones_totales = sum(len(d.historial_posiciones) for d in drones)
    posiciones_unicas = sum(len(set(d.historial_posiciones)) for d in drones)
    eficiencia_pct = (
        (posiciones_unicas / posiciones_totales) * 100.0 if posiciones_totales else 0.0
    )

    return ResultadoSimulacionAgentes(
        arquitectura=drones[0].arquitectura,
        num_drones=len(drones),
        pasos=pasos,
        cobertura_instantanea_media_pct=statistics.mean(coberturas_inst),
        cobertura_acumulada_pct=curva_acumulada[-1],
        cobertura_prioritaria_media_pct=statistics.mean(coberturas_prio),
        cobertura_prioritaria_acumulada_pct=(
            len(prioritarias_acumuladas) / total_prioritarias * 100.0
            if total_prioritarias
            else 0.0
        ),
        redundancia_media_pct=statistics.mean(redundancias),
        tiempo_sin_vigilancia_medio=statistics.mean(antiguedades_paso),
        eficiencia_patrullaje_pct=eficiencia_pct,
        curva_cobertura_acumulada=curva_acumulada,
    )


def ejecutar_comparacion_arquitecturas(
    entorno: Entorno,
    drones_lista: list[int],
    pasos: int,
    replicas: int,
    radio: float = config_agentes.RADIO_OBSERVACION_AGENTE,
    bateria_inicial: float = config_agentes.BATERIA_INICIAL,
    consumo_por_paso: float = config_agentes.CONSUMO_BATERIA_PASO,
    peso_prioritario: float = config_agentes.PESO_SECTOR_PRIORITARIO,
    prob_exploracion: float = config_agentes.PROB_EXPLORACION_REACTIVA,
    semilla_base: int = config_agentes.SEMILLA_EXPERIMENTO_AGENTES,
    usar_linea_de_vista: bool = config_entorno.USAR_LINEA_DE_VISTA,
) -> tuple[list[dict[str, float | int | str]], dict[tuple[str, int], list[float]]]:
    """Compara agentes reactivos y basados en modelos bajo condiciones equivalentes."""
    filas: list[dict[str, float | int | str]] = []
    curvas_medias: dict[tuple[str, int], list[float]] = {}

    for n in drones_lista:
        posiciones_por_replica = [
            colocar_drones_aleatorios(entorno, n, random.Random(semilla_base + r))
            for r in range(replicas)
        ]

        for arquitectura in ARQUITECTURAS:
            resultados_rep: list[ResultadoSimulacionAgentes] = []
            for r, posiciones in enumerate(posiciones_por_replica):
                drones = [
                    crear_dron(
                        arquitectura=arquitectura,
                        id_dron=idx,
                        posicion=pos,
                        radio_observacion=radio,
                        bateria=bateria_inicial,
                        bateria_max=bateria_inicial,
                        consumo_por_paso=consumo_por_paso,
                        semilla=semilla_base * 10 + r * 100 + idx,
                        prob_exploracion=prob_exploracion,
                        peso_prioritario=peso_prioritario,
                    )
                    for idx, pos in enumerate(posiciones)
                ]
                resultados_rep.append(
                    simular_patrullaje(
                        entorno=entorno,
                        drones=drones,
                        pasos=pasos,
                        usar_linea_de_vista=usar_linea_de_vista,
                    )
                )

            def _media(valores: list[float]) -> float:
                return round(statistics.mean(valores), 2)

            def _desv(valores: list[float]) -> float:
                return round(statistics.stdev(valores), 2) if len(valores) > 1 else 0.0

            cob_inst = [x.cobertura_instantanea_media_pct for x in resultados_rep]
            cob_acum = [x.cobertura_acumulada_pct for x in resultados_rep]
            cob_prio = [x.cobertura_prioritaria_media_pct for x in resultados_rep]
            cob_prio_acum = [x.cobertura_prioritaria_acumulada_pct for x in resultados_rep]
            red = [x.redundancia_media_pct for x in resultados_rep]
            sin_vig = [x.tiempo_sin_vigilancia_medio for x in resultados_rep]
            efic = [x.eficiencia_patrullaje_pct for x in resultados_rep]

            filas.append({
                "arquitectura": arquitectura,
                "drones": n,
                "pasos": pasos,
                "radio": radio,
                "cobertura_inst_media_pct": _media(cob_inst),
                "cobertura_acum_media_pct": _media(cob_acum),
                "cobertura_acum_desv_pct": _desv(cob_acum),
                "cobertura_prio_media_pct": _media(cob_prio),
                "cobertura_prio_acum_pct": _media(cob_prio_acum),
                "tiempo_sin_vigilancia_medio": _media(sin_vig),
                "redundancia_media_pct": _media(red),
                "eficiencia_patrullaje_pct": _media(efic),
            })

            curvas_medias[(arquitectura, n)] = [
                round(
                    statistics.mean(rep.curva_cobertura_acumulada[t] for rep in resultados_rep),
                    2,
                )
                for t in range(pasos)
            ]

    return filas, curvas_medias


def guardar_csv(filas: list[dict[str, float | int | str]], ruta: Path) -> None:
    """Guarda la tabla de resultados experimentales en formato CSV UTF-8."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        writer.writeheader()
        writer.writerows(filas)


def imprimir_tabla(filas: list[dict[str, float | int | str]]) -> None:
    """Imprime un resumen tabular legible de la comparativa de arquitecturas."""
    encabezado = (
        f"{'arquitectura':<18} {'drones':>6} {'cob_inst%':>10} {'cob_acum%':>16} "
        f"{'cob_prio%':>10} {'sin_vig':>8} {'red%':>7} {'efic%':>7}"
    )
    print(encabezado)
    print("-" * len(encabezado))
    for f in filas:
        acum = f"{f['cobertura_acum_media_pct']:6.2f} ± {f['cobertura_acum_desv_pct']:5.2f}"
        print(
            f"{str(f['arquitectura']):<18} {int(f['drones']):>6} "
            f"{float(f['cobertura_inst_media_pct']):>10.2f} {acum:>16} "
            f"{float(f['cobertura_prio_media_pct']):>10.2f} "
            f"{float(f['tiempo_sin_vigilancia_medio']):>8.2f} "
            f"{float(f['redundancia_media_pct']):>7.2f} "
            f"{float(f['eficiencia_patrullaje_pct']):>7.2f}"
        )


def main() -> None:
    """Punto de entrada CLI para ejecutar la comparativa de Etapa 2."""
    entorno = generar_mapa_industrial(
        ancho=config_entorno.ANCHO_MAPA,
        alto=config_entorno.ALTO_MAPA,
        num_edificios=config_entorno.NUM_EDIFICIOS,
        num_recargas=config_entorno.ESTACIONES_RECARGA,
        sectores_x=config_entorno.SECTORES_X,
        sectores_y=config_entorno.SECTORES_Y,
        semilla=config_entorno.SEMILLA_MAPA,
        sectores_prioritarios=config_entorno.SECTORES_PRIORITARIOS,
        peso_prioritario=config_entorno.PESO_SECTOR_PRIORITARIO,
    )

    filas, curvas = ejecutar_comparacion_arquitecturas(
        entorno=entorno,
        drones_lista=config_agentes.DRONES_EXPERIMENTO_AGENTES,
        pasos=config_agentes.PASOS_EXPERIMENTO_AGENTES,
        replicas=config_agentes.REPLICAS_AGENTES,
        radio=config_agentes.RADIO_OBSERVACION_AGENTE,
        bateria_inicial=config_agentes.BATERIA_INICIAL,
        consumo_por_paso=config_agentes.CONSUMO_BATERIA_PASO,
        peso_prioritario=config_agentes.PESO_SECTOR_PRIORITARIO,
        prob_exploracion=config_agentes.PROB_EXPLORACION_REACTIVA,
        semilla_base=config_agentes.SEMILLA_EXPERIMENTO_AGENTES,
        usar_linea_de_vista=config_entorno.USAR_LINEA_DE_VISTA,
    )

    csv_path = RESULTADOS / "comparacion_arquitecturas.csv"
    img_path = RESULTADOS / "graficas" / "comparacion_arquitecturas.png"
    guardar_csv(filas, csv_path)
    graficar_comparacion_arquitecturas(filas, curvas, img_path)

    print("Comparación de arquitecturas (Etapa 2 · Reactivo vs. Basado en modelos):\n")
    imprimir_tabla(filas)
    print(f"\nCSV guardado en: {csv_path}")
    print(f"Gráfica guardada en: {img_path}")


if __name__ == "__main__":
    main()
