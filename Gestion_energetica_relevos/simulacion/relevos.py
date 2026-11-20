
"""Selección inteligente de drones sustitutos."""

from __future__ import annotations

from dataclasses import dataclass

from Construccion_de_entorno.simulacion.entorno import Entorno
from Programacion_de_agentes.simulacion.agentes import (
    DronBase,
    EstadoOperativo,
)

from Gestion_energetica_relevos.simulacion.energia import GestorEnergia


@dataclass
class CandidatoRelevo:
    """Información de un candidato a sustituto."""

    dron: DronBase
    distancia: int
    energia_requerida: float


def seleccionar_sustituto(
    dron_original: DronBase,
    candidatos: list[DronBase],
    entorno: Entorno,
    gestor_energia: GestorEnergia,
    pasos_vigilancia: int = 10,
) -> CandidatoRelevo | None:
    """Selecciona el sustituto viable más cercano."""

    if pasos_vigilancia < 0:
        raise ValueError("Los pasos de vigilancia no pueden ser negativos")

    opciones: list[CandidatoRelevo] = []

    for candidato in candidatos:

        # Un dron no puede sustituirse a sí mismo.
        if candidato.id == dron_original.id:
            continue

        # Solo participan drones disponibles.
        if candidato.estado_operativo != EstadoOperativo.RESERVA:
            continue

        if candidato.bateria <= 0:
            continue

        # Calculamos una ruta real, respetando los edificios.
        ruta = _buscar_ruta(
            entorno,
            candidato.posicion,
            dron_original.posicion,
        )

        if not ruta:
            continue

        distancia = len(ruta) - 1

        # Calculamos la ruta desde el relevo hacia una recarga.
        ruta_recarga = gestor_energia.ruta_recarga(
            dron_original.posicion,
            entorno,
        )

        if not ruta_recarga:
            continue

        distancia_recarga = len(ruta_recarga) - 1

        # Energía para llegar, vigilar y regresar a recargar.
        movimientos_totales = (
            distancia
            + pasos_vigilancia
            + distancia_recarga
        )

        energia_requerida = (
            movimientos_totales * candidato.consumo_por_paso
        )

        if candidato.bateria < energia_requerida:
            continue

        opciones.append(
            CandidatoRelevo(
                dron=candidato,
                distancia=distancia,
                energia_requerida=energia_requerida,
            )
        )

    if not opciones:
        return None

    return min(
        opciones,
        key=lambda opcion: (
            opcion.distancia,
            -opcion.dron.porcentaje_bateria,
            opcion.dron.id,
        ),
    )


def _buscar_ruta(
    entorno: Entorno,
    origen: tuple[int, int],
    destino: tuple[int, int],
) -> list[tuple[int, int]]:
    """Encuentra el camino más corto entre dos posiciones."""

    from collections import deque

    if not entorno.es_transitable(origen):
        return []

    if not entorno.es_transitable(destino):
        return []

    cola = deque([origen])
    anteriores = {origen: None}

    while cola:
        actual = cola.popleft()

        if actual == destino:
            ruta = []
            while actual is not None:
                ruta.append(actual)
                actual = anteriores[actual]

            return list(reversed(ruta))

        for vecino in entorno.vecinos(actual):
            if vecino not in anteriores:
                anteriores[vecino] = actual
                cola.append(vecino)

    return []


@dataclass
class ResultadoRelevo:
    """Resultado de una operación de relevo."""

    completado: bool
    dron_original_id: int
    sustituto_id: int | None
    pasos_desplazamiento: int
    motivo: str


def ejecutar_relevo(
    dron_original: DronBase,
    candidatos: list[DronBase],
    entorno: Entorno,
    gestor_energia: GestorEnergia,
    pasos_vigilancia: int = 10,
) -> ResultadoRelevo:
    """Ejecuta un relevo local entre dos drones.

    Esta primera versión no utiliza todavía el canal
    de comunicación del coordinador.
    """

    seleccionado = seleccionar_sustituto(
        dron_original=dron_original,
        candidatos=candidatos,
        entorno=entorno,
        gestor_energia=gestor_energia,
        pasos_vigilancia=pasos_vigilancia,
    )

    if seleccionado is None:
        return ResultadoRelevo(
            completado=False,
            dron_original_id=dron_original.id,
            sustituto_id=None,
            pasos_desplazamiento=0,
            motivo="No existe un sustituto viable",
        )

    sustituto = seleccionado.dron

    ruta = _buscar_ruta(
        entorno,
        sustituto.posicion,
        dron_original.posicion,
    )

    # Un dron en RESERVA no puede moverse mediante actuar().
    sustituto.estado_operativo = EstadoOperativo.ACTIVO

    pasos = 0

    for siguiente_posicion in ruta[1:]:
        if sustituto.bateria < sustituto.consumo_por_paso:
            sustituto.estado_operativo = EstadoOperativo.INACTIVO

            return ResultadoRelevo(
                completado=False,
                dron_original_id=dron_original.id,
                sustituto_id=sustituto.id,
                pasos_desplazamiento=pasos,
                motivo="El sustituto agotó su batería",
            )

        posicion_anterior = sustituto.posicion

        sustituto.actuar(siguiente_posicion, entorno)

        if sustituto.posicion == posicion_anterior:
            return ResultadoRelevo(
                completado=False,
                dron_original_id=dron_original.id,
                sustituto_id=sustituto.id,
                pasos_desplazamiento=pasos,
                motivo="El sustituto no pudo avanzar",
            )

        pasos += 1

    # El relevo solo termina si el sustituto llegó.
    if sustituto.posicion != dron_original.posicion:
        return ResultadoRelevo(
            completado=False,
            dron_original_id=dron_original.id,
            sustituto_id=sustituto.id,
            pasos_desplazamiento=pasos,
            motivo="El sustituto no llegó al destino",
        )

    sustituto.estado_operativo = EstadoOperativo.VIGILANDO
    dron_original.estado_operativo = EstadoOperativo.EN_RELEVO

    return ResultadoRelevo(
        completado=True,
        dron_original_id=dron_original.id,
        sustituto_id=sustituto.id,
        pasos_desplazamiento=pasos,
        motivo="Sustituto llegó y asumió la vigilancia",
    )


