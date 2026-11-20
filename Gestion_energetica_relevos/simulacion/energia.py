
"""Gestión energética de drones autónomos."""

from __future__ import annotations

from collections import deque

from Construccion_de_entorno.simulacion.entorno import Celda, Entorno
from Programacion_de_agentes.simulacion.agentes import (
    DronBase,
    EstadoOperativo,
)


class GestorEnergia:
    """Controla umbrales, rutas de recarga y recuperación de energía."""

    def __init__(
        self,
        umbral_preventivo: float = 35.0,
        umbral_critico: float = 20.0,
        tasa_recarga: float = 5.0,
    ) -> None:
        if not 0 <= umbral_critico < umbral_preventivo <= 100:
            raise ValueError("Los umbrales de batería no son válidos")
        if tasa_recarga <= 0:
            raise ValueError("La tasa de recarga debe ser positiva")

        self.umbral_preventivo = umbral_preventivo
        self.umbral_critico = umbral_critico
        self.tasa_recarga = tasa_recarga

    def necesita_relevo(self, dron: DronBase) -> bool:
        """Detecta si debe solicitar sustitución preventiva."""
        return dron.porcentaje_bateria <= self.umbral_preventivo

    def bateria_critica(self, dron: DronBase) -> bool:
        """Detecta un nivel de batería crítico."""
        return dron.porcentaje_bateria <= self.umbral_critico

    def ruta_recarga(
        self, posicion: Celda, entorno: Entorno
    ) -> list[Celda]:
        """Encuentra la ruta más corta hacia una estación mediante BFS."""
        if not entorno.recargas:
            return []

        cola = deque([posicion])
        anteriores: dict[Celda, Celda | None] = {posicion: None}
        destino = None

        while cola:
            actual = cola.popleft()

            if actual in entorno.recargas:
                destino = actual
                break

            for vecino in entorno.vecinos(actual):
                if vecino not in anteriores:
                    anteriores[vecino] = actual
                    cola.append(vecino)

        if destino is None:
            return []

        ruta = []
        actual: Celda | None = destino

        while actual is not None:
            ruta.append(actual)
            actual = anteriores[actual]

        return list(reversed(ruta))

    def puede_llegar_a_recarga(
        self, dron: DronBase, entorno: Entorno
    ) -> bool:
        """Comprueba si la energía alcanza para llegar a recargar."""
        ruta = self.ruta_recarga(dron.posicion, entorno)

        if not ruta:
            return False

        movimientos = len(ruta) - 1
        energia_necesaria = movimientos * dron.consumo_por_paso

        return dron.bateria >= energia_necesaria

    def recargar(self, dron: DronBase, entorno: Entorno) -> bool:
        """Recarga al dron únicamente si está en una estación."""
        if dron.posicion not in entorno.recargas:
            return False

        dron.estado_operativo = EstadoOperativo.EN_RECARGA
        dron.bateria = min(
            dron.bateria_max,
            dron.bateria + self.tasa_recarga,
        )

        if dron.bateria >= dron.bateria_max:
            dron.estado_operativo = EstadoOperativo.RESERVA

        return True

    
    def ir_a_recargar(
        self,
        dron: DronBase,
        entorno: Entorno,
    ) -> bool:
        """Mueve un dron a la estación de recarga más cercana."""

        ruta = self.ruta_recarga(dron.posicion, entorno)

        if not ruta:
            return False

        energia_necesaria = (
            (len(ruta) - 1) * dron.consumo_por_paso
        )

        if dron.bateria < energia_necesaria:
            return False

        dron.estado_operativo = EstadoOperativo.ACTIVO

        for siguiente in ruta[1:]:
            dron.actuar(siguiente, entorno)

        if dron.posicion not in entorno.recargas:
            return False

        dron.estado_operativo = EstadoOperativo.EN_RECARGA
        return True

