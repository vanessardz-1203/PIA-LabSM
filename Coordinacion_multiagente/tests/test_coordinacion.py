"""
Pruebas del Integrante 3: comunicación y coordinación.

Ejecutar desde la raíz del proyecto:
    python -m pytest Coordinacion_multiagente/tests -v
"""
from __future__ import annotations

import random
from dataclasses import dataclass

import pytest

from Construccion_de_entorno.simulacion.cobertura import colocar_drones_aleatorios
from Construccion_de_entorno.simulacion.entorno import Sector, generar_mapa_industrial
from Programacion_de_agentes.simulacion.agentes import EstadoOperativo, crear_dron

from Coordinacion_multiagente.simulacion.coordinacion import (
    ID_PIZARRON,
    CanalComunicacion,
    CoordinadorMensajeria,
    CoordinadorPizarron,
    Mensaje,
    Reclamo,
    TablaReclamos,
    TipoMensaje,
    crear_coordinador,
    elegir_sector,
    evaluar_asignacion,
)
from Coordinacion_multiagente.simulacion.dron_coordinado import DronCoordinado

MECANISMOS = ["pizarron", "mensajeria_directa"]


# ---- utilidades de prueba ----------------------------------------------------
@dataclass
class DronFalso:
    """Dron mínimo que cumple el protocolo DronCoordinable (no se mueve)."""

    id: int
    posicion: tuple[int, int] = (0, 0)
    estado_operativo: EstadoOperativo = EstadoOperativo.VIGILANDO
    bateria: float = 100.0

    @property
    def esta_operativo(self) -> bool:
        return self.bateria > 0 and self.estado_operativo in (
            EstadoOperativo.ACTIVO, EstadoOperativo.VIGILANDO)


