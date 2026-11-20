"""
Integrante 3 · Experimento: pizarrón compartido vs. mensajería directa (Etapa 3)

Pregunta de investigación (Secundaria 2):
    ¿Qué mecanismo de coordinación, pizarrón compartido o mensajería directa,
    reduce más los recorridos redundantes y los conflictos de asignación?

Metodología:
    - Mismo mapa industrial reproducible de la Etapa 1 (40x30, 4 sectores,
      prioritarios 0 y 3 con peso 2).
    - Factores: mecanismo x número de drones x retraso x pérdida de mensajes.
    - Para cada combinación se ejecutan ``REPLICAS_COORD`` réplicas. En la réplica
      ``r`` ambos mecanismos usan EXACTAMENTE las mismas posiciones iniciales,
      las mismas semillas de los drones y la misma semilla del canal.
    - En ``PASO_FALLA`` cae (INACTIVO) el dron de menor id que vigila un sector
      prioritario, para medir la reasignación ante fallas.
    - Línea base "sin_coordinacion": los mismos drones sin coordinador (se
      comportan como el dron basado en modelos original del Integrante 2).

Uso (desde la raíz del repositorio):
    python -m Coordinacion_multiagente.experimentos.experimento_coordinacion
"""
from __future__ import annotations

import argparse
import csv
import os
import random
import statistics
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from Construccion_de_entorno import config as config_entorno
from Construccion_de_entorno.simulacion.cobertura import colocar_drones_aleatorios
from Construccion_de_entorno.simulacion.entorno import Celda, Entorno, generar_mapa_industrial
from Programacion_de_agentes import config as config_agentes
from Programacion_de_agentes.simulacion.agentes import EstadoOperativo

from Coordinacion_multiagente import config
from Coordinacion_multiagente.simulacion.coordinacion import (
    CanalComunicacion,
    crear_coordinador,
    evaluar_asignacion,
)
from Coordinacion_multiagente.simulacion.dron_coordinado import DronCoordinado

RAIZ_ETAPA_3 = Path(__file__).resolve().parent.parent
RESULTADOS = RAIZ_ETAPA_3 / "resultados"
LINEA_BASE = "sin_coordinacion"


