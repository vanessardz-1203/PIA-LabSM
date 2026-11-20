
from Construccion_de_entorno.simulacion.entorno import Entorno
from Programacion_de_agentes.simulacion.agentes import (
    DronReactivo,
    EstadoOperativo,
)
from Gestion_energetica_relevos.simulacion.energia import GestorEnergia

import pytest

from Construccion_de_entorno.simulacion.entorno import Sector
from Coordinacion_multiagente.simulacion.coordinacion import (
    crear_coordinador,
)
from Gestion_energetica_relevos.simulacion.relevos import (
    ejecutar_relevo_coordinado,
)

from Gestion_energetica_relevos.simulacion.relevos import (
    ejecutar_ciclo_energetico,
)

def test_dron_detecta_bateria_baja():
    dron = DronReactivo(
        id_dron=1,
        posicion=(0, 0),
        bateria=20.0,
    )

    gestor = GestorEnergia()

    assert gestor.necesita_relevo(dron)
    assert gestor.bateria_critica(dron)


def test_dron_encuentra_estacion_recarga():
    entorno = Entorno(
        ancho=5,
        alto=5,
        recargas={(4, 4)},
    )

    gestor = GestorEnergia()
    ruta = gestor.ruta_recarga((0, 0), entorno)

    assert ruta[0] == (0, 0)
    assert ruta[-1] == (4, 4)
    assert len(ruta) == 9


def test_dron_recarga_bateria():
    entorno = Entorno(
        ancho=5,
        alto=5,
        recargas={(2, 2)},
    )

    dron = DronReactivo(
        id_dron=1,
        posicion=(2, 2),
        bateria=20.0,
    )

    gestor = GestorEnergia(tasa_recarga=10.0)

    resultado = gestor.recargar(dron, entorno)

    assert resultado is True
    assert dron.bateria == 30.0
    assert dron.estado_operativo == EstadoOperativo.EN_RECARGA


from Gestion_energetica_relevos.simulacion.relevos import (
    seleccionar_sustituto,
)


def test_selecciona_sustituto_mas_cercano():
    entorno = Entorno(
        ancho=10,
        alto=10,
        recargas={(0, 0), (9, 9)},
    )

    original = DronReactivo(
        id_dron=1,
        posicion=(5, 5),
        bateria=25.0,
    )

    cercano = DronReactivo(
        id_dron=2,
        posicion=(4, 5),
        bateria=90.0,
        estado_operativo=EstadoOperativo.RESERVA,
    )

    lejano = DronReactivo(
        id_dron=3,
        posicion=(0, 0),
        bateria=100.0,
        estado_operativo=EstadoOperativo.RESERVA,
    )

    gestor = GestorEnergia()

    resultado = seleccionar_sustituto(
        dron_original=original,
        candidatos=[cercano, lejano],
        entorno=entorno,
        gestor_energia=gestor,
    )

    assert resultado is not None
    assert resultado.dron.id == 2
    assert resultado.distancia == 1


def test_sin_sustituto_disponible():
    entorno = Entorno(
        ancho=5,
        alto=5,
        recargas={(0, 0)},
    )

    original = DronReactivo(
        id_dron=1,
        posicion=(2, 2),
        bateria=20.0,
    )

    ocupado = DronReactivo(
        id_dron=2,
        posicion=(2, 3),
        bateria=90.0,
        estado_operativo=EstadoOperativo.VIGILANDO,
    )

    resultado = seleccionar_sustituto(
        dron_original=original,
        candidatos=[ocupado],
        entorno=entorno,
        gestor_energia=GestorEnergia(),
    )

    assert resultado is None


from Gestion_energetica_relevos.simulacion.relevos import (
    ejecutar_relevo,
)


def test_relevo_completado():
    entorno = Entorno(
        ancho=6,
        alto=6,
        recargas={(0, 0), (5, 5)},
    )

    original = DronReactivo(
        id_dron=1,
        posicion=(3, 3),
        bateria=25.0,
    )

    sustituto = DronReactivo(
        id_dron=2,
        posicion=(1, 3),
        bateria=90.0,
        estado_operativo=EstadoOperativo.RESERVA,
    )

    resultado = ejecutar_relevo(
        dron_original=original,
        candidatos=[sustituto],
        entorno=entorno,
        gestor_energia=GestorEnergia(),
    )

    assert resultado.completado is True
    assert resultado.sustituto_id == 2
    assert resultado.pasos_desplazamiento == 2

    assert sustituto.posicion == (3, 3)
    assert sustituto.estado_operativo == EstadoOperativo.VIGILANDO
    assert original.estado_operativo == EstadoOperativo.EN_RELEVO


def test_relevo_fallido_sin_sustitutos():
    entorno = Entorno(
        ancho=5,
        alto=5,
        recargas={(0, 0)},
    )

    original = DronReactivo(
        id_dron=1,
        posicion=(2, 2),
        bateria=20.0,
    )

    resultado = ejecutar_relevo(
        dron_original=original,
        candidatos=[],
        entorno=entorno,
        gestor_energia=GestorEnergia(),
    )

    assert resultado.completado is False
    assert resultado.sustituto_id is None

    # El original no abandona la vigilancia.
    assert original.estado_operativo == EstadoOperativo.VIGILANDO


