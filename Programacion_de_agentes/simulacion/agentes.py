"""
Integrante 2 · Agentes autónomos, percepción y memoria (Etapa 2)

Define el modelo de agentes dron para la simulación multiagente (Práctica 1):

- :class:`EstadoOperativo`: estados posibles del dron (compatible con etapas futuras).
- :class:`Percepcion`: instantánea inmutable de lo que el dron percibe del entorno.
- :class:`ModeloInterno`: representación interna incremental del mundo y memoria
  temporal de vigilancia utilizada por agentes basados en modelos.
- :class:`DronBase`: clase base abstracta con posición, batería, radio de
  observación, estado operativo y ciclo percepción-decisión-acción.
- :class:`DronReactivo`: arquitectura reactiva pura (sin memoria).
- :class:`DronBasadoEnModelos`: arquitectura basada en modelos con memoria y
  patrullaje inteligente mediante :mod:`Programacion_de_agentes.simulacion.patrullaje`.
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum

from Construccion_de_entorno.simulacion.cobertura import celdas_visibles
from Construccion_de_entorno.simulacion.entorno import RECARGA, Celda, Entorno

from .patrullaje import (
    DIRECCIONES_4,
    elegir_movimiento_basado_en_modelos,
    elegir_movimiento_reactivo,
)


class EstadoOperativo(str, Enum):
    """Estados operativos posibles de un dron autónomo.

    Se definen los estados contemplados en la arquitectura general del proyecto
    para asegurar compatibilidad con las etapas posteriores sin acoplar su lógica.
    """

    ACTIVO = "activo"
    VIGILANDO = "vigilando"
    EN_RECARGA = "en_recarga"
    RESERVA = "reserva"
    EN_RELEVO = "en_relevo"
    INACTIVO = "inactivo"


@dataclass(frozen=True)
class Percepcion:
    """Instantánea inmutable del entorno percibida por un dron en un paso dado.

    Atributos:
        paso: Índice discreto del paso de simulación.
        posicion: Coordenada ``(x, y)`` actual del dron.
        celdas_visibles: Celdas transitables visibles según radio y línea de vista.
        vecinos_transitables: Celdas adyacentes en 4 direcciones a las que puede moverse.
        tipos_visibles: Tipo de cada celda visible (``libre`` o ``recarga``).
        celdas_prioritarias_visibles: Subconjunto de ``celdas_visibles`` en sectores prioritarios.
        vecinos_prioritarios: Subconjunto de ``vecinos_transitables`` en sectores prioritarios.
        sector_actual: ID del sector que contiene la posición actual (o ``None``).
        en_sector_prioritario: ``True`` si la posición actual pertenece a un sector prioritario.
        bateria: Nivel actual de batería del dron.
        estado_operativo: Estado operativo actual del dron.
        dimensiones_entorno: Tupla ``(ancho, alto)`` de la cuadrícula.
    """

    paso: int
    posicion: Celda
    celdas_visibles: frozenset[Celda]
    vecinos_transitables: tuple[Celda, ...]
    tipos_visibles: dict[Celda, str]
    celdas_prioritarias_visibles: frozenset[Celda]
    vecinos_prioritarios: frozenset[Celda]
    sector_actual: int | None
    en_sector_prioritario: bool
    bateria: float
    estado_operativo: EstadoOperativo
    dimensiones_entorno: tuple[int, int]

    @property
    def esta_operativo(self) -> bool:
        """Indica si el dron tiene batería y un estado que le permite patrullar."""
        return (
            self.bateria > 0.0
            and self.estado_operativo in (EstadoOperativo.ACTIVO, EstadoOperativo.VIGILANDO)
        )


@dataclass
class ModeloInterno:
    """Memoria interna del agente basado en modelos.

    Construye progresivamente un mapa local a partir únicamente de las
    percepciones recibidas y mantiene tiempos de última observación por celda
    para estimar zonas desatendidas y fronteras por explorar.
    """

    ancho: int = 0
    alto: int = 0
    celdas_transitables_conocidas: set[Celda] = field(default_factory=set)
    obstaculos_conocidos: set[Celda] = field(default_factory=set)
    celdas_prioritarias_conocidas: set[Celda] = field(default_factory=set)
    recargas_conocidas: set[Celda] = field(default_factory=set)
    ultima_observacion: dict[Celda, int] = field(default_factory=dict)
    visitas_posicion: dict[Celda, int] = field(default_factory=dict)
    sectores_observados: dict[int, int] = field(default_factory=dict)
    paso_actual: int = 0

    def dentro_de_limites(self, c: Celda) -> bool:
        """Comprueba si una celda está dentro de las dimensiones conocidas del mapa."""
        x, y = c
        return 0 <= x < self.ancho and 0 <= y < self.alto

    def actualizar(self, percepcion: Percepcion) -> None:
        """Incorpora una nueva :class:`Percepcion` al estado interno del dron.

        Actualiza:
        - Dimensiones del mapa y paso actual.
        - Celdas transitables, prioritarias y estaciones de recarga descubiertas.
        - Obstáculos adyacentes inferidos a partir de vecinos bloqueados.
        - Instante de última observación de cada celda visible y visitas a la posición.
        """
        self.ancho, self.alto = percepcion.dimensiones_entorno
        self.paso_actual = percepcion.paso

        pos = percepcion.posicion
        self.celdas_transitables_conocidas.add(pos)
        self.celdas_transitables_conocidas.update(percepcion.celdas_visibles)
        self.celdas_transitables_conocidas.update(percepcion.vecinos_transitables)
        self.celdas_prioritarias_conocidas.update(percepcion.celdas_prioritarias_visibles)
        self.celdas_prioritarias_conocidas.update(percepcion.vecinos_prioritarios)

        # Inferir obstáculos locales: vecinos dentro de límites que no son transitables
        vecinos_validos = set(percepcion.vecinos_transitables)
        px, py = pos
        for dx, dy in DIRECCIONES_4:
            candidato = (px + dx, py + dy)
            if self.dentro_de_limites(candidato) and candidato not in vecinos_validos:
                self.obstaculos_conocidos.add(candidato)

        for celda, tipo in percepcion.tipos_visibles.items():
            if tipo == RECARGA:
                self.recargas_conocidas.add(celda)

        for celda in percepcion.celdas_visibles:
            self.ultima_observacion[celda] = percepcion.paso

        self.visitas_posicion[pos] = self.visitas_posicion.get(pos, 0) + 1
        if percepcion.sector_actual is not None:
            self.sectores_observados[percepcion.sector_actual] = percepcion.paso

    def antiguedad(self, celda: Celda) -> int:
        """Pasos transcurridos desde la última vez que ``celda`` fue observada.

        Si la celda nunca ha sido observada, retorna ``paso_actual + 1``.
        """
        if celda not in self.ultima_observacion:
            return self.paso_actual + 1
        return max(0, self.paso_actual - self.ultima_observacion[celda])

    def contar_vecinos_desconocidos(self, celda: Celda) -> int:
        """Cuenta cuántos vecinos 4-conectados de ``celda`` siguen sin clasificarse."""
        x, y = celda
        desconocidos = 0
        for dx, dy in DIRECCIONES_4:
            vecino = (x + dx, y + dy)
            if not self.dentro_de_limites(vecino):
                continue
            if (
                vecino not in self.celdas_transitables_conocidas
                and vecino not in self.obstaculos_conocidos
            ):
                desconocidos += 1
        return desconocidos

    def celdas_frontera(self) -> set[Celda]:
        """Devuelve celdas transitables conocidas adyacentes a territorio desconocido."""
        return {
            c
            for c in self.celdas_transitables_conocidas
            if self.contar_vecinos_desconocidos(c) > 0
        }


class DronBase(ABC):
    """Clase base abstracta para los agentes dron de la simulación.

    Modela el estado individual del agente (posición, batería, radio de
    observación y estado operativo) y el ciclo estándar percepción -> decisión
    -> acción.
    """

    arquitectura: str = "base"

    def __init__(
        self,
        id_dron: int,
        posicion: Celda,
        radio_observacion: float = 5.0,
        bateria: float = 100.0,
        bateria_max: float = 100.0,
        consumo_por_paso: float = 0.5,
        estado_operativo: EstadoOperativo = EstadoOperativo.VIGILANDO,
        semilla: int | None = None,
    ) -> None:
        """Inicializa un dron autónomo validando sus parámetros físicos básicos.

        Args:
            id_dron: Identificador entero único del agente.
            posicion: Coordenada inicial ``(x, y)`` dentro del mapa.
            radio_observacion: Alcance de observación euclidiano en celdas (>= 0).
            bateria: Nivel inicial de energía en ``[0, bateria_max]``.
            bateria_max: Capacidad máxima de batería (> 0).
            consumo_por_paso: Desgaste de batería por paso ejecutado (>= 0).
            estado_operativo: Estado inicial del agente.
            semilla: Semilla para el generador aleatorio interno del agente.
        """
        if radio_observacion < 0:
            raise ValueError("radio_observacion debe ser mayor o igual a 0")
        if bateria_max <= 0:
            raise ValueError("bateria_max debe ser mayor a 0")
        if not (0.0 <= bateria <= bateria_max):
            raise ValueError("bateria debe estar en el rango [0, bateria_max]")
        if consumo_por_paso < 0:
            raise ValueError("consumo_por_paso debe ser mayor o igual a 0")

        self.id: int = id_dron
        self.posicion: Celda = posicion
        self.radio_observacion: float = float(radio_observacion)
        self.bateria_max: float = float(bateria_max)
        self.bateria: float = float(bateria)
        self.consumo_por_paso: float = float(consumo_por_paso)
        self.estado_operativo: EstadoOperativo = (
            EstadoOperativo.INACTIVO if self.bateria <= 0.0 else estado_operativo
        )
        self.rng: random.Random = random.Random(semilla)

        self.pasos_ejecutados: int = 0
        self.movimientos_realizados: int = 0
        self.historial_posiciones: list[Celda] = [posicion]
        self.celdas_observadas_unicas: set[Celda] = set()

    @property
    def porcentaje_bateria(self) -> float:
        """Nivel de batería expresado como porcentaje en ``[0.0, 100.0]``."""
        return (self.bateria / self.bateria_max) * 100.0

    @property
    def esta_operativo(self) -> bool:
        """``True`` si el dron puede ejecutar acciones de patrullaje."""
        return (
            self.bateria > 0.0
            and self.estado_operativo in (EstadoOperativo.ACTIVO, EstadoOperativo.VIGILANDO)
        )

    def percibir(
        self,
        entorno: Entorno,
        paso: int,
        usar_linea_de_vista: bool = True,
    ) -> Percepcion:
        """Construye la percepción actual del dron a partir del :class:`Entorno`.

        Args:
            entorno: Mapa industrial actual.
            paso: Paso de simulación en curso.
            usar_linea_de_vista: Si es ``True``, los edificios bloquean la visión.

        Returns:
            Instancia inmutable de :class:`Percepcion`.
        """
        if self.esta_operativo:
            visibles = frozenset(
                celdas_visibles(
                    entorno,
                    self.posicion,
                    self.radio_observacion,
                    usar_linea_de_vista=usar_linea_de_vista,
                )
            )
            self.celdas_observadas_unicas.update(visibles)
        else:
            visibles = frozenset()

        vecinos = tuple(entorno.vecinos(self.posicion))
        tipos_visibles = {c: entorno.tipo_celda(c) for c in visibles}
        prioritarias_visibles = frozenset(
            c for c in visibles if entorno.es_celda_prioritaria(c)
        )
        vecinos_prioritarios = frozenset(
            v for v in vecinos if entorno.es_celda_prioritaria(v)
        )
        sector = entorno.sector_de(self.posicion)

        return Percepcion(
            paso=paso,
            posicion=self.posicion,
            celdas_visibles=visibles,
            vecinos_transitables=vecinos,
            tipos_visibles=tipos_visibles,
            celdas_prioritarias_visibles=prioritarias_visibles,
            vecinos_prioritarios=vecinos_prioritarios,
            sector_actual=sector.id if sector is not None else None,
            en_sector_prioritario=bool(sector is not None and sector.prioritario),
            bateria=self.bateria,
            estado_operativo=self.estado_operativo,
            dimensiones_entorno=(entorno.ancho, entorno.alto),
        )

    @abstractmethod
    def decidir(self, percepcion: Percepcion) -> Celda:
        """Determina la siguiente celda objetivo a partir de la percepción."""

    def actuar(self, destino: Celda, entorno: Entorno) -> bool:
        """Ejecuta el desplazamiento elegido validando límites, obstáculos y batería.

        Args:
            destino: Celda elegida por :meth:`decidir` (debe ser la posición actual
                o un vecino transitable en 4 direcciones).
            entorno: Entorno industrial donde se valida el movimiento.

        Returns:
            ``True`` si el paso operativo se ejecutó; ``False`` si el dron estaba
            inactivo o sin batería.

        Raises:
            ValueError: Si ``destino`` no es la posición actual ni un vecino transitable.
        """
        if not self.esta_operativo:
            if self.bateria <= 0.0:
                self.estado_operativo = EstadoOperativo.INACTIVO
            return False

        vecinos_validos = set(entorno.vecinos(self.posicion))
        if destino != self.posicion and destino not in vecinos_validos:
            raise ValueError(
                f"Movimiento inválido para dron {self.id}: de {self.posicion} a {destino}"
            )

        if destino != self.posicion:
            self.posicion = destino
            self.movimientos_realizados += 1

        self.pasos_ejecutados += 1
        self.historial_posiciones.append(self.posicion)

        self.bateria = max(0.0, self.bateria - self.consumo_por_paso)
        if self.bateria <= 0.0:
            self.estado_operativo = EstadoOperativo.INACTIVO
        return True

    def ejecutar_paso(
        self,
        entorno: Entorno,
        paso: int,
        usar_linea_de_vista: bool = True,
    ) -> Percepcion:
        """Ejecuta un ciclo completo: percibir -> decidir -> actuar.

        Returns:
            La :class:`Percepcion` obtenida al inicio del paso.
        """
        percepcion = self.percibir(entorno, paso, usar_linea_de_vista=usar_linea_de_vista)
        if not self.esta_operativo:
            return percepcion
        destino = self.decidir(percepcion)
        self.actuar(destino, entorno)
        return percepcion


class DronReactivo(DronBase):
    """Agente dron de arquitectura reactiva (estímulo-respuesta sin memoria).

    No conserva representación interna del mapa ni historial de sectores
    visitados; decide su movimiento exclusivamente a partir de su percepción
    inmediata mediante :func:`elegir_movimiento_reactivo`.
    """

    arquitectura: str = "reactivo"

    def __init__(
        self,
        id_dron: int,
        posicion: Celda,
        radio_observacion: float = 5.0,
        bateria: float = 100.0,
        bateria_max: float = 100.0,
        consumo_por_paso: float = 0.5,
        estado_operativo: EstadoOperativo = EstadoOperativo.VIGILANDO,
        prob_exploracion: float = 0.25,
        semilla: int | None = None,
    ) -> None:
        super().__init__(
            id_dron=id_dron,
            posicion=posicion,
            radio_observacion=radio_observacion,
            bateria=bateria,
            bateria_max=bateria_max,
            consumo_por_paso=consumo_por_paso,
            estado_operativo=estado_operativo,
            semilla=semilla,
        )
        if not (0.0 <= prob_exploracion <= 1.0):
            raise ValueError("prob_exploracion debe estar en [0.0, 1.0]")
        self.prob_exploracion: float = float(prob_exploracion)

    def decidir(self, percepcion: Percepcion) -> Celda:
        """Aplica reglas reactivas puras sobre ``percepcion``."""
        return elegir_movimiento_reactivo(
            percepcion=percepcion,
            rng=self.rng,
            prob_exploracion=self.prob_exploracion,
        )


class DronBasadoEnModelos(DronBase):
    """Agente dron de arquitectura basada en modelos con memoria interna.

    Mantiene un :class:`ModeloInterno` que actualiza con cada percepción para
    recordar zonas ya exploradas, medir cuánto tiempo lleva sin vigilancia cada
    celda, identificar sectores prioritarios y planificar rutas más cortas (BFS)
    hacia fronteras o sectores desatendidos.
    """

    arquitectura: str = "basado_en_modelos"

    def __init__(
        self,
        id_dron: int,
        posicion: Celda,
        radio_observacion: float = 5.0,
        bateria: float = 100.0,
        bateria_max: float = 100.0,
        consumo_por_paso: float = 0.5,
        estado_operativo: EstadoOperativo = EstadoOperativo.VIGILANDO,
        peso_prioritario: float = 2.0,
        semilla: int | None = None,
    ) -> None:
        super().__init__(
            id_dron=id_dron,
            posicion=posicion,
            radio_observacion=radio_observacion,
            bateria=bateria,
            bateria_max=bateria_max,
            consumo_por_paso=consumo_por_paso,
            estado_operativo=estado_operativo,
            semilla=semilla,
        )
        if peso_prioritario < 1.0:
            raise ValueError("peso_prioritario debe ser mayor o igual a 1.0")
        self.peso_prioritario: float = float(peso_prioritario)
        self.modelo: ModeloInterno = ModeloInterno()
        self.objetivo_actual: Celda | None = None
        self.objetivo_es_frontera: bool = False

    def decidir(self, percepcion: Percepcion) -> Celda:
        """Actualiza el modelo interno y planifica el siguiente paso con BFS."""
        self.modelo.actualizar(percepcion)
        siguiente, nuevo_obj, es_frontera = elegir_movimiento_basado_en_modelos(
            percepcion=percepcion,
            modelo=self.modelo,
            objetivo_actual=self.objetivo_actual,
            objetivo_es_frontera=self.objetivo_es_frontera,
            peso_prioritario=self.peso_prioritario,
            rng=self.rng,
        )
        self.objetivo_actual = nuevo_obj
        self.objetivo_es_frontera = es_frontera
        return siguiente


def crear_dron(
    arquitectura: str,
    id_dron: int,
    posicion: Celda,
    *,
    radio_observacion: float = 5.0,
    bateria: float = 100.0,
    bateria_max: float = 100.0,
    consumo_por_paso: float = 0.5,
    estado_operativo: EstadoOperativo = EstadoOperativo.VIGILANDO,
    semilla: int | None = None,
    prob_exploracion: float = 0.25,
    peso_prioritario: float = 2.0,
) -> DronBase:
    """Fábrica para instanciar drones por nombre de arquitectura.

    Args:
        arquitectura: ``"reactivo"`` o ``"basado_en_modelos"``.
        id_dron: Identificador del agente.
        posicion: Celda inicial del dron.
        radio_observacion: Radio de observación en celdas.
        bateria: Nivel inicial de batería.
        bateria_max: Capacidad máxima de batería.
        consumo_por_paso: Consumo por paso ejecutado.
        estado_operativo: Estado inicial.
        semilla: Semilla aleatoria propia del agente.
        prob_exploracion: Parámetro exclusivo de ``DronReactivo``.
        peso_prioritario: Parámetro exclusivo de ``DronBasadoEnModelos``.

    Returns:
        Instancia concreta de :class:`DronBase`.

    Raises:
        ValueError: Si ``arquitectura`` no corresponde a una arquitectura válida.
    """
    clave = arquitectura.strip().lower()
    if clave == "reactivo":
        return DronReactivo(
            id_dron=id_dron,
            posicion=posicion,
            radio_observacion=radio_observacion,
            bateria=bateria,
            bateria_max=bateria_max,
            consumo_por_paso=consumo_por_paso,
            estado_operativo=estado_operativo,
            prob_exploracion=prob_exploracion,
            semilla=semilla,
        )
    if clave == "basado_en_modelos":
        return DronBasadoEnModelos(
            id_dron=id_dron,
            posicion=posicion,
            radio_observacion=radio_observacion,
            bateria=bateria,
            bateria_max=bateria_max,
            consumo_por_paso=consumo_por_paso,
            estado_operativo=estado_operativo,
            peso_prioritario=peso_prioritario,
            semilla=semilla,
        )
    raise ValueError(
        f"Arquitectura desconocida: {arquitectura!r}. "
        "Valores soportados: 'reactivo', 'basado_en_modelos'."
    )
