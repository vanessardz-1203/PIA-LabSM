"""
Pruebas del Integrante 2: agentes autónomos, percepción, memoria y patrullaje (Etapa 2).

Ejecutar dentro de Docker desde la raíz del repositorio:
    python -m pytest Programacion_de_agentes/tests/test_agentes.py -v
"""
from __future__ import annotations

import random

from Construccion_de_entorno.simulacion.entorno import Entorno, generar_mapa_industrial
from Programacion_de_agentes.experimentos.experimento_agentes import simular_patrullaje
from Programacion_de_agentes.simulacion.agentes import (
    DronBasadoEnModelos,
    DronReactivo,
    EstadoOperativo,
    ModeloInterno,
    crear_dron,
)
from Programacion_de_agentes.simulacion.patrullaje import (
    camino_mas_corto_bfs,
    siguiente_paso_hacia,
)


def _mapa_pequeno() -> Entorno:
    """Crea un mapa industrial compacto y reproducible para pruebas unitarias."""
    return generar_mapa_industrial(
        ancho=16,
        alto=12,
        num_edificios=2,
        num_recargas=2,
        sectores_x=2,
        sectores_y=2,
        semilla=7,
        sectores_prioritarios=(0, 3),
    )


# ---- atributos, validaciones y ciclo de vida del dron -----------------------
def test_inicializacion_atributos_y_validaciones():
    dron = DronReactivo(
        id_dron=1,
        posicion=(0, 0),
        radio_observacion=4,
        bateria=80.0,
        bateria_max=100.0,
        consumo_por_paso=1.0,
    )
    assert dron.id == 1
    assert dron.posicion == (0, 0)
    assert dron.radio_observacion == 4.0
    assert dron.bateria == 80.0
    assert dron.porcentaje_bateria == 80.0
    assert dron.estado_operativo == EstadoOperativo.VIGILANDO
    assert dron.esta_operativo

    dron_vacio = DronBasadoEnModelos(id_dron=2, posicion=(0, 0), bateria=0.0)
    assert dron_vacio.estado_operativo == EstadoOperativo.INACTIVO
    assert not dron_vacio.esta_operativo

    for kwargs in (
        {"radio_observacion": -1},
        {"bateria_max": 0},
        {"bateria": 150.0, "bateria_max": 100.0},
        {"consumo_por_paso": -0.5},
    ):
        try:
            DronReactivo(id_dron=0, posicion=(0, 0), **kwargs)
        except ValueError:
            continue
        raise AssertionError(f"Debió fallar con argumentos inválidos: {kwargs}")


def test_fabrica_crear_dron():
    r = crear_dron("reactivo", 1, (0, 0), semilla=1)
    m = crear_dron("basado_en_modelos", 2, (0, 0), semilla=1)
    assert isinstance(r, DronReactivo)
    assert isinstance(m, DronBasadoEnModelos)

    try:
        crear_dron("desconocido", 3, (0, 0))
    except ValueError:
        return
    raise AssertionError("crear_dron debió rechazar arquitectura desconocida")


def test_consumo_bateria_y_transicion_a_inactivo():
    entorno = Entorno(ancho=5, alto=5)
    dron = DronReactivo(
        id_dron=0,
        posicion=(2, 2),
        radio_observacion=2,
        bateria=1.5,
        bateria_max=10.0,
        consumo_por_paso=1.0,
        semilla=10,
    )
    dron.ejecutar_paso(entorno, paso=1)
    assert dron.bateria == 0.5
    assert dron.esta_operativo

    dron.ejecutar_paso(entorno, paso=2)
    assert dron.bateria == 0.0
    assert dron.estado_operativo == EstadoOperativo.INACTIVO
    assert not dron.esta_operativo

    pos_final = dron.posicion
    dron.ejecutar_paso(entorno, paso=3)
    assert dron.posicion == pos_final
    assert dron.bateria == 0.0


def test_actuar_rechaza_movimiento_invalido():
    entorno = Entorno(ancho=5, alto=5, edificios={(2, 1)})
    dron = DronReactivo(id_dron=0, posicion=(2, 2))
    for destino_invalido in ((4, 4), (2, 1), (-1, 2)):
        try:
            dron.actuar(destino_invalido, entorno)
        except ValueError:
            continue
        raise AssertionError(f"actuar debió rechazar destino inválido {destino_invalido}")


# ---- percepción del entorno -------------------------------------------------
def test_percepcion_respeta_linea_de_vista_y_prioritarios():
    entorno = _mapa_pequeno()
    dron = DronReactivo(id_dron=0, posicion=(0, 0), radio_observacion=3)
    percepcion = dron.percibir(entorno, paso=1, usar_linea_de_vista=True)

    assert percepcion.posicion == (0, 0)
    assert (0, 0) in percepcion.celdas_visibles
    assert all(entorno.es_transitable(c) for c in percepcion.celdas_visibles)
    assert all(c in percepcion.celdas_visibles for c in percepcion.celdas_prioritarias_visibles)
    assert percepcion.en_sector_prioritario is True
    assert percepcion.sector_actual == 0


