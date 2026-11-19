"""
Integrante 2 · Estrategias de patrullaje y navegación (Etapa 2)

Implementa las políticas de decisión de movimiento para los drones autónomos
bajo dos enfoques arquitectónicos sin coordinación inter-dron (Práctica 1):

1. **Estrategia reactiva** (`elegir_movimiento_reactivo`):
   Reglas condición-acción basadas exclusivamente en la :class:`Percepcion`
   actual (estímulo-respuesta), sin memoria de estados previos ni mapa interno.

2. **Estrategia basada en modelos** (`elegir_movimiento_basado_en_modelos`):
   Explota el :class:`ModeloInterno` del agente para:
   - Explorar celdas frontera hacia territorio todavía no observado.
   - Priorizar sectores prioritarios y zonas con mayor antigüedad sin vigilancia.
   - Planificar rutas más cortas sobre celdas transitables conocidas mediante BFS.
"""
from __future__ import annotations

import random
from collections import deque
from typing import TYPE_CHECKING

from Construccion_de_entorno.simulacion.entorno import Celda

if TYPE_CHECKING:
    from .agentes import ModeloInterno, Percepcion

# Direcciones ortogonales fijas para garantizar recorridos deterministas
DIRECCIONES_4: tuple[Celda, ...] = ((1, 0), (-1, 0), (0, 1), (0, -1))