def test_descarta_sustituto_sin_energia():
    entorno = Entorno(
        ancho=10,
        alto=10,
        recargas={(0, 0)},
    )

    original = DronReactivo(
        id_dron=1,
        posicion=(8, 8),
        bateria=20.0,
    )

    candidato = DronReactivo(
        id_dron=2,
        posicion=(1, 1),
        bateria=2.0,
        estado_operativo=EstadoOperativo.RESERVA,
    )

    resultado = seleccionar_sustituto(
        dron_original=original,
        candidatos=[candidato],
        entorno=entorno,
        gestor_energia=GestorEnergia(),
    )

    assert resultado is None


def test_relevo_evita_obstaculos():
    entorno = Entorno(
        ancho=5,
        alto=5,
        edificios={(1, 1), (2, 1), (3, 1)},
        recargas={(0, 0), (4, 4)},
    )

    original = DronReactivo(
        id_dron=1,
        posicion=(2, 2),
        bateria=25.0,
    )

    sustituto = DronReactivo(
        id_dron=2,
        posicion=(2, 0),
        bateria=90.0,
        estado_operativo=EstadoOperativo.RESERVA,
    )

    resultado = ejecutar_relevo(
        dron_original=original,
        candidatos=[sustituto],
        entorno=entorno,
        gestor_energia=GestorEnergia(),
    )

    assert resultado.completado is True
    assert sustituto.posicion == (2, 2)
    assert resultado.pasos_desplazamiento == 6


@pytest.mark.parametrize(
    "tipo_coordinador",
    ["pizarron", "mensajeria_directa"],
)
def test_transferencia_sector_en_relevo(tipo_coordinador):
    entorno = Entorno(
        ancho=6,
        alto=6,
        recargas={(0, 0), (5, 5)},
        sectores=[
            Sector(
                id=1,
                celdas={
                    (x, y)
                    for x in range(6)
                    for y in range(6)
                },
            )
        ],
    )

    original = DronReactivo(
        id_dron=1,
        posicion=(3, 3),
        bateria=25.0,
    )

    sustituto = DronReactivo(
        id_dron=2,
        posicion=(1, 3),
        bateria=90.0,
        estado_operativo=EstadoOperativo.RESERVA,
    )

    coordinador = crear_coordinador(
        tipo_coordinador,
        entorno.sectores,
    )

    coordinador.registrar_dron(original.id)
    coordinador.registrar_dron(sustituto.id)

    coordinador.fijar_sector(
        original.id,
        sector=1,
        paso=0,
    )

    resultado = ejecutar_relevo_coordinado(
        dron_original=original,
        candidatos=[sustituto],
        entorno=entorno,
        gestor_energia=GestorEnergia(),
        coordinador=coordinador,
        sector_id=1,
        paso_actual=1,
    )

    assert resultado.completado is True
    assert coordinador.asignacion_de(original.id) is None
    assert coordinador.asignacion_de(sustituto.id) == 1
    assert sustituto.estado_operativo == EstadoOperativo.VIGILANDO


def test_dron_relevado_llega_a_recarga():
    entorno = Entorno(
        ancho=5,
        alto=5,
        recargas={(0, 0)},
    )

    dron = DronReactivo(
        id_dron=1,
        posicion=(2, 2),
        bateria=25.0,
        estado_operativo=EstadoOperativo.EN_RELEVO,
    )

    gestor = GestorEnergia()

    resultado = gestor.ir_a_recargar(dron, entorno)

    assert resultado is True
    assert dron.posicion == (0, 0)
    assert dron.estado_operativo == EstadoOperativo.EN_RECARGA




@pytest.mark.parametrize(
    "tipo_coordinador",
    ["pizarron", "mensajeria_directa"],
)
def test_ciclo_energetico_completo(tipo_coordinador):
    entorno = Entorno(
        ancho=6,
        alto=6,
        recargas={(0, 0), (5, 5)},
        sectores=[
            Sector(
                id=1,
                celdas={
                    (x, y)
                    for x in range(6)
                    for y in range(6)
                },
            )
        ],
    )

    original = DronReactivo(
        id_dron=1,
        posicion=(3, 3),
        bateria=25.0,
    )

    sustituto = DronReactivo(
        id_dron=2,
        posicion=(1, 3),
        bateria=90.0,
        estado_operativo=EstadoOperativo.RESERVA,
    )

    coordinador = crear_coordinador(
        tipo_coordinador,
        entorno.sectores,
    )

    coordinador.registrar_dron(original.id)
    coordinador.registrar_dron(sustituto.id)

    coordinador.fijar_sector(
        original.id,
        sector=1,
        paso=0,
    )

    resultado = ejecutar_ciclo_energetico(
        dron_original=original,
        candidatos=[sustituto],
        entorno=entorno,
        gestor_energia=GestorEnergia(),
        coordinador=coordinador,
        paso_actual=1,
    )

    assert resultado.relevo_realizado is True
    assert resultado.sustituto_id == 2
    assert resultado.llego_a_recarga is True

    assert coordinador.asignacion_de(original.id) is None
    assert coordinador.asignacion_de(sustituto.id) == 1

    assert original.posicion in entorno.recargas
    assert original.estado_operativo == EstadoOperativo.EN_RECARGA

    assert sustituto.estado_operativo == EstadoOperativo.VIGILANDO
