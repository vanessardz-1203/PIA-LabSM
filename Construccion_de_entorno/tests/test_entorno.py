"""
Pruebas del Integrante 1: entorno y cobertura.

Ejecutar desde la raíz del proyecto:
    python -m pytest tests/test_entorno.py -v
"""
import random

from simulacion.cobertura import (
    calcular_cobertura,
    celdas_visibles,
    colocar_drones_aleatorios,
    cobertura_por_sector,
    hay_linea_de_vista,
    linea_bresenham,
)
from simulacion.entorno import (
    RECARGA,
    Entorno,
    es_conectado,
    generar_mapa_industrial,
)


def _mapa_base():
    return generar_mapa_industrial(ancho=40, alto=30, semilla=42)


# ---- entorno ----------------------------------------------------------------
def test_dimensiones_del_mapa():
    mapa = _mapa_base()
    assert mapa.ancho == 40
    assert mapa.alto == 30


def test_edificios_no_son_transitables():
    mapa = _mapa_base()
    assert mapa.edificios, "debe haber al menos un edificio"
    assert all(not mapa.es_transitable(c) for c in mapa.edificios)


def test_recargas_son_transitables_y_se_identifican():
    mapa = _mapa_base()
    assert len(mapa.recargas) > 0
    for c in mapa.recargas:
        assert mapa.es_transitable(c)
        assert mapa.tipo_celda(c) == RECARGA


def test_borde_del_mapa_siempre_libre():
    mapa = _mapa_base()
    borde = [(x, y) for x in range(mapa.ancho) for y in range(mapa.alto)
             if x in (0, mapa.ancho - 1) or y in (0, mapa.alto - 1)]
    assert not any(c in mapa.edificios for c in borde)


def test_fuera_de_limites_no_es_transitable():
    mapa = _mapa_base()
    assert not mapa.es_transitable((-1, 0))
    assert not mapa.es_transitable((mapa.ancho, 0))
    assert not mapa.es_transitable((0, mapa.alto))


def test_sectores_particionan_el_area_transitable():
    mapa = _mapa_base()
    union = set()
    total = 0
    for sector in mapa.sectores:
        total += len(sector.celdas)
        union |= sector.celdas
    assert union == mapa.celdas_transitables()
    assert total == len(union), "ningún celda debe pertenecer a dos sectores"


def test_mapa_es_conectado():
    assert es_conectado(_mapa_base())


def test_generacion_reproducible():
    a = generar_mapa_industrial(semilla=7)
    b = generar_mapa_industrial(semilla=7)
    assert a.edificios == b.edificios
    assert a.recargas == b.recargas


def test_conectividad_detecta_zona_aislada():
    # Muro completo que separa el mapa en dos mitades
    e = Entorno(ancho=5, alto=3, edificios={(2, 0), (2, 1), (2, 2)})
    assert not es_conectado(e)


# ---- líneas de visión --------------------------------------------------------
def test_bresenham_horizontal():
    assert linea_bresenham((0, 0), (3, 0)) == [(0, 0), (1, 0), (2, 0), (3, 0)]


def test_bresenham_diagonal():
    assert linea_bresenham((0, 0), (2, 2)) == [(0, 0), (1, 1), (2, 2)]


def test_bresenham_sentido_inverso():
    assert linea_bresenham((3, 0), (0, 0)) == [(3, 0), (2, 0), (1, 0), (0, 0)]


def test_edificio_bloquea_la_vision():
    e = Entorno(ancho=7, alto=3, edificios={(3, 1)})
    assert not hay_linea_de_vista(e, (1, 1), (5, 1))
    assert hay_linea_de_vista(e, (1, 0), (5, 0))


# ---- cobertura ----------------------------------------------------------------
def test_radio_limita_la_visibilidad():
    e = Entorno(ancho=20, alto=20)
    vis = celdas_visibles(e, (10, 10), radio=2, usar_linea_de_vista=False)
    assert (12, 10) in vis          # distancia 2
    assert (13, 10) not in vis      # distancia 3
    assert (12, 12) not in vis      # distancia 2.83 > 2


def test_un_dron_con_radio_grande_cubre_todo():
    e = Entorno(ancho=5, alto=5)
    res = calcular_cobertura(e, [(2, 2)], radio=10, usar_linea_de_vista=False)
    assert res.cobertura == 1.0
    assert res.puntos_ciegos == set()


def test_muro_deja_puntos_ciegos_detras():
    # Muro vertical completo en x = 3; un dron a la izquierda no ve el lado derecho
    e = Entorno(ancho=7, alto=3, edificios={(3, 0), (3, 1), (3, 2)})
    res = calcular_cobertura(e, [(1, 1)], radio=10)
    esperados = {(x, y) for x in range(4, 7) for y in range(3)}
    assert res.puntos_ciegos == esperados


def test_redundancia_con_dos_drones_en_el_mismo_punto():
    e = Entorno(ancho=5, alto=5)
    res = calcular_cobertura(e, [(2, 2), (2, 2)], radio=1, usar_linea_de_vista=False)
    # Rombo de radio 1 alrededor de (2,2): 5 celdas vistas por ambos drones
    assert abs(res.cobertura_redundante - 5 / 25) < 1e-9
    assert res.redundancia_media == 2.0


def test_mas_drones_no_reduce_la_cobertura():
    mapa = _mapa_base()
    posiciones = colocar_drones_aleatorios(mapa, 6, random.Random(1))
    c3 = calcular_cobertura(mapa, posiciones[:3], radio=4).cobertura
    c6 = calcular_cobertura(mapa, posiciones, radio=4).cobertura
    assert c6 >= c3


def test_sin_linea_de_vista_cubre_al_menos_tanto_como_con_ella():
    mapa = _mapa_base()
    posiciones = colocar_drones_aleatorios(mapa, 4, random.Random(3))
    con = calcular_cobertura(mapa, posiciones, radio=5, usar_linea_de_vista=True).cobertura
    sin = calcular_cobertura(mapa, posiciones, radio=5, usar_linea_de_vista=False).cobertura
    assert sin >= con


def test_cobertura_por_sector_en_rango():
    mapa = _mapa_base()
    posiciones = colocar_drones_aleatorios(mapa, 4, random.Random(5))
    res = calcular_cobertura(mapa, posiciones, radio=5)
    por_sector = cobertura_por_sector(mapa, res)
    assert len(por_sector) == len(mapa.sectores)
    assert all(0.0 <= v <= 1.0 for v in por_sector.values())


def test_colocacion_aleatoria_valida():
    mapa = _mapa_base()
    posiciones = colocar_drones_aleatorios(mapa, 8, random.Random(9))
    assert len(set(posiciones)) == 8
    assert all(mapa.es_transitable(p) for p in posiciones)


# ---- ejecución directa sin pytest (útil si pytest no está instalado) ---------
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
