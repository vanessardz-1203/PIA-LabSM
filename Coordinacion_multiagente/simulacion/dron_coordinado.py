"""
Integrante 3 · Adaptador temporal: dron que obedece la asignación de sectores.

Los drones de la Etapa 2 todavía no reciben un sector asignado (``decidir()``
solo recibe la percepción). Para poder medir el efecto de la coordinación sin
modificar el código del Integrante 2, aquí se define una **subclase** de
:class:`DronBasadoEnModelos` con un atributo extra ``sector_asignado``:

- Si ``sector_asignado`` es ``None`` se comporta EXACTAMENTE como el dron
  original (delegando en ``super().decidir``). Así sirve también como línea
  base "sin coordinación" con el mismo código y las mismas semillas.
- Si tiene sector, patrulla dentro de él: elige como objetivo la celda del
  sector que lleva más tiempo sin observar (según su propia memoria) y va
  hacia ella por la ruta más corta (BFS del Integrante 2).

Este archivo es un puente. Lo ideal al integrar es que el Integrante 2 agregue
``sector_asignado`` (o un parámetro equivalente) a ``DronBase`` y que su
estrategia basada en modelos lo respete; entonces este adaptador sobra.
"""
from __future__ import annotations

from Construccion_de_entorno.simulacion.entorno import Celda, Entorno, Sector
from Programacion_de_agentes.simulacion.agentes import DronBasadoEnModelos, Percepcion
from Programacion_de_agentes.simulacion.patrullaje import (
    camino_mas_corto_bfs,
    distancia_manhattan,
)


class DronCoordinado(DronBasadoEnModelos):
    """Dron basado en modelos que, si tiene sector asignado, patrulla solo ese sector."""

    arquitectura: str = "basado_en_modelos_coordinado"

    def __init__(self, *args, entorno: Entorno, **kwargs) -> None:
        """Mismos parámetros que :class:`DronBasadoEnModelos` más ``entorno``.

        Se recibe el entorno para conocer la geometría de los sectores y planear
        rutas. Simplificación documentada: el dron conoce el plano de la
        instalación (es razonable: es un mapa fijo de la planta).
        """
        super().__init__(*args, **kwargs)
        self.sector_asignado: int | None = None
        self._sectores: dict[int, Sector] = {s.id: s for s in entorno.sectores}
        self._transitables: set[Celda] = entorno.celdas_transitables()
        self._ruta: list[Celda] = []
        self._sector_de_ruta: int | None = None

    def decidir(self, percepcion: Percepcion) -> Celda:
        """Patrulla el sector asignado o, si no tiene, se comporta como el original."""
        if self.sector_asignado is None or self.sector_asignado not in self._sectores:
            self._ruta = []
            return super().decidir(percepcion)

        self.modelo.actualizar(percepcion)
        pos = percepcion.posicion
        if self._ruta and self._ruta[0] == pos:
            self._ruta.pop(0)
        hay_que_replanear = (
            not self._ruta
            or self._sector_de_ruta != self.sector_asignado
            or self._ruta[0] not in percepcion.vecinos_transitables
            # el objetivo ya se vio: ir hasta allá ya no aporta
            or self.modelo.antiguedad(self._ruta[-1]) == 0
        )
        if hay_que_replanear:
            self._planear(pos)
        return self._ruta[0] if self._ruta else pos

    def _planear(self, pos: Celda) -> None:
        sector = self._sectores[self.sector_asignado]  # type: ignore[index]
        self._sector_de_ruta = self.sector_asignado
        candidatas = [c for c in sector.celdas if c != pos]
        if not candidatas:
            self._ruta = []
            return
        # La celda "más olvidada"; empate -> la más cercana; luego coordenadas.
        objetivo = min(
            candidatas,
            key=lambda c: (-self.modelo.antiguedad(c), distancia_manhattan(pos, c), c),
        )
        camino = camino_mas_corto_bfs(pos, objetivo, self._transitables)
        self._ruta = camino[1:] if len(camino) > 1 else []
