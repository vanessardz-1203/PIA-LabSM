"""
Integrante 1 · Cobertura de vigilancia

Responde cuatro preguntas:
  1. ¿Qué celdas ve un dron desde su posición? (visibilidad)
  2. ¿Qué porcentaje del mapa está vigilado? (cobertura)
  3. ¿Qué celdas nadie ve y cuáles ve más de un dron? (puntos ciegos y redundancia)
  4. ¿Qué porcentaje de los sectores prioritarios está vigilado? (cobertura prioritaria)

Modificación documentada (revisión Etapa 1):
  - `celdas_visibles` valida que la posición del dron sea transitable.
  - Se añadió `cobertura_prioritaria` para medir cobertura en sectores prioritarios.
"""
from __future__ import annotations

import math
import random
from collections import Counter
from dataclasses import dataclass

# Modificación Etapa 1: import relativo para permitir reutilización desde otras carpetas de etapa
from .entorno import Celda, Entorno


# ---- visibilidad -----------------------------------------------------------
def linea_bresenham(origen: Celda, destino: Celda) -> list[Celda]:
    """Celdas por las que pasa una línea recta entre dos puntos (algoritmo de Bresenham)."""
    x0, y0 = origen
    x1, y1 = destino
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    camino: list[Celda] = []
    while True:
        camino.append((x0, y0))
        if (x0, y0) == (x1, y1):
            return camino
        e2 = 2 * error
        if e2 >= dy:
            error += dy
            x0 += sx
        if e2 <= dx:
            error += dx
            y0 += sy


def hay_linea_de_vista(entorno: Entorno, origen: Celda, destino: Celda) -> bool:
    """True si ninguna celda intermedia entre origen y destino es un edificio."""
    intermedias = linea_bresenham(origen, destino)[1:-1]
    return not any(c in entorno.edificios for c in intermedias)


def celdas_visibles(entorno: Entorno, posicion: Celda, radio: float,
                    usar_linea_de_vista: bool = True) -> set[Celda]:
    """Celdas transitables dentro del radio de observación y con visión libre.

    Si ``posicion`` está fuera de los límites o coincide con un edificio,
    retorna un conjunto vacío.
    """
    # Modificación Etapa 1: evita calcular visibilidad desde celdas no transitables
    if not entorno.es_transitable(posicion) or radio < 0:
        return set()

    px, py = posicion
    r = math.ceil(radio)
    visibles: set[Celda] = set()
    for x in range(px - r, px + r + 1):
        for y in range(py - r, py + r + 1):
            c = (x, y)
            if not entorno.es_transitable(c):
                continue
            if math.dist(posicion, c) > radio:
                continue
            if usar_linea_de_vista and not hay_linea_de_vista(entorno, posicion, c):
                continue
            visibles.add(c)
    return visibles


# ---- cobertura -------------------------------------------------------------
@dataclass
class ResultadoCobertura:
    """Resultado de un instante: qué se vigila, cuántas veces y qué queda ciego."""
    objetivo: set[Celda]        # celdas que deben vigilarse (todas las transitables)
    veces_vista: Counter        # celda -> número de drones que la ven

    @property
    def cubiertas(self) -> set[Celda]:
        """Subconjunto de celdas objetivo observadas por al menos un dron."""
        return {c for c in self.objetivo if self.veces_vista[c] > 0}

    @property
    def puntos_ciegos(self) -> set[Celda]:
        """Subconjunto de celdas objetivo que ningún dron observa."""
        return self.objetivo - self.cubiertas

    @property
    def cobertura(self) -> float:
        """Fracción del objetivo vigilada por al menos un dron (0 a 1)."""
        return len(self.cubiertas) / len(self.objetivo) if self.objetivo else 0.0

    @property
    def cobertura_redundante(self) -> float:
        """Fracción del objetivo vigilada por al menos dos drones (0 a 1)."""
        if not self.objetivo:
            return 0.0
        vistas_dos = sum(1 for c in self.objetivo if self.veces_vista[c] >= 2)
        return vistas_dos / len(self.objetivo)

    @property
    def redundancia_media(self) -> float:
        """Promedio de drones que ven cada celda cubierta."""
        cubiertas = self.cubiertas
        if not cubiertas:
            return 0.0
        return sum(self.veces_vista[c] for c in cubiertas) / len(cubiertas)


def calcular_cobertura(entorno: Entorno, posiciones: list[Celda], radio: float,
                       usar_linea_de_vista: bool = True) -> ResultadoCobertura:
    """Une lo que ve cada dron y devuelve las métricas de cobertura."""
    veces_vista: Counter = Counter()
    for posicion in posiciones:
        veces_vista.update(celdas_visibles(entorno, posicion, radio, usar_linea_de_vista))
    return ResultadoCobertura(objetivo=entorno.celdas_transitables(), veces_vista=veces_vista)


def cobertura_por_sector(entorno: Entorno, resultado: ResultadoCobertura) -> dict[int, float]:
    """Porcentaje de cobertura (0 a 1) de cada sector."""
    salida: dict[int, float] = {}
    for sector in entorno.sectores:
        if not sector.celdas:
            continue
        cubiertas = sum(1 for c in sector.celdas if resultado.veces_vista[c] > 0)
        salida[sector.id] = cubiertas / len(sector.celdas)
    return salida


def cobertura_prioritaria(entorno: Entorno, resultado: ResultadoCobertura) -> float:
    """Fracción de cobertura (0 a 1) considerando solo sectores prioritarios.

    Modificación Etapa 1: permite cuantificar la vigilancia sobre zonas críticas.
    Retorna ``0.0`` si el entorno no define celdas prioritarias.
    """
    prioritarias = entorno.celdas_prioritarias()
    if not prioritarias:
        return 0.0
    cubiertas = sum(1 for c in prioritarias if resultado.veces_vista[c] > 0)
    return cubiertas / len(prioritarias)


# ---- colocación de drones ---------------------------------------------------
def colocar_drones_aleatorios(entorno: Entorno, n: int, rng: random.Random) -> list[Celda]:
    """Posiciona n drones en celdas transitables distintas, al azar."""
    libres = sorted(entorno.celdas_transitables())
    if n > len(libres):
        raise ValueError(f"No hay suficientes celdas libres ({len(libres)}) para {n} drones")
    return rng.sample(libres, n)