# ---- arquitectura reactiva --------------------------------------------------
def test_dron_reactivo_sin_memoria_y_reproducible():
    entorno = _mapa_pequeno()
    d1 = DronReactivo(id_dron=0, posicion=(0, 0), radio_observacion=3, semilla=123)
    d2 = DronReactivo(id_dron=0, posicion=(0, 0), radio_observacion=3, semilla=123)

    assert not hasattr(d1, "modelo")

    for paso in range(1, 25):
        d1.ejecutar_paso(entorno, paso=paso)
        d2.ejecutar_paso(entorno, paso=paso)
        assert entorno.es_transitable(d1.posicion)

    assert d1.historial_posiciones == d2.historial_posiciones


def test_dron_reactivo_responde_a_estimulo_prioritario_local():
    entorno = generar_mapa_industrial(
        ancho=6,
        alto=3,
        num_edificios=0,
        num_recargas=0,
        sectores_x=2,
        sectores_y=1,
        semilla=1,
        sectores_prioritarios=(0,),
    )
    dron = DronReactivo(
        id_dron=0,
        posicion=(3, 1),
        radio_observacion=2,
        prob_exploracion=0.0,
        semilla=5,
    )
    percepcion = dron.percibir(entorno, paso=1)
    destino = dron.decidir(percepcion)
    assert destino == (2, 1)


# ---- navegación BFS y modelo interno ----------------------------------------
def test_camino_mas_corto_bfs_rodea_obstaculo():
    edificios = {(2, 0), (2, 1), (2, 2)}
    transitables = {(x, y) for x in range(5) for y in range(4) if (x, y) not in edificios}
    camino = camino_mas_corto_bfs((1, 0), (3, 0), transitables)
    assert camino[0] == (1, 0)
    assert camino[-1] == (3, 0)
    assert all(c not in edificios for c in camino)
    assert (2, 3) in camino
    assert siguiente_paso_hacia((1, 0), (3, 0), transitables) == camino[1]


def test_modelo_interno_registra_memoria_obstaculos_y_antiguedad():
    entorno = Entorno(ancho=5, alto=5, edificios={(2, 1)}, recargas={(1, 2)})
    dron = DronBasadoEnModelos(id_dron=0, posicion=(2, 2), radio_observacion=1, semilla=1)
    p1 = dron.percibir(entorno, paso=1)
    dron.modelo.actualizar(p1)

    assert (2, 1) in dron.modelo.obstaculos_conocidos
    assert (1, 2) in dron.modelo.recargas_conocidas
    assert dron.modelo.ultima_observacion[(2, 2)] == 1
    assert dron.modelo.antiguedad((2, 2)) == 0
    assert dron.modelo.antiguedad((4, 4)) == 2
    assert dron.modelo.celdas_frontera()

    dron.modelo.paso_actual = 5
    assert dron.modelo.antiguedad((1, 2)) == 4


def test_modelo_interno_vacio_sin_errores():
    modelo = ModeloInterno(ancho=4, alto=4)
    assert modelo.celdas_frontera() == set()
    assert modelo.antiguedad((0, 0)) == 1


# ---- arquitectura basada en modelos vs reactiva -----------------------------
def test_dron_basado_en_modelos_explora_mejor_que_reactivo():
    entorno = _mapa_pequeno()
    posiciones = [(0, 0), (15, 11)]

    drones_reactivos = [
        DronReactivo(id_dron=i, posicion=p, radio_observacion=3, semilla=50 + i)
        for i, p in enumerate(posiciones)
    ]
    drones_modelos = [
        DronBasadoEnModelos(id_dron=i, posicion=p, radio_observacion=3, semilla=50 + i)
        for i, p in enumerate(posiciones)
    ]

    res_reactivo = simular_patrullaje(entorno, drones_reactivos, pasos=60)
    res_modelo = simular_patrullaje(entorno, drones_modelos, pasos=60)

    assert res_modelo.cobertura_acumulada_pct > res_reactivo.cobertura_acumulada_pct
    assert res_modelo.tiempo_sin_vigilancia_medio < res_reactivo.tiempo_sin_vigilancia_medio
    assert res_modelo.eficiencia_patrullaje_pct > res_reactivo.eficiencia_patrullaje_pct


def test_dron_basado_en_modelos_siempre_realiza_movimientos_validos():
    entorno = _mapa_pequeno()
    rng = random.Random(42)
    inicio = rng.choice(sorted(entorno.celdas_transitables()))
    dron = DronBasadoEnModelos(id_dron=0, posicion=inicio, radio_observacion=3, semilla=42)
    for paso in range(1, 50):
        anterior = dron.posicion
        dron.ejecutar_paso(entorno, paso=paso)
        assert entorno.es_transitable(dron.posicion)
        assert abs(dron.posicion[0] - anterior[0]) + abs(dron.posicion[1] - anterior[1]) <= 1


if __name__ == "__main__":
    import sys
    import traceback

    funciones = [f for n, f in list(globals().items()) if n.startswith("test_")]
    fallidas = 0
    for f in funciones:
        try:
            f()
            print(f"PASS  {f.__name__}")
        except Exception:
            fallidas += 1
            print(f"FAIL  {f.__name__}")
            traceback.print_exc()
    print(f"\n{len(funciones) - fallidas}/{len(funciones)} pruebas pasaron")
    sys.exit(1 if fallidas else 0)