def sectores_2x2() -> list[Sector]:
    """Cuatro sectores 10x10 como el mapa real: 0 y 3 prioritarios (peso 2)."""
    sectores = []
    for i in range(4):
        x0, y0 = (i % 2) * 10, (i // 2) * 10
        celdas = {(x, y) for x in range(x0, x0 + 10) for y in range(y0, y0 + 10)}
        prioritario = i in (0, 3)
        sectores.append(Sector(i, celdas, prioritario, 2.0 if prioritario else 1.0))
    return sectores


def correr(coord, drones, desde: int, hasta: int) -> None:
    for paso in range(desde, hasta + 1):
        coord.paso(paso, drones)


def asignacion_operativa(coord, drones):
    return {d.id: coord.asignacion_de(d.id) for d in drones if d.esta_operativo}


@pytest.fixture(scope="module")
def entorno():
    return generar_mapa_industrial(sectores_prioritarios=(0, 3), peso_prioritario=2.0)


# ---- 1. Mensaje ----------------------------------------------------------------
def test_mensaje_campos_y_difusion():
    m = Mensaje(1, None, TipoMensaje.RECLAMAR_SECTOR, {"sector": 2}, paso_envio=4)
    assert (m.emisor, m.receptor, m.tipo, m.paso_envio) == (1, None, TipoMensaje.RECLAMAR_SECTOR, 4)
    assert m.contenido["sector"] == 2
    assert m.es_difusion
    assert not Mensaje(1, 3, TipoMensaje.CONFIRMAR_RELEVO, {}, 0).es_difusion


def test_mensaje_es_inmutable_y_copia_el_contenido():
    datos = {"sector": 1}
    m = Mensaje(0, None, "liberar_sector", datos, 0)  # acepta el texto del tipo
    assert m.tipo is TipoMensaje.LIBERAR_SECTOR
    datos["sector"] = 99                               # cambiar el original no afecta
    assert m.contenido["sector"] == 1
    with pytest.raises(TypeError):
        m.contenido["sector"] = 5                      # type: ignore[index]
    with pytest.raises(AttributeError):
        m.emisor = 7                                   # type: ignore[misc]


def test_mensaje_valida_paso_y_tipo():
    with pytest.raises(ValueError):
        Mensaje(0, None, TipoMensaje.INFORME_SECTOR, {}, paso_envio=-1)
    with pytest.raises(ValueError):
        Mensaje(0, None, "tipo_inexistente", {}, 0)


# ---- 2. Canal: retraso y pérdida -------------------------------------------------
def test_canal_aplica_retraso_fijo():
    canal = CanalComunicacion(retraso=3)
    canal.enviar(Mensaje(0, 1, TipoMensaje.SOLICITAR_RELEVO, {}, paso_envio=2), [1])
    assert canal.entregar(4) == []          # aún no llega
    entregas = canal.entregar(5)            # 2 + 3
    assert len(entregas) == 1 and entregas[0].destinatario == 1
    assert entregas[0].retraso == 3
    assert canal.retraso_medio == 3.0 and canal.pendientes == 0


def test_canal_retraso_variable_dentro_de_rango():
    canal = CanalComunicacion(retraso=1, retraso_variable=2, semilla=5)
    for paso in range(50):
        canal.enviar(Mensaje(0, None, TipoMensaje.INFORME_SECTOR, {"sector": 0}, paso), [1])
    retrasos = [e.retraso for e in canal.entregar(10**6)]
    assert min(retrasos) >= 1 and max(retrasos) <= 3
    assert len(set(retrasos)) > 1


def test_canal_perdida_reproducible_con_semilla():
    def simular(semilla):
        canal = CanalComunicacion(prob_perdida=0.3, semilla=semilla)
        for paso in range(500):
            canal.enviar(Mensaje(0, None, TipoMensaje.INFORME_SECTOR, {"sector": 0}, paso), [1, 2])
        return canal.perdidos, [(e.destinatario, e.mensaje.paso_envio) for e in canal.entregar(10**6)]

    assert simular(11) == simular(11)        # misma semilla -> mismos mensajes perdidos
    perdidos, _ = simular(11)
    assert 0.25 < perdidos / 1000 < 0.35     # cerca de la probabilidad configurada


def test_canal_metricas_cuadran():
    canal = CanalComunicacion(retraso=1, prob_perdida=0.5, semilla=1)
    for paso in range(100):
        canal.enviar(Mensaje(0, None, TipoMensaje.INFORME_SECTOR, {"sector": 0}, paso), [1, 2, 3])
    canal.entregar(50)
    m = canal.metricas()
    assert m["enviados"] == 300
    assert m["enviados"] == m["entregados"] + m["perdidos"] + m["pendientes"]


def test_canal_extremos_y_hook_de_perdida():
    canal = CanalComunicacion(prob_perdida=1.0, semilla=0)
    canal.enviar(Mensaje(0, None, TipoMensaje.INFORME_SECTOR, {"sector": 0}, 0), [1, 2])
    assert canal.perdidos == 2 and canal.entregar(0) == []

    canal = CanalComunicacion()
    canal.hook_perdida = lambda mensaje, destino: destino == 2  # aislar al dron 2
    canal.enviar(Mensaje(0, None, TipoMensaje.INFORME_SECTOR, {"sector": 0}, 0), [1, 2])
    assert [e.destinatario for e in canal.entregar(0)] == [1]

    with pytest.raises(ValueError):
        CanalComunicacion(prob_perdida=1.5)
    with pytest.raises(ValueError):
        CanalComunicacion(retraso=-1)


# ---- 3. Tabla de reclamos ----------------------------------------------------------
def test_tabla_reclamar_cambiar_y_liberar():
    t = TablaReclamos()
    t.aplicar(Mensaje(1, None, TipoMensaje.RECLAMAR_SECTOR, {"sector": 0, "paso_reclamo": 3}, 3))
    assert t.reclamantes(0) == [1]
    # el nuevo reclamo sustituye al anterior aunque no llegue un LIBERAR
    t.aplicar(Mensaje(1, None, TipoMensaje.RECLAMAR_SECTOR, {"sector": 2, "paso_reclamo": 5}, 5))
    assert t.reclamantes(0) == [] and t.reclamantes(2) == [1]
    t.aplicar(Mensaje(1, None, TipoMensaje.LIBERAR_SECTOR, {"sector": 2}, 6))
    assert t.reclamos() == []


def test_tabla_ignora_mensajes_viejos_desordenados():
    t = TablaReclamos()
    t.aplicar(Mensaje(1, None, TipoMensaje.LIBERAR_SECTOR, {"sector": 0}, 9))
    t.aplicar(Mensaje(1, None, TipoMensaje.RECLAMAR_SECTOR, {"sector": 0}, 4))  # llegó tarde
    assert t.reclamos() == []


def test_tabla_comparte_ultima_vigilancia_y_expira():
    t = TablaReclamos()
    t.aplicar(Mensaje(4, None, TipoMensaje.INFORME_SECTOR,
                      {"sector": 3, "paso_reclamo": 1, "en_sector": True}, 10))
    assert t.ultima_vigilancia[3] == 10
    assert t.expirar(paso_actual=25, timeout=15) == []   # 15 pasos: aún vigente
    assert t.expirar(paso_actual=26, timeout=15) == [4]  # 16 pasos: caducó
    assert t.reclamantes(3) == []


def test_tabla_mide_timeout_desde_la_llegada():
    t = TablaReclamos()
    t.aplicar(Mensaje(4, None, TipoMensaje.INFORME_SECTOR, {"sector": 3}, 0), paso_llegada=10)
    assert t.expirar(paso_actual=25, timeout=15) == []   # 15 pasos desde que llegó
    assert t.expirar(paso_actual=26, timeout=15) == [4]


@pytest.mark.parametrize("mecanismo", MECANISMOS)
def test_retraso_alto_y_un_informe_perdido_no_es_falsa_alarma(mecanismo):
    # Regresión: con retraso 10 y timeout 15, perder UN informe no debe hacer
    # que los demás den por caído a un dron sano.
    coord = crear_coordinador(mecanismo, sectores_2x2(), CanalComunicacion(retraso=10),
                              periodo_informe=5, timeout_informe=15)
    coord.canal.hook_perdida = lambda m, d: m.emisor == 0 and m.paso_envio == 6
    drones = [DronFalso(0, (2, 2)), DronFalso(1, (18, 18))]
    correr(coord, drones, 1, 40)
    assert coord.metricas()["expiraciones"] == 0
    assert coord.vista_de(1).reclamo_de(0) is not None


# ---- 4. Regla de asignación y evaluación ----------------------------------------------
def test_elegir_sector_prefiere_prioritario_libre():
    sectores = sectores_2x2()
    assert elegir_sector(0, (2, 2), sectores, []) == 0      # prioritario más cercano
    assert elegir_sector(0, (18, 18), sectores, []) == 3


def test_elegir_sector_reparte_segun_peso():
    sectores = sectores_2x2()
    # 0 y 3 ocupados: un sector normal vacío (clave 1.0, 0) gana a duplicar un
    # prioritario (clave 1.0, 1) por el desempate de ocupantes.
    ajenos = [Reclamo(1, 0, 0, 0), Reclamo(2, 3, 0, 0)]
    assert elegir_sector(0, (2, 2), sectores, ajenos) in (1, 2)
    # Con los cuatro ocupados, el quinto dron va a un prioritario (peso 2).
    ajenos += [Reclamo(3, 1, 0, 0), Reclamo(4, 2, 0, 0)]
    assert elegir_sector(0, (2, 2), sectores, ajenos) in (0, 3)


def test_elegir_sector_conflicto_lo_gana_la_precedencia():
    sectores = sectores_2x2()
    a = Reclamo(1, 0, paso_reclamo=0, ultimo_informe=0)
    b = Reclamo(2, 0, paso_reclamo=0, ultimo_informe=0)
    # mismo paso de reclamo -> gana el id menor; el otro se va
    assert elegir_sector(1, (2, 2), sectores, [b], actual=a) == 0
    assert elegir_sector(2, (2, 2), sectores, [a], actual=b) != 0
    # quien llegó antes gana aunque tenga id mayor
    viejo = Reclamo(9, 0, paso_reclamo=1, ultimo_informe=1)
    nuevo = Reclamo(1, 0, paso_reclamo=5, ultimo_informe=5)
    assert elegir_sector(9, (2, 2), sectores, [nuevo], actual=viejo) == 0
    assert elegir_sector(1, (2, 2), sectores, [viejo], actual=nuevo) != 0


def test_elegir_sector_histeresis_y_fijo():
    sectores = sectores_2x2()
    # en el sector 1 (normal, clave 1.0) con los prioritarios vacíos (clave 0.5):
    # hay algo estrictamente mejor, así que se cambia a un prioritario
    assert elegir_sector(0, (12, 2), sectores, [], actual=Reclamo(0, 1, 0, 0)) in (0, 3)
    # con 0 y 3 ocupados se queda en el 1 (no hay nada estrictamente mejor)
    ajenos = [Reclamo(1, 0, 0, 0), Reclamo(2, 3, 0, 0)]
    assert elegir_sector(0, (2, 2), sectores, ajenos, actual=Reclamo(0, 1, 0, 0)) == 1
    # un reclamo fijo nunca se reevalúa
    fijo = Reclamo(0, 1, 0, 0, fijo=True)
    assert elegir_sector(0, (2, 2), sectores, [Reclamo(1, 1, 0, 0)], actual=fijo) == 1


def test_evaluar_asignacion():
    sectores = sectores_2x2()
    ok = evaluar_asignacion({0: 0, 1: 1, 2: 2, 3: 3}, sectores)
    assert ok.valida and ok.duplicados_evitables == 0 and ok.sectores_vacios == 0
    mala = evaluar_asignacion({0: 0, 1: 0, 2: 2, 3: 3}, sectores)
    assert not mala.valida and mala.duplicados_evitables == 1 and mala.sectores_vacios == 1
    # 3 drones: un sector vacío es inevitable, pero debe ser uno normal
    assert evaluar_asignacion({0: 0, 1: 3, 2: 1}, sectores).valida
    assert not evaluar_asignacion({0: 0, 1: 1, 2: 2}, sectores).valida  # el 3 (prio) vacío
    # 6 drones: duplicar prioritarios es correcto, no redundante
    assert evaluar_asignacion({0: 0, 1: 0, 2: 3, 3: 3, 4: 1, 5: 2}, sectores).valida


# ---- 5. Pizarrón y mensajería directa ------------------------------------------------
def test_pizarron_escritura_respeta_retraso_y_es_visible_para_todos():
    coord = CoordinadorPizarron(sectores_2x2(), CanalComunicacion(retraso=2))
    drones = [DronFalso(0, (2, 2)), DronFalso(1, (18, 18))]
    coord.paso(1, drones)
    assert coord.asignacion_de(0) == 0 and coord.asignacion_de(1) == 3
    assert coord.pizarron.tabla.reclamos() == []          # todavía viajando
    coord.paso(3, drones)
    tabla = coord.pizarron.tabla
    assert tabla.reclamantes(0) == [0] and tabla.reclamantes(3) == [1]
    assert coord.vista_de(0) is coord.vista_de(1)          # una sola fuente compartida
    assert coord.sectores_libres(0) == [0, 1, 2]           # el 0 es suyo; el 3 no está libre
    # un mensaje al pizarrón = una copia por dron
    assert coord.canal.enviados == 2


def test_mensajeria_buzones_y_difusion_por_copias():
    coord = CoordinadorMensajeria(sectores_2x2(), CanalComunicacion(retraso=1))
    drones = [DronFalso(i, (2, 2)) for i in range(3)]
    coord.paso(1, drones)
    assert coord.canal.enviados == 3 * 2                   # cada difusión -> N-1 copias
    coord.paso(2, drones)
    assert coord.vista_de(1).reclamo_de(0) is not None     # el 1 sabe lo del 0
    assert coord.vista_de(0).reclamo_de(0) is None         # nadie se envía a sí mismo
    assert coord.vista_de(0) is not coord.vista_de(1)      # cada dron tiene su visión


def test_mensajeria_perdida_genera_visiones_distintas():
    coord = CoordinadorMensajeria(sectores_2x2(), CanalComunicacion())
    coord.canal.hook_perdida = lambda m, destino: destino == 2
    drones = [DronFalso(0, (2, 2)), DronFalso(1, (18, 18)), DronFalso(2, (12, 2))]
    coord.paso(1, drones)
    assert coord.vista_de(1).reclamo_de(0) is not None
    assert coord.vista_de(2).reclamo_de(0) is None          # al 2 no le llegó


def test_pizarron_caido_congela_la_informacion():
    coord = CoordinadorPizarron(sectores_2x2())
    coord.pizarron.disponible = False
    coord.paso(1, [DronFalso(0, (2, 2))])
    assert coord.pizarron.tabla.reclamos() == []
    assert coord.metricas()["escrituras_rechazadas"] == 1


def test_fabrica_de_coordinadores():
    assert isinstance(crear_coordinador("pizarron", sectores_2x2()), CoordinadorPizarron)
    assert isinstance(crear_coordinador(" Mensajeria_Directa ", sectores_2x2()),
                      CoordinadorMensajeria)
    with pytest.raises(ValueError):
        crear_coordinador("telepatia", sectores_2x2())
    with pytest.raises(ValueError):
        CoordinadorPizarron(sectores_2x2(), periodo_informe=5, timeout_informe=5)
    with pytest.raises(ValueError):
        CoordinadorPizarron(sectores_2x2()).registrar_dron(ID_PIZARRON)


# ---- 6. Asignación coordinada: sin duplicados, conflictos y reasignación ---------------
@pytest.mark.parametrize("mecanismo", MECANISMOS)
@pytest.mark.parametrize("retraso", [0, 3])
def test_conflicto_inicial_se_resuelve_sin_duplicados(mecanismo, retraso):
    # Los 4 drones arrancan juntos en la misma esquina: todos querrán el sector 0.
    coord = crear_coordinador(mecanismo, sectores_2x2(), CanalComunicacion(retraso=retraso))
    drones = [DronFalso(i, (1, 1)) for i in range(4)]
    coord.paso(1, drones)
    assert len({coord.asignacion_de(d.id) for d in drones}) < 4   # hubo conflicto
    correr(coord, drones, 2, 30)
    final = asignacion_operativa(coord, drones)
    assert sorted(final.values()) == [0, 1, 2, 3]                 # uno por sector
    assert evaluar_asignacion(final, coord.sectores).valida


@pytest.mark.parametrize("mecanismo", MECANISMOS)
def test_mas_drones_que_sectores_refuerza_prioritarios(mecanismo):
    coord = crear_coordinador(mecanismo, sectores_2x2(), CanalComunicacion(retraso=1))
    drones = [DronFalso(i, (i * 3, 5)) for i in range(6)]
    correr(coord, drones, 1, 30)
    final = asignacion_operativa(coord, drones)
    conteo = {s: list(final.values()).count(s) for s in range(4)}
    assert conteo == {0: 2, 1: 1, 2: 1, 3: 2}
    assert evaluar_asignacion(final, coord.sectores).valida


@pytest.mark.parametrize("mecanismo", MECANISMOS)
def test_reasignacion_cuando_un_dron_queda_inactivo(mecanismo):
    coord = crear_coordinador(mecanismo, sectores_2x2(), CanalComunicacion(retraso=1),
                              periodo_informe=5, timeout_informe=15)
    drones = [DronFalso(i, (i * 5, i * 5)) for i in range(4)]
    correr(coord, drones, 1, 20)
    caido = next(d for d in drones if coord.asignacion_de(d.id) == 0)
    caido.estado_operativo = EstadoOperativo.INACTIVO     # falla silenciosa
    correr(coord, drones, 21, 25)
    assert 0 not in asignacion_operativa(coord, drones).values()  # aún no lo detectan
    correr(coord, drones, 26, 60)
    final = asignacion_operativa(coord, drones)
    assert 0 in final.values()                        # un sano tomó el prioritario
    assert evaluar_asignacion(final, coord.sectores).valida
    assert coord.metricas()["expiraciones"] >= 1


@pytest.mark.parametrize("mecanismo", MECANISMOS)
def test_dron_que_va_a_recargar_libera_su_sector(mecanismo):
    coord = crear_coordinador(mecanismo, sectores_2x2())
    drones = [DronFalso(0, (2, 2)), DronFalso(1, (18, 18))]
    correr(coord, drones, 1, 3)
    drones[0].estado_operativo = EstadoOperativo.EN_RECARGA
    coord.paso(4, drones)
    assert coord.asignacion_de(0) is None
    assert coord.vista_de(1).reclamo_de(0) is None    # liberación inmediata, sin timeout
    coord.paso(5, drones)
    assert coord.asignacion_de(1) in (0, 3)


@pytest.mark.parametrize("mecanismo", MECANISMOS)
def test_asignacion_converge_con_perdida(mecanismo):
    coord = crear_coordinador(mecanismo, sectores_2x2(),
                              CanalComunicacion(retraso=2, prob_perdida=0.3, semilla=4))
    drones = [DronFalso(i, (1, 1)) for i in range(4)]
    correr(coord, drones, 1, 80)
    assert evaluar_asignacion(asignacion_operativa(coord, drones), coord.sectores).valida


# ---- 7. Mensajes de relevo (solo transporte) ----------------------------------------------
@pytest.mark.parametrize("mecanismo", MECANISMOS)
def test_flujo_de_relevo_solicitud_confirmacion_y_rechazo(mecanismo):
    coord = crear_coordinador(mecanismo, sectores_2x2(), CanalComunicacion(retraso=2))
    for i in range(3):
        coord.registrar_dron(i)
    coord.solicitar_relevo(emisor=0, sector=3, paso=1, datos={"bateria": 18.0})
    assert coord.recibir(1) == []                       # aún en camino
    coord.paso(3, [])
    solicitud = coord.recibir(1)
    assert [m.tipo for m in solicitud] == [TipoMensaje.SOLICITAR_RELEVO]
    assert solicitud[0].contenido["bateria"] == 18.0 and solicitud[0].contenido["sector"] == 3
    assert [m.tipo for m in coord.recibir(2)] == [TipoMensaje.SOLICITAR_RELEVO]  # difusión
    assert coord.recibir(0) == []                       # el emisor no recibe su propio mensaje
    assert coord.recibir(1) == []                       # leer consume los nuevos

    coord.confirmar_relevo(emisor=1, receptor=0, sector=3, paso=3)
    coord.rechazar_relevo(emisor=2, receptor=0, sector=3, paso=3, motivo="bateria baja")
    coord.paso(5, [])
    tipos = [m.tipo for m in coord.recibir(0)]
    assert tipos == [TipoMensaje.CONFIRMAR_RELEVO, TipoMensaje.RECHAZAR_RELEVO]
    assert coord.recibir(2) == []                       # la confirmación era solo para el 0


@pytest.mark.parametrize("mecanismo", MECANISMOS)
def test_fijar_sector_para_relevo_tiene_prioridad(mecanismo):
    coord = crear_coordinador(mecanismo, sectores_2x2(), CanalComunicacion(retraso=1))
    drones = [DronFalso(i, (i * 5, i * 5)) for i in range(4)]
    correr(coord, drones, 1, 20)
    saliente = next(d for d in drones if coord.asignacion_de(d.id) == 3)
    sustituto = DronFalso(9, (15, 15), estado_operativo=EstadoOperativo.EN_RELEVO)
    # Lo que haría el Integrante 4 tras recibir la confirmación:
    coord.fijar_sector(sustituto.id, 3, paso=21)
    saliente.estado_operativo = EstadoOperativo.EN_RECARGA
    correr(coord, drones + [sustituto], 21, 30)
    assert coord.asignacion_de(9) == 3                 # aunque está EN_RELEVO, conserva el sector
    assert coord.asignacion_de(saliente.id) is None
    assert evaluar_asignacion(asignacion_operativa(coord, drones + [sustituto])
                              | {9: 3}, coord.sectores).valida


# ---- 8. Integración con drones y entorno reales (sin modificarlos) ------------------------
@pytest.mark.parametrize("mecanismo", MECANISMOS)
def test_integracion_con_drones_reales_de_la_etapa_2(entorno, mecanismo):
    posiciones = colocar_drones_aleatorios(entorno, 4, random.Random(1))
    drones = [crear_dron("basado_en_modelos", i, p, semilla=i) for i, p in enumerate(posiciones)]
    coord = crear_coordinador(mecanismo, entorno.sectores, CanalComunicacion(retraso=1))
    for paso in range(1, 21):
        coord.paso(paso, drones)
        for dron in drones:
            dron.ejecutar_paso(entorno, paso)
    assert evaluar_asignacion(asignacion_operativa(coord, drones), entorno.sectores).valida


def test_dron_coordinado_patrulla_su_sector(entorno):
    sector = entorno.sectores[2]
    inicio = sorted(entorno.sectores[0].celdas)[0]
    dron = DronCoordinado(0, inicio, entorno=entorno, semilla=0)
    dron.sector_asignado = sector.id
    for paso in range(1, 81):
        dron.ejecutar_paso(entorno, paso)
    ultimas = dron.historial_posiciones[-30:]
    assert sum(1 for c in ultimas if c in sector.celdas) >= 25  # llegó y se queda


def test_dron_coordinado_sin_sector_equivale_al_original(entorno):
    inicio = sorted(entorno.celdas_transitables())[100]
    original = crear_dron("basado_en_modelos", 0, inicio, semilla=3)
    adaptado = DronCoordinado(0, inicio, entorno=entorno, semilla=3)
    for paso in range(1, 41):
        original.ejecutar_paso(entorno, paso)
        adaptado.ejecutar_paso(entorno, paso)
    assert original.historial_posiciones == adaptado.historial_posiciones