# ---- utilidades geométricas y búsqueda de rutas (BFS) -----------------------
def distancia_manhattan(a: Celda, b: Celda) -> int:
    """Calcula la distancia Manhattan entre dos celdas de la cuadrícula."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def bfs_desde(
    origen: Celda,
    celdas_transitables: set[Celda],
) -> tuple[dict[Celda, int], dict[Celda, Celda | None]]:
    """Ejecuta una búsqueda en anchura (BFS) desde ``origen`` sobre celdas transitables.

    Calcula en una sola pasada tanto la distancia mínima (en pasos) hacia toda
    celda alcanzable como el árbol de predecesores para reconstruir rutas.

    Args:
        origen: Celda inicial del dron.
        celdas_transitables: Conjunto de celdas por las que se permite transitar.

    Returns:
        Tupla ``(distancias, padres)`` donde:
        - ``distancias[c]`` es la longitud del camino más corto de ``origen`` a ``c``.
        - ``padres[c]`` es el predecesor inmediato de ``c`` (``None`` para ``origen``).
    """
    if origen not in celdas_transitables:
        return {}, {}

    distancias: dict[Celda, int] = {origen: 0}
    padres: dict[Celda, Celda | None] = {origen: None}
    cola: deque[Celda] = deque([origen])

    while cola:
        actual = cola.popleft()
        dist_siguiente = distancias[actual] + 1
        x, y = actual
        for dx, dy in DIRECCIONES_4:
            vecino = (x + dx, y + dy)
            if vecino in celdas_transitables and vecino not in distancias:
                distancias[vecino] = dist_siguiente
                padres[vecino] = actual
                cola.append(vecino)

    return distancias, padres


def reconstruir_camino(
    origen: Celda,
    destino: Celda,
    padres: dict[Celda, Celda | None],
) -> list[Celda]:
    """Reconstruye el camino más corto desde ``origen`` hasta ``destino``.

    Args:
        origen: Celda de inicio.
        destino: Celda objetivo.
        padres: Diccionario de predecesores generado por :func:`bfs_desde`.

    Returns:
        Lista ordenada de celdas ``[origen, ..., destino]`` o lista vacía si
        ``destino`` no es alcanzable.
    """
    if destino not in padres:
        return []
    camino: list[Celda] = []
    actual: Celda | None = destino
    while actual is not None:
        camino.append(actual)
        if actual == origen:
            break
        actual = padres[actual]
    if not camino or camino[-1] != origen:
        return []
    camino.reverse()
    return camino


def camino_mas_corto_bfs(
    origen: Celda,
    destino: Celda,
    celdas_transitables: set[Celda],
) -> list[Celda]:
    """Devuelve la ruta más corta en 4 direcciones entre ``origen`` y ``destino``.

    Args:
        origen: Posición inicial.
        destino: Posición objetivo.
        celdas_transitables: Celdas transitables permitidas para planificar.

    Returns:
        Lista de celdas desde ``origen`` hasta ``destino`` (ambas inclusive),
        o lista vacía si no existe ruta.
    """
    if origen == destino and origen in celdas_transitables:
        return [origen]
    _, padres = bfs_desde(origen, celdas_transitables)
    return reconstruir_camino(origen, destino, padres)


def siguiente_paso_hacia(
    origen: Celda,
    destino: Celda,
    celdas_transitables: set[Celda],
    padres: dict[Celda, Celda | None] | None = None,
) -> Celda | None:
    """Obtiene la celda adyacente inmediata para avanzar hacia ``destino``.

    Si ya se dispone del diccionario ``padres`` (de :func:`bfs_desde`), lo
    reutiliza para evitar recomputar BFS.

    Returns:
        Siguiente celda en la ruta, ``origen`` si ya está en ``destino``, o
        ``None`` si ``destino`` es inalcanzable.
    """
    if origen == destino:
        return origen
    if padres is None:
        _, padres = bfs_desde(origen, celdas_transitables)
    camino = reconstruir_camino(origen, destino, padres)
    if len(camino) < 2:
        return None
    return camino[1]


# ---- estrategia 1: arquitectura reactiva (sin memoria) ----------------------
def elegir_movimiento_reactivo(
    percepcion: Percepcion,
    rng: random.Random,
    prob_exploracion: float = 0.25,
) -> Celda:
    """Selecciona el siguiente movimiento mediante reglas puramente reactivas.

    No almacena ni consulta historial de visitas ni mapa del entorno. Aplica
    reglas condición-acción exclusivamente sobre la :class:`Percepcion` actual:

    1. Si el dron no puede operar o no tiene vecinos transitables, permanece
       en su celda actual.
    2. Si percibe celdas prioritarias en su campo de visión pero aún no está
       rodeado completamente por ellas, con probabilidad ``1 - prob_exploracion``
       elige un vecino que minimice la distancia Manhattan hacia la celda
       prioritaria visible más cercana.
    3. En cualquier otro caso (o durante un paso de exploración aleatoria),
       elige de manera uniforme uno de los vecinos transitables disponibles.

    Args:
        percepcion: Percepción instantánea del dron.
        rng: Generador pseudoaleatorio del dron para desempates reproducibles.
        prob_exploracion: Probabilidad de elegir un vecino aleatorio aun cuando
            exista un estímulo prioritario cercano.

    Returns:
        Celda adyacente transitable o la posición actual si no puede moverse.
    """
    if not percepcion.esta_operativo or not percepcion.vecinos_transitables:
        return percepcion.posicion

    vecinos = list(percepcion.vecinos_transitables)

    # Estímulo local: acercarse a celdas prioritarias visibles si no está inmerso en ellas
    prioritarias_visibles = percepcion.celdas_prioritarias_visibles
    todos_vecinos_prioritarios = all(
        v in percepcion.vecinos_prioritarios for v in vecinos
    )
    if (
        prioritarias_visibles
        and not todos_vecinos_prioritarios
        and rng.random() >= prob_exploracion
    ):
        vecinos_prio = [v for v in vecinos if v in percepcion.vecinos_prioritarios]
        if vecinos_prio and not percepcion.en_sector_prioritario:
            return rng.choice(vecinos_prio)

        objetivo_local = min(
            prioritarias_visibles,
            key=lambda c: (distancia_manhattan(percepcion.posicion, c), c),
        )
        mejor_dist = min(distancia_manhattan(v, objetivo_local) for v in vecinos)
        mejores = [
            v for v in vecinos if distancia_manhattan(v, objetivo_local) == mejor_dist
        ]
        return rng.choice(mejores)

    return rng.choice(vecinos)


# ---- estrategia 2: arquitectura basada en modelos ---------------------------
def seleccionar_objetivo_modelo(
    posicion: Celda,
    modelo: ModeloInterno,
    distancias: dict[Celda, int],
    peso_prioritario: float = 2.0,
    factor_distancia: float = 0.35,
    rng: random.Random | None = None,
) -> tuple[Celda | None, bool]:
    """Selecciona el mejor objetivo de patrullaje a partir del modelo interno.

    Aplica dos fases jerárquicas:

    - **Fase A (Exploración de frontera):** Si existen celdas conocidas con
      vecinos adyacentes aún desconocidos y alcanzables vía BFS, selecciona la
      frontera que maximiza ``(peso * (1 + 0.5 * desconocidos)) / (1 + distancia)``.
    - **Fase B (Vigilancia por antigüedad):** Cuando ya no hay frontera
      alcanzable, evalúa todas las celdas transitables conocidas y selecciona la
      que maximiza ``((antiguedad + 1) * peso) / ((1 + factor_distancia * distancia) * (1 + 0.1 * visitas))``,
      ponderando más alto las celdas pertenecientes a sectores prioritarios.

    Args:
        posicion: Celda actual del dron.
        modelo: Estado interno actualizado del agente basado en modelos.
        distancias: Mapa ``celda -> distancia BFS`` desde ``posicion``.
        peso_prioritario: Factor multiplicador aplicado a celdas prioritarias.
        factor_distancia: Penalización progresiva por distancia en Fase B.
        rng: Generador opcional para desempatar candidatos equivalentes.

    Returns:
        Tupla ``(celda_objetivo, es_frontera)`` o ``(None, False)`` si no hay
        candidatos alcanzables distintos de ``posicion``.
    """
    # Fase A: priorizar exploración de fronteras hacia zonas no descubiertas
    frontera = [
        c for c in modelo.celdas_frontera() if c in distancias and c != posicion
    ]
    if frontera:
        mejor_puntaje = -1.0
        mejores: list[Celda] = []
        for c in sorted(frontera):
            peso = peso_prioritario if c in modelo.celdas_prioritarias_conocidas else 1.0
            desconocidos = modelo.contar_vecinos_desconocidos(c)
            puntaje = (peso * (1.0 + 0.5 * desconocidos)) / (1.0 + distancias[c])
            if puntaje > mejor_puntaje + 1e-9:
                mejor_puntaje = puntaje
                mejores = [c]
            elif abs(puntaje - mejor_puntaje) <= 1e-9:
                mejores.append(c)
        elegido = rng.choice(mejores) if rng is not None else mejores[0]
        return elegido, True

    # Fase B: patrullaje continuo priorizando antigüedad sin vigilancia y sectores prioritarios
    candidatas = [
        c for c in modelo.celdas_transitables_conocidas if c in distancias and c != posicion
    ]
    if not candidatas:
        return None, False

    mejor_puntaje = -1.0
    mejores = []
    for c in sorted(candidatas):
        antiguedad = modelo.antiguedad(c)
        peso = peso_prioritario if c in modelo.celdas_prioritarias_conocidas else 1.0
        penalizacion_visitas = 1.0 + 0.1 * modelo.visitas_posicion.get(c, 0)
        puntaje = (
            ((antiguedad + 1.0) * peso)
            / ((1.0 + factor_distancia * distancias[c]) * penalizacion_visitas)
        )
        if puntaje > mejor_puntaje + 1e-9:
            mejor_puntaje = puntaje
            mejores = [c]
        elif abs(puntaje - mejor_puntaje) <= 1e-9:
            mejores.append(c)

    elegido = rng.choice(mejores) if rng is not None else mejores[0]
    return elegido, False


def elegir_movimiento_basado_en_modelos(
    percepcion: Percepcion,
    modelo: ModeloInterno,
    objetivo_actual: Celda | None,
    objetivo_es_frontera: bool,
    peso_prioritario: float = 2.0,
    rng: random.Random | None = None,
) -> tuple[Celda, Celda | None, bool]:
    """Decide el siguiente paso usando el modelo interno, selección de objetivo y BFS.

    Mantiene persistencia de objetivo para evitar oscilaciones entre pasos:
    solo replanifica un nuevo destino cuando no existe objetivo activo, el dron
    alcanzó el objetivo, una frontera dejó de serlo, o una celda objetivo de
    re-vigilancia ya fue recién observada en el paso actual.

    Args:
        percepcion: Percepción instantánea del dron.
        modelo: Memoria espacial y temporal actualizada del dron.
        objetivo_actual: Celda destino vigente de pasos anteriores (si existe).
        objetivo_es_frontera: Indica si ``objetivo_actual`` fue elegido como frontera.
        peso_prioritario: Ponderación para sectores prioritarios.
        rng: Generador pseudoaleatorio para desempates reproducibles.

    Returns:
        Tupla ``(siguiente_celda, nuevo_objetivo, nuevo_objetivo_es_frontera)``.
    """
    if not percepcion.esta_operativo or not percepcion.vecinos_transitables:
        return percepcion.posicion, None, False

    posicion = percepcion.posicion
    distancias, padres = bfs_desde(posicion, modelo.celdas_transitables_conocidas)

    objetivo_valido = False
    if objetivo_actual is not None and objetivo_actual in distancias and objetivo_actual != posicion:
        if objetivo_es_frontera:
            objetivo_valido = modelo.contar_vecinos_desconocidos(objetivo_actual) > 0
        else:
            objetivo_valido = objetivo_actual not in percepcion.celdas_visibles

    if not objetivo_valido:
        objetivo_actual, objetivo_es_frontera = seleccionar_objetivo_modelo(
            posicion=posicion,
            modelo=modelo,
            distancias=distancias,
            peso_prioritario=peso_prioritario,
            rng=rng,
        )

    if objetivo_actual is not None:
        paso = siguiente_paso_hacia(
            posicion,
            objetivo_actual,
            modelo.celdas_transitables_conocidas,
            padres=padres,
        )
        if paso is not None and paso in percepcion.vecinos_transitables:
            return paso, objetivo_actual, objetivo_es_frontera

    vecinos = list(percepcion.vecinos_transitables)
    min_visitas = min(modelo.visitas_posicion.get(v, 0) for v in vecinos)
    candidatos = [v for v in vecinos if modelo.visitas_posicion.get(v, 0) == min_visitas]
    siguiente = rng.choice(candidatos) if rng is not None else candidatos[0]
    return siguiente, objetivo_actual, objetivo_es_frontera