def crear_entorno() -> Entorno:
    """Mapa oficial del proyecto con la configuración del Integrante 1."""
    return generar_mapa_industrial(
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


def simular_replica(
    entorno: Entorno,
    mecanismo: str,
    posiciones: list[Celda],
    replica: int,
    retraso: int,
    perdida: float,
    pasos: int = config.PASOS_EXPERIMENTO_COORD,
    paso_falla: int | None = config.PASO_FALLA,
) -> dict[str, float | int | str]:
    """Ejecuta una réplica y devuelve sus métricas."""
    drones = [
        DronCoordinado(
            i, pos, entorno=entorno,
            radio_observacion=config_agentes.RADIO_OBSERVACION_AGENTE,
            bateria=config_agentes.BATERIA_INICIAL,
            bateria_max=config_agentes.BATERIA_MAXIMA,
            consumo_por_paso=config_agentes.CONSUMO_BATERIA_PASO,
            peso_prioritario=config_agentes.PESO_SECTOR_PRIORITARIO,
            semilla=config.SEMILLA_EXPERIMENTO_COORD * 10 + replica * 100 + i,
        )
        for i, pos in enumerate(posiciones)
    ]
    coord = None
    if mecanismo != LINEA_BASE:
        canal = CanalComunicacion(retraso=retraso, prob_perdida=perdida,
                                  semilla=config.SEMILLA_CANAL + replica)
        coord = crear_coordinador(mecanismo, entorno.sectores, canal,
                                  config.PERIODO_INFORME, config.TIMEOUT_INFORME)

    transitables = entorno.celdas_transitables()
    prioritarias = entorno.celdas_prioritarias()
    total = len(transitables)
    acumuladas: set[Celda] = set()
    cob_inst: list[float] = []
    cob_prio: list[float] = []
    redund: list[float] = []
    duplicados: list[int] = []
    validos: list[bool] = []
    convergencia: int | None = None
    recuperacion: int | None = None

    for paso in range(1, pasos + 1):
        if paso_falla is not None and paso == paso_falla:
            _provocar_falla(drones, coord, entorno)

        if coord is not None:
            coord.paso(paso, drones)
            for dron in drones:
                dron.sector_asignado = coord.asignacion_de(dron.id)
            operativos = {d.id: coord.asignacion_de(d.id) for d in drones if d.esta_operativo}
            ev = evaluar_asignacion(operativos, entorno.sectores)
            duplicados.append(ev.duplicados_evitables)
            validos.append(ev.valida)
            if ev.valida and convergencia is None:
                convergencia = paso
            if (paso_falla is not None and paso >= paso_falla
                    and ev.valida and recuperacion is None):
                recuperacion = paso - paso_falla

        vistas: Counter = Counter()
        for dron in drones:
            # percepcion.celdas_visibles ya viene vacía si el dron no está operativo
            vistas.update(dron.ejecutar_paso(entorno, paso).celdas_visibles)
        cubiertas = set(vistas)
        acumuladas |= cubiertas
        cob_inst.append(len(cubiertas) / total * 100)
        cob_prio.append(len(cubiertas & prioritarias) / len(prioritarias) * 100)
        redund.append(sum(1 for k in vistas.values() if k >= 2) / total * 100)

    fila: dict[str, float | int | str] = {
        "mecanismo": mecanismo,
        "drones": len(drones),
        "retraso": retraso,
        "perdida": perdida,
        "replica": replica,
        "cobertura_inst_media_pct": statistics.mean(cob_inst),
        "cobertura_acum_pct": len(acumuladas) / total * 100,
        "cobertura_prio_media_pct": statistics.mean(cob_prio),
        "redundancia_cobertura_pct": statistics.mean(redund),
    }
    if coord is not None:
        m = coord.metricas()
        tras_falla = validos[paso_falla - 1:] if paso_falla else validos
        fila.update({
            "duplicados_evitables_medio": statistics.mean(duplicados),
            "pasos_asignacion_valida_pct": sum(validos) / len(validos) * 100,
            "pasos_convergencia": convergencia if convergencia is not None else pasos,
            # si nunca se recupera se registra el máximo posible (dato censurado)
            "recuperacion_falla": (recuperacion if recuperacion is not None
                                   else len(tras_falla)),
            "recuperado": int(recuperacion is not None),
            "cambios_sector": m["cambios_sector"],
            "expiraciones": m["expiraciones"],
            "mensajes_por_paso": int(m["enviados"]) / pasos,
            "mensajes_perdidos": m["perdidos"],
            "retraso_medio_medido": m["retraso_medio"],
        })
    return fila


def _provocar_falla(drones: list[DronCoordinado], coord, entorno: Entorno) -> None:
    """Deja INACTIVO al dron de menor id que vigila un sector prioritario.

    Sin coordinador no hay asignaciones: cae el dron de menor id que esté
    dentro de un sector prioritario (o el dron 0 si ninguno lo está).
    No se modifica el código del dron: se cambia su estado desde fuera, como
    haría el módulo de robustez del Integrante 5.
    """
    prioritarios = {s.id for s in entorno.sectores if s.prioritario}
    candidatos = []
    for d in drones:
        if not d.esta_operativo:
            continue
        if coord is not None:
            sector = coord.asignacion_de(d.id)
        else:
            s = entorno.sector_de(d.posicion)
            sector = s.id if s else None
        if sector in prioritarios:
            candidatos.append(d)
    victima = candidatos[0] if candidatos else drones[0]
    victima.estado_operativo = EstadoOperativo.INACTIVO


# ---- ejecución por configuración ------------------------------------------------
def _correr_configuracion(args: tuple) -> list[dict[str, float | int | str]]:
    mecanismo, n, retraso, perdida, replicas, pasos, paso_falla = args
    entorno = crear_entorno()
    filas = []
    for r in range(replicas):
        posiciones = colocar_drones_aleatorios(
            entorno, n, random.Random(config.SEMILLA_EXPERIMENTO_COORD + r))
        filas.append(simular_replica(entorno, mecanismo, posiciones, r,
                                     retraso, perdida, pasos, paso_falla))
    return filas


def ejecutar_experimento(
    drones_lista: list[int] = config.DRONES_EXPERIMENTO_COORD,
    retrasos: list[int] = config.RETRASOS_EXPERIMENTO,
    perdidas: list[float] = config.PERDIDAS_EXPERIMENTO,
    replicas: int = config.REPLICAS_COORD,
    pasos: int = config.PASOS_EXPERIMENTO_COORD,
    paso_falla: int | None = config.PASO_FALLA,
    procesos: int | None = None,
) -> list[dict[str, float | int | str]]:
    """Corre todas las configuraciones y devuelve las filas por réplica.

    Cada configuración usa sus propias semillas, así que repartirlas entre
    procesos no cambia los resultados (solo el tiempo de ejecución).
    """
    tareas = []
    for n in drones_lista:
        if config.INCLUIR_LINEA_BASE:
            tareas.append((LINEA_BASE, n, 0, 0.0, replicas, pasos, paso_falla))
        for retraso in retrasos:
            for perdida in perdidas:
                for mecanismo in config.MECANISMOS_EXPERIMENTO:
                    tareas.append((mecanismo, n, retraso, perdida, replicas, pasos, paso_falla))
    procesos = procesos or max(1, (os.cpu_count() or 2) - 1)
    if procesos == 1:
        resultados = [_correr_configuracion(t) for t in tareas]
    else:
        with ProcessPoolExecutor(max_workers=procesos) as pool:
            resultados = list(pool.map(_correr_configuracion, tareas))
    return [fila for bloque in resultados for fila in bloque]


METRICAS_RESUMEN = [
    "cobertura_inst_media_pct", "cobertura_acum_pct", "cobertura_prio_media_pct",
    "redundancia_cobertura_pct", "duplicados_evitables_medio",
    "pasos_asignacion_valida_pct", "pasos_convergencia", "recuperacion_falla",
    "recuperado", "cambios_sector", "expiraciones", "mensajes_por_paso",
    "mensajes_perdidos", "retraso_medio_medido",
]
CON_DESVIACION = {"cobertura_inst_media_pct", "duplicados_evitables_medio",
                  "pasos_convergencia", "recuperacion_falla", "mensajes_por_paso"}


def resumir(filas: list[dict]) -> list[dict[str, float | int | str]]:
    """Promedia (y desviación estándar en métricas clave) por configuración."""
    grupos: dict[tuple, list[dict]] = {}
    for f in filas:
        grupos.setdefault((f["mecanismo"], f["drones"], f["retraso"], f["perdida"]), []).append(f)
    resumen = []
    for (mec, n, ret, per), grupo in grupos.items():
        fila: dict[str, float | int | str] = {
            "mecanismo": mec, "drones": n,
            "retraso": "" if mec == LINEA_BASE else ret,
            "perdida": "" if mec == LINEA_BASE else per,
            "replicas": len(grupo),
        }
        for clave in METRICAS_RESUMEN:
            valores = [float(g[clave]) for g in grupo if clave in g]
            if not valores:
                fila[clave] = ""
                continue
            fila[clave] = round(statistics.mean(valores), 3)
            if clave in CON_DESVIACION:
                fila[clave + "_desv"] = (round(statistics.stdev(valores), 3)
                                         if len(valores) > 1 else 0.0)
        resumen.append(fila)
    return resumen


def guardar_csv(filas: list[dict], ruta: Path) -> None:
    """Guarda filas en CSV UTF-8 (columnas = unión de claves en orden de aparición)."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    columnas: list[str] = []
    for f in filas:
        for k in f:
            if k not in columnas:
                columnas.append(k)
    with open(ruta, "w", newline="", encoding="utf-8") as archivo:
        writer = csv.DictWriter(archivo, fieldnames=columnas, restval="")
        writer.writeheader()
        writer.writerows(filas)


def main() -> None:
    """Punto de entrada CLI."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--replicas", type=int, default=config.REPLICAS_COORD)
    parser.add_argument("--procesos", type=int, default=None,
                        help="procesos en paralelo (1 = secuencial)")
    args = parser.parse_args()

    filas = ejecutar_experimento(replicas=args.replicas, procesos=args.procesos)
    resumen = resumir(filas)
    guardar_csv(filas, RESULTADOS / "replicas_coordinacion.csv")
    guardar_csv(resumen, RESULTADOS / "comparacion_coordinacion.csv")

    from Coordinacion_multiagente.experimentos.graficas import generar_graficas
    rutas = generar_graficas(resumen, RESULTADOS / "graficas")

    print(f"Réplicas: {len(filas)} filas -> {RESULTADOS / 'replicas_coordinacion.csv'}")
    print(f"Resumen: {len(resumen)} configuraciones -> "
          f"{RESULTADOS / 'comparacion_coordinacion.csv'}")
    for ruta in rutas:
        print(f"Gráfica: {ruta}")


if __name__ == "__main__":
    main()
