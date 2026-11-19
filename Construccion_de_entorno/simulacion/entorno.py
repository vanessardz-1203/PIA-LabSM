"""
Integrante 1 · Entorno industrial

Modela la instalación como una cuadrícula de celdas (x, y).
Cada celda es de uno de estos tipos:
  - LIBRE:    transitable y vigilable
  - EDIFICIO: obstáculo; no se puede volar sobre él y bloquea la visión
  - RECARGA:  estación de recarga; transitable

Modificación documentada (revisión Etapa 1):
  - Se incorporó soporte de sectores prioritarios (`Sector.prioritario`,
    `Sector.peso` y consultas auxiliares en `Entorno`) para cumplir con el
    requisito de la Etapa 1 manteniendo compatibilidad hacia atrás con la
    cuadrícula existente de 40 x 30 celdas.
"""
from __future__ import annotations

import random
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field

Celda = tuple[int, int]

LIBRE = "libre"
EDIFICIO = "edificio"
RECARGA = "recarga"


@dataclass
class Sector:
    """Zona rectangular de la instalación que debe ser patrullada.

    Atributos:
        id: Identificador entero único del sector dentro del entorno.
        celdas: Conjunto de celdas transitables que pertenecen al sector.
        prioritario: Indica si el sector requiere vigilancia prioritaria.
        peso: Ponderación relativa del sector (>= 1.0 en sectores prioritarios).
    """
    id: int
    celdas: set[Celda] = field(default_factory=set)
    # Modificación Etapa 1: atributos para modelar sectores prioritarios
    prioritario: bool = False
    peso: float = 1.0


@dataclass
class Entorno:
    """Mapa industrial: dimensiones, obstáculos, recargas y sectores.

    Proporciona consultas geométricas, de transitabilidad, vecindad y
    pertenencia a sectores (incluyendo sectores prioritarios).
    """
    ancho: int
    alto: int
    edificios: set[Celda] = field(default_factory=set)
    recargas: set[Celda] = field(default_factory=set)
    sectores: list[Sector] = field(default_factory=list)

    # ---- consultas básicas ------------------------------------------------
    def dentro_de_limites(self, c: Celda) -> bool:
        """Indica si la coordenada ``c`` cae dentro de ``[0, ancho) x [0, alto)``."""
        x, y = c
        return 0 <= x < self.ancho and 0 <= y < self.alto

    def tipo_celda(self, c: Celda) -> str:
        """Devuelve el tipo de celda: ``EDIFICIO``, ``RECARGA`` o ``LIBRE``."""
        if c in self.edificios:
            return EDIFICIO
        if c in self.recargas:
            return RECARGA
        return LIBRE

    def es_transitable(self, c: Celda) -> bool:
        """Retorna ``True`` si la celda está en límites y no es un edificio."""
        return self.dentro_de_limites(c) and c not in self.edificios

    def celdas_transitables(self) -> set[Celda]:
        """Devuelve el conjunto completo de celdas transitables del mapa."""
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
        """Devuelve el :class:`Sector` que contiene a ``c``, o ``None`` si no aplica."""
        for sector in self.sectores:
            if c in sector.celdas:
                return sector
        return None

    # ---- consultas de sectores prioritarios (Modificación Etapa 1) --------
    def sectores_prioritarios(self) -> list[Sector]:
        """Devuelve la lista de sectores marcados como prioritarios."""
        return [s for s in self.sectores if s.prioritario]

    def celdas_prioritarias(self) -> set[Celda]:
        """Devuelve la unión de celdas transitables en sectores prioritarios."""
        celdas: set[Celda] = set()
        for sector in self.sectores:
            if sector.prioritario:
                celdas |= sector.celdas
        return celdas

    def es_celda_prioritaria(self, c: Celda) -> bool:
        """Indica si la celda ``c`` pertenece a algún sector prioritario."""
        sector = self.sector_de(c)
        return bool(sector is not None and sector.prioritario)


