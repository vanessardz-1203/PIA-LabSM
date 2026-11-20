
import pytest

from Construccion_de_entorno.simulacion.entorno import (
    Entorno,
    Sector,
)
from Programacion_de_agentes.simulacion.agentes import (
    DronReactivo,
    EstadoOperativo,
)
from Coordinacion_multiagente.simulacion.coordinacion import (
    crear_coordinador,
)
from Gestion_energetica_relevos.simulacion.energia import (
    GestorEnergia,
)
from Gestion_energetica_relevos.simulacion.controlador import (
    ControladorRelevos,
)


@pytest.mark.parametrize(
    "mecanismo",
    ["pizarron", "mensajeria_directa"],
)
def test_controlador_relevo_por_ticks(mecanismo):
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
        mecanismo,
        entorno.sectores,
    )

    coordinador.registrar_dron(original.id)
    coordinador.registrar_dron(sustituto.id)
    coordinador.fijar_sector(original.id, 1, 0)

    controlador = ControladorRelevos(
        entorno=entorno,
        gestor_energia=GestorEnergia(),
        coordinador=coordinador,
    )

    iniciado = controlador.iniciar(
        original=original,
        candidatos=[sustituto],
        paso=0,
    )

    assert iniciado is True
    assert sustituto.posicion == (1, 3)

    coordinador.paso(1, [original, sustituto])
    controlador.avanzar([original, sustituto], paso=1)

    assert sustituto.posicion == (2, 3)
    assert controlador.completados == 0

    coordinador.paso(2, [original, sustituto])
    controlador.avanzar([original, sustituto], paso=2)

    assert sustituto.posicion == (3, 3)

    # Un tick adicional para procesar la confirmación pendiente
    coordinador.paso(3, [original, sustituto])
    controlador.avanzar([original, sustituto], paso=3)

    assert controlador.completados == 1

    assert coordinador.asignacion_de(original.id) is None
    assert coordinador.asignacion_de(sustituto.id) == 1
    assert sustituto.estado_operativo == EstadoOperativo.VIGILANDO

def test_regreso_a_recarga_por_ticks():
    entorno = Entorno(
        ancho=6,
        alto=6,
        recargas={(0, 0)},
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
        posicion=(2, 0),
        bateria=25.0,
    )

    sustituto = DronReactivo(
        id_dron=2,
        posicion=(1, 0),
        bateria=90.0,
        estado_operativo=EstadoOperativo.RESERVA,
    )

    coordinador = crear_coordinador(
        "pizarron",
        entorno.sectores,
    )

    coordinador.fijar_sector(original.id, 1, 0)

    controlador = ControladorRelevos(
        entorno=entorno,
        gestor_energia=GestorEnergia(),
        coordinador=coordinador,
    )

    assert controlador.iniciar(
        original,
        [sustituto],
        paso=0,
    )

    drones = [original, sustituto]

    for paso in range(1, 5):
        coordinador.paso(paso, drones)
        controlador.avanzar(drones, paso)
        controlador.avanzar_recargas(drones)

    assert controlador.completados == 1
    assert original.posicion == (0, 0)

    bateria_inicial = original.bateria

    controlador.avanzar_recargas(drones)

    assert original.bateria > bateria_inicial
