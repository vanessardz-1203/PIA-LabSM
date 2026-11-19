"""
Integrante 1 · Entorno industrial

Modela la instalación como una cuadrícula de celdas (x, y).
Cada celda es de uno de estos tipos:
  - LIBRE:    transitable y vigilable
  - EDIFICIO: obstáculo; no se puede volar sobre él y bloquea la visión
  - RECARGA:  estación de recarga; transitable
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field

Celda = tuple[int, int]

LIBRE = "libre"
EDIFICIO = "edificio"
RECARGA = "recarga"


@dataclass
class Sector:
    """Zona rectangular de la instalación que debe ser patrullada."""
    id: int
    celdas: set[Celda] = field(default_factory=set)


@dataclass
class Entorno:
    """Mapa industrial: dimensiones, obstáculos, recargas y sectores."""
    ancho: int
    alto: int
    edificios: set[Celda] = field(default_factory=set)
    recargas: set[Celda] = field(default_factory=set)
    sectores: list[Sector] = field(default_factory=list)

    # ---- consultas básicas ------------------------------------------------
    def dentro_de_limites(self, c: Celda) -> bool:
        x, y = c
        return 0 <= x < self.ancho and 0 <= y < self.alto

    def tipo_celda(self, c: Celda) -> str:
        if c in self.edificios:
            return EDIFICIO
        if c in self.recargas:
            return RECARGA
        return LIBRE

    def es_transitable(self, c: Celda) -> bool:
        return self.dentro_de_limites(c) and c not in self.edificios

    def celdas_transitables(self) -> set[Celda]:
        return {
            (x, y)
            for x in range(self.ancho)
            for y in range(self.alto)
            if (x, y) not in self.edificios
        }

    def vecinos(self, c: Celda) -> list[Celda]:
        """Vecinos de 4 direcciones (arriba, abajo, izquierda, derecha) transitables."""
        x, y = c
        candidatos = [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]
        return [v for v in candidatos if self.es_transitable(v)]

    def sector_de(self, c: Celda) -> Sector | None:
        for sector in self.sectores:
            if c in sector.celdas:
                return sector
        return None


# ---- generación del mapa ----------------------------------------------------
def generar_mapa_industrial(
    ancho: int = 40,
    alto: int = 30,
    num_edificios: int = 8,
    num_recargas: int = 4,
    sectores_x: int = 2,
    sectores_y: int = 2,
    semilla: int = 42,
) -> Entorno:
    """Crea un mapa reproducible: edificios, recargas y sectores."""
    rng = random.Random(semilla)
    entorno = Entorno(ancho=ancho, alto=alto)
    colocados = _colocar_edificios(entorno, num_edificios, rng)
    if colocados < num_edificios:
        raise RuntimeError(
            f"Solo se pudieron colocar {colocados} de {num_edificios} edificios. "
            "Aumenta el tamaño del mapa o reduce el número de edificios."
        )
    _colocar_recargas(entorno, num_recargas, rng)
    entorno.sectores = dividir_en_sectores(entorno, sectores_x, sectores_y)
    return entorno


def _colocar_edificios(entorno: Entorno, num: int, rng: random.Random,
                       max_intentos: int = 2000) -> int:
    """Coloca rectángulos sin tocarse y sin tocar el borde del mapa."""
    colocados = 0
    for _ in range(max_intentos):
        if colocados >= num:
            break
        ancho_b = rng.randint(3, 7)
        alto_b = rng.randint(3, 6)
        # x0 >= 1 y x0 + ancho_b - 1 <= ancho - 2: deja un pasillo perimetral libre
        x0 = rng.randint(1, entorno.ancho - ancho_b - 1)
        y0 = rng.randint(1, entorno.alto - alto_b - 1)
        bloque = {(x, y) for x in range(x0, x0 + ancho_b) for y in range(y0, y0 + alto_b)}
        # Halo de seguridad: exige al menos 1 celda libre entre edificios
        halo = {(x + dx, y + dy) for (x, y) in bloque
                for dx in (-1, 0, 1) for dy in (-1, 0, 1)}
        if halo & entorno.edificios:
            continue
        entorno.edificios |= bloque
        colocados += 1
    return colocados


def _colocar_recargas(entorno: Entorno, num: int, rng: random.Random,
                      distancia_minima: int = 6) -> None:
    """Elige celdas libres separadas al menos `distancia_minima` (distancia Manhattan)."""
    candidatas = sorted(entorno.celdas_transitables())
    rng.shuffle(candidatas)
    elegidas: list[Celda] = []
    for c in candidatas:
        if len(elegidas) >= num:
            break
        if all(abs(c[0] - e[0]) + abs(c[1] - e[1]) >= distancia_minima for e in elegidas):
            elegidas.append(c)
    entorno.recargas = set(elegidas)


def dividir_en_sectores(entorno: Entorno, sectores_x: int, sectores_y: int) -> list[Sector]:
    """Parte el mapa en una cuadrícula de sectores; cada celda pertenece a uno solo."""
    sectores = [Sector(id=i) for i in range(sectores_x * sectores_y)]
    for c in entorno.celdas_transitables():
        sx = c[0] * sectores_x // entorno.ancho
        sy = c[1] * sectores_y // entorno.alto
        sectores[sy * sectores_x + sx].celdas.add(c)
    return sectores


# ---- utilidades -------------------------------------------------------------
def es_conectado(entorno: Entorno) -> bool:
    """True si todas las celdas transitables son alcanzables entre sí (BFS)."""
    transitables = entorno.celdas_transitables()
    if not transitables:
        return True
    inicio = next(iter(transitables))
    visitadas = {inicio}
    cola = deque([inicio])
    while cola:
        actual = cola.popleft()
        for vecino in entorno.vecinos(actual):
            if vecino not in visitadas:
                visitadas.add(vecino)
                cola.append(vecino)
    return len(visitadas) == len(transitables)


def mapa_ascii(entorno: Entorno, drones: set[Celda] | None = None) -> str:
    """Representación de texto del mapa: '#' edificio, 'R' recarga, 'D' dron, '.' libre."""
    drones = drones or set()
    filas = []
    for y in range(entorno.alto):
        fila = []
        for x in range(entorno.ancho):
            c = (x, y)
            if c in drones:
                fila.append("D")
            elif c in entorno.edificios:
                fila.append("#")
            elif c in entorno.recargas:
                fila.append("R")
            else:
                fila.append(".")
        filas.append("".join(fila))
    return "\n".join(filas)