def ejecutar_relevo_coordinado(
    dron_original: DronBase,
    candidatos: list[DronBase],
    entorno: Entorno,
    gestor_energia: GestorEnergia,
    coordinador,
    sector_id: int,
    paso_actual: int = 0,
) -> ResultadoRelevo:
    """Ejecuta un relevo y actualiza la asignación del sector."""

    # Primero verificamos que el dron original
    # sea responsable del sector indicado.
    if coordinador.asignacion_de(dron_original.id) != sector_id:
        return ResultadoRelevo(
            completado=False,
            dron_original_id=dron_original.id,
            sustituto_id=None,
            pasos_desplazamiento=0,
            motivo="El dron original no tiene asignado ese sector",
        )

    # Ejecutamos el desplazamiento y el relevo local.
    resultado = ejecutar_relevo(
        dron_original=dron_original,
        candidatos=candidatos,
        entorno=entorno,
        gestor_energia=gestor_energia,
    )

    if not resultado.completado:
        return resultado

    # El sustituto ya llegó. Transferimos la responsabilidad.
    coordinador.liberar_sector(dron_original.id, paso_actual)
    coordinador.fijar_sector(
        resultado.sustituto_id,
        sector_id,
        paso_actual,
    )

    return resultado


@dataclass
class ResultadoCicloEnergetico:
    relevo_realizado: bool
    dron_original_id: int
    sustituto_id: int | None
    sector_id: int | None
    llego_a_recarga: bool
    motivo: str


def ejecutar_ciclo_energetico(
    dron_original: DronBase,
    candidatos: list[DronBase],
    entorno: Entorno,
    gestor_energia: GestorEnergia,
    coordinador,
    paso_actual: int = 0,
) -> ResultadoCicloEnergetico:
    """Detecta batería baja, ejecuta relevo y envía a recargar."""

    sector_id = coordinador.asignacion_de(dron_original.id)

    if not gestor_energia.necesita_relevo(dron_original):
        return ResultadoCicloEnergetico(
            relevo_realizado=False,
            dron_original_id=dron_original.id,
            sustituto_id=None,
            sector_id=sector_id,
            llego_a_recarga=False,
            motivo="La batería todavía es suficiente",
        )

    if sector_id is None:
        return ResultadoCicloEnergetico(
            relevo_realizado=False,
            dron_original_id=dron_original.id,
            sustituto_id=None,
            sector_id=None,
            llego_a_recarga=False,
            motivo="El dron no tiene un sector asignado",
        )

    # Primero verificamos que el original pueda
    # llegar a una estación después del relevo.
    if not gestor_energia.puede_llegar_a_recarga(
        dron_original, entorno
    ):
        return ResultadoCicloEnergetico(
            relevo_realizado=False,
            dron_original_id=dron_original.id,
            sustituto_id=None,
            sector_id=sector_id,
            llego_a_recarga=False,
            motivo="Batería insuficiente para llegar a recarga",
        )

    resultado = ejecutar_relevo_coordinado(
        dron_original=dron_original,
        candidatos=candidatos,
        entorno=entorno,
        gestor_energia=gestor_energia,
        coordinador=coordinador,
        sector_id=sector_id,
        paso_actual=paso_actual,
    )

    if not resultado.completado:
        return ResultadoCicloEnergetico(
            relevo_realizado=False,
            dron_original_id=dron_original.id,
            sustituto_id=None,
            sector_id=sector_id,
            llego_a_recarga=False,
            motivo=resultado.motivo,
        )

    llego = gestor_energia.ir_a_recargar(
        dron_original, entorno
    )

    return ResultadoCicloEnergetico(
        relevo_realizado=True,
        dron_original_id=dron_original.id,
        sustituto_id=resultado.sustituto_id,
        sector_id=sector_id,
        llego_a_recarga=llego,
        motivo=(
            "Relevo y traslado a recarga completados"
            if llego
            else "Relevo completado, traslado a recarga pendiente"
        ),
    )