# ---- generación del mapa ----------------------------------------------------
def generar_mapa_industrial(
    ancho: int = 40,
    alto: int = 30,
    num_edificios: int = 8,
    num_recargas: int = 4,
    sectores_x: int = 2,
    sectores_y: int = 2,
    semilla: int = 42,
    sectores_prioritarios: Iterable[int] | None = None,
    peso_prioritario: float = 2.0,
) -> Entorno:
    """Crea un mapa reproducible: edificios, recargas y sectores (incluyendo prioritarios).

    Args:
        ancho: Número de celdas en el eje X.
        alto: Número de celdas en el eje Y.
        num_edificios: Cantidad de obstáculos rectangulares a colocar.
        num_recargas: Cantidad de estaciones de recarga.
        sectores_x: Divisiones horizontales para formar sectores.
        sectores_y: Divisiones verticales para formar sectores.
        semilla: Semilla aleatoria para garantizar reproducibilidad.
        sectores_prioritarios: IDs de sectores marcados como prioritarios. Si es
            ``None``, se seleccionan automáticamente el primer y último sector
            (por ejemplo, ``(0, 3)`` en una partición 2x2; ``(0,)`` si solo hay uno).
        peso_prioritario: Ponderación asignada a cada sector prioritario.

    Returns:
        Instancia de :class:`Entorno` lista para simular.
    """
    rng = random.Random(semilla)
    entorno = Entorno(ancho=ancho, alto=alto)
    colocados = _colocar_edificios(entorno, num_edificios, rng)
    if colocados < num_edificios:
        raise RuntimeError(
            f"Solo se pudieron colocar {colocados} de {num_edificios} edificios. "
            "Aumenta el tamaño del mapa o reduce el número de edificios."
        )
    _colocar_recargas(entorno, num_recargas, rng)
    entorno.sectores = dividir_en_sectores(
        entorno,
        sectores_x,
        sectores_y,
        sectores_prioritarios=sectores_prioritarios,
        peso_prioritario=peso_prioritario,
    )
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


def dividir_en_sectores(
    entorno: Entorno,
    sectores_x: int,
    sectores_y: int,
    sectores_prioritarios: Iterable[int] | None = None,
    peso_prioritario: float = 2.0,
) -> list[Sector]:
    """Parte el mapa en una cuadrícula de sectores; cada celda pertenece a uno solo.

    Modificación Etapa 1: permite designar qué sectores son prioritarios y su peso.
    Si ``sectores_prioritarios`` es ``None``, marca por defecto las esquinas
    opuestas (ID ``0`` y último ID cuando existen 2 o más sectores).
    """
    total_sectores = sectores_x * sectores_y
    if total_sectores <= 0:
        raise ValueError("sectores_x y sectores_y deben ser mayores a 0")
    if peso_prioritario < 1.0:
        raise ValueError("peso_prioritario debe ser mayor o igual a 1.0")

    if sectores_prioritarios is None:
        prioritarios_ids = {0, total_sectores - 1} if total_sectores >= 2 else {0}
    else:
        prioritarios_ids = set(sectores_prioritarios)
        invalidos = {sid for sid in prioritarios_ids if not (0 <= sid < total_sectores)}
        if invalidos:
            raise ValueError(
                f"IDs de sectores prioritarios fuera de rango [0, {total_sectores - 1}]: "
                f"{sorted(invalidos)}"
            )

    sectores = [
        Sector(
            id=i,
            prioritario=(i in prioritarios_ids),
            peso=peso_prioritario if i in prioritarios_ids else 1.0,
        )
        for i in range(total_sectores)
    ]
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


def mapa_ascii(
    entorno: Entorno,
    drones: set[Celda] | None = None,
    mostrar_prioritarios: bool = False,
) -> str:
    """Representación de texto del mapa.

    Símbolos: ``#`` edificio, ``R`` recarga, ``D`` dron, ``*`` celda libre
    prioritaria (cuando ``mostrar_prioritarios=True``) y ``.`` celda libre.
    """
    drones = drones or set()
    prioritarias = entorno.celdas_prioritarias() if mostrar_prioritarios else set()
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
            elif c in prioritarias:
                fila.append("*")
            else:
                fila.append(".")
        filas.append("".join(fila))
    return "\n".join(filas)
