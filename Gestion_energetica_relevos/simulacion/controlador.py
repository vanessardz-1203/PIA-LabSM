
"""Controlador de relevos energéticos por pasos."""

from dataclasses import dataclass
from enum import Enum

from Construccion_de_entorno.simulacion.entorno import Entorno
from Programacion_de_agentes.simulacion.agentes import (
    DronBase,
    EstadoOperativo,
)
from Gestion_energetica_relevos.simulacion.energia import GestorEnergia
from Gestion_energetica_relevos.simulacion.relevos import (
    seleccionar_sustituto,
    _buscar_ruta,
)
from Coordinacion_multiagente.simulacion.coordinacion import TipoMensaje


class FaseRelevo(str, Enum):
    SOLICITADO = "solicitado"
    EN_CAMINO = "en_camino"
    COMPLETADO = "completado"
    FALLIDO = "fallido"


@dataclass
class RelevoActivo:
    original_id: int
    sustituto_id: int
    sector_id: int
    fase: FaseRelevo
    ruta: list[tuple[int, int]]
    indice_ruta: int = 0
    confirmacion_recibida: bool = False


class ControladorRelevos:
    """Administra relevos sin mover drones instantáneamente."""

    def __init__(
        self,
        entorno: Entorno,
        gestor_energia: GestorEnergia,
        coordinador,
    ):
        self.entorno = entorno
        self.gestor = gestor_energia
        self.coordinador = coordinador
        self.relevos: dict[int, RelevoActivo] = {}
        self.completados = 0
        self.fallidos = 0
        self.drones_recargando = {}
        self.recargas_completadas = 0

    def iniciar(
        self,
        original: DronBase,
        candidatos: list[DronBase],
        paso: int,
    ) -> bool:
        """Selecciona sustituto y solicita relevo."""

        if original.id in self.relevos:
            return False

        if not self.gestor.necesita_relevo(original):
            return False

        sector = self.coordinador.asignacion_de(original.id)

        if sector is None:
            return False

        if not self.gestor.puede_llegar_a_recarga(
            original, self.entorno
        ):
            self.fallidos += 1
            return False

        ocupado = {
            relevo.sustituto_id
            for relevo in self.relevos.values()
        }

        disponibles = [
            dron for dron in candidatos
            if dron.id not in ocupado
        ]

        seleccionado = seleccionar_sustituto(
            original,
            disponibles,
            self.entorno,
            self.gestor,
        )

        if seleccionado is None:
            self.fallidos += 1
            return False

        sustituto = seleccionado.dron

        ruta = _buscar_ruta(
            self.entorno,
            sustituto.posicion,
            original.posicion,
        )

        if not ruta:
            self.fallidos += 1
            return False

        self.coordinador.solicitar_relevo(
            emisor=original.id,
            sector=sector,
            paso=paso,
            receptor=sustituto.id,
        )

        self.relevos[original.id] = RelevoActivo(
            original_id=original.id,
            sustituto_id=sustituto.id,
            sector_id=sector,
            fase=FaseRelevo.SOLICITADO,
            ruta=ruta,
        )

        return True

    def avanzar(
        self,
        drones: list[DronBase],
        paso: int,
    ) -> None:
        """Procesa mensajes y mueve al sustituto una celda por tick."""

        por_id = {dron.id: dron for dron in drones}

        # Primero debe ejecutarse coordinador.paso().
        mensajes = {
            dron.id: self.coordinador.recibir(dron.id)
            for dron in drones
        }

        for original_id, relevo in list(self.relevos.items()):
            original = por_id.get(original_id)
            sustituto = por_id.get(relevo.sustituto_id)

            # Comprobar que ambos drones existen.
            if original is None or sustituto is None:
                relevo.fase = FaseRelevo.FALLIDO
                self.fallidos += 1
                del self.relevos[original_id]
                continue

            # Guardar confirmaciones recibidas.
            # Pueden llegar antes de terminar el recorrido.
            for mensaje in mensajes[original.id]:
                if (
                    mensaje.tipo == TipoMensaje.CONFIRMAR_RELEVO
                    and mensaje.emisor == sustituto.id
                    and mensaje.contenido.get("sector") == relevo.sector_id
                ):
                    relevo.confirmacion_recibida = True

            # FASE 1: Esperar solicitud de relevo.
            if relevo.fase == FaseRelevo.SOLICITADO:

                solicitudes = [
                    mensaje
                    for mensaje in mensajes[sustituto.id]
                    if (
                        mensaje.tipo == TipoMensaje.SOLICITAR_RELEVO
                        and mensaje.emisor == original.id
                        and mensaje.contenido.get("sector")
                        == relevo.sector_id
                    )
                ]

                if not solicitudes:
                    continue

                # El sustituto acepta el relevo.
                self.coordinador.confirmar_relevo(
                    emisor=sustituto.id,
                    receptor=original.id,
                    sector=relevo.sector_id,
                    paso=paso,
                )

                relevo.fase = FaseRelevo.EN_CAMINO
                sustituto.estado_operativo = EstadoOperativo.ACTIVO

            # FASE 2: Desplazamiento del sustituto.
            if relevo.fase == FaseRelevo.EN_CAMINO:

                if relevo.indice_ruta < len(relevo.ruta) - 1:

                    siguiente = relevo.ruta[
                        relevo.indice_ruta + 1
                    ]

                    anterior = sustituto.posicion

                    sustituto.actuar(
                        siguiente,
                        self.entorno,
                    )

                    # Comprobar que el movimiento fue exitoso.
                    if sustituto.posicion == anterior:
                        relevo.fase = FaseRelevo.FALLIDO
                        self.fallidos += 1
                        sustituto.estado_operativo = (
                            EstadoOperativo.RESERVA
                        )
                        del self.relevos[original_id]
                        continue

                    relevo.indice_ruta += 1

                # FASE 3: Completar transferencia.
                if sustituto.posicion == original.posicion:

                    # Esperar confirmación del coordinador.
                    if not relevo.confirmacion_recibida:
                        continue

                    sustituto.estado_operativo = (
                        EstadoOperativo.VIGILANDO
                    )

                    original.estado_operativo = (
                        EstadoOperativo.EN_RELEVO
                    )

                    # Liberar el sector del dron original.
                    self.coordinador.liberar_sector(
                        original.id,
                        paso,
                    )

                    # Asignar el sector al sustituto.
                    self.coordinador.fijar_sector(
                        sustituto.id,
                        relevo.sector_id,
                        paso,
                    )

                    relevo.fase = FaseRelevo.COMPLETADO
                    self.completados += 1

                    # Preparar ruta de regreso del dron original.
                    ruta_recarga = self.gestor.ruta_recarga(
                        original.posicion,
                        self.entorno,
                    )

                    if ruta_recarga:
                        self.drones_recargando[original.id] = {
                            "ruta": ruta_recarga,
                            "indice": 0,
                        }

                    del self.relevos[original_id]

    def avanzar_recargas(
        self,
        drones: list[DronBase],
    ) -> None:
        """
        Mueve drones relevados hacia una estación de recarga.

        Cada llamada representa un tick:
        - Avanza como máximo una celda.
        - Recarga progresivamente al llegar.
        - Devuelve el dron a RESERVA al completar su batería.
        """

        por_id = {dron.id: dron for dron in drones}

        for dron_id, datos in list(self.drones_recargando.items()):
            dron = por_id.get(dron_id)

            if dron is None:
                del self.drones_recargando[dron_id]
                continue

            ruta = datos["ruta"]
            indice = datos["indice"]

            # FASE 1: Viajar hacia la estación.
            if indice < len(ruta) - 1:
                siguiente = ruta[indice + 1]
                anterior = dron.posicion

                dron.estado_operativo = EstadoOperativo.ACTIVO
                dron.actuar(siguiente, self.entorno)

                if dron.posicion == anterior:
                    self.fallidos += 1
                    del self.drones_recargando[dron_id]
                    continue

                datos["indice"] += 1
                continue

            # FASE 2: Recargar en la estación.
            if dron.posicion in self.entorno.recargas:
                self.gestor.recargar(dron, self.entorno)

                if dron.bateria >= dron.bateria_max:
                    dron.estado_operativo = EstadoOperativo.RESERVA
                    self.recargas_completadas += 1
                    del self.drones_recargando[dron_id]
