import pytest
from Construccion_de_entorno.simulacion.entorno import Entorno
from Programacion_de_agentes.simulacion.agentes import DronReactivo, EstadoOperativo
from Coordinacion_multiagente.simulacion.coordinacion import CanalComunicacion, crear_coordinador
from Integracion_robustez.simulacion.robustez import Evento, GestorRobustez


def test_falla_dron():
    e = Entorno(ancho=4, alto=4)
    d = DronReactivo(id_dron=1, posicion=(0, 0))
    canal = CanalComunicacion()
    c = crear_coordinador('pizarron', [], canal)
    eventos = GestorRobustez([Evento(2, 'falla_dron', dron_id=1)])
    assert eventos.aplicar(1, [d], e, c, canal) == []
    eventos.aplicar(2, [d], e, c, canal)
    assert d.estado_operativo == EstadoOperativo.INACTIVO


def test_perdida_y_retraso():
    e = Entorno(ancho=4, alto=4)
    canal = CanalComunicacion()
    c = crear_coordinador('pizarron', [], canal)
    eventos = GestorRobustez([Evento(1, 'perdida_mensajes', valor=0.3), Evento(2, 'retraso_mensajes', valor=10)])
    eventos.aplicar(1, [], e, c, canal)
    assert canal.prob_perdida == 0.3
    eventos.aplicar(2, [], e, c, canal)
    assert canal.retraso == 10


def test_evento_invalido():
    with pytest.raises(ValueError):
        GestorRobustez([Evento(0, 'falla_dron', dron_id=1)])
