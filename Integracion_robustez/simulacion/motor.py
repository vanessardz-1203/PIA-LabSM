"""Motor integrado: percepción, coordinación, energía, relevos y métricas."""
from __future__ import annotations
import random
from dataclasses import dataclass, asdict
from Construccion_de_entorno.simulacion.entorno import generar_mapa_industrial
from Construccion_de_entorno.simulacion.cobertura import calcular_cobertura, cobertura_prioritaria, colocar_drones_aleatorios
from Programacion_de_agentes.simulacion.agentes import crear_dron, EstadoOperativo
from Coordinacion_multiagente.simulacion.coordinacion import CanalComunicacion, crear_coordinador
from Gestion_energetica_relevos.simulacion.energia import GestorEnergia
from Gestion_energetica_relevos.simulacion.controlador import ControladorRelevos
from Integracion_robustez.simulacion.robustez import GestorRobustez, Evento


@dataclass
class RegistroPaso:
    paso: int
    cobertura_pct: float
    cobertura_prioritaria_pct: float
    redundancia_pct: float
    puntos_ciegos: int
    activos: int
    bateria_media_pct: float
    relevos_completados: int
    relevos_fallidos: int
    mensajes_enviados: int


class MotorSimulacion:
    def __init__(self, *, drones=4, pasos=150, semilla=42, mecanismo='pizarron',
                 arquitectura='basado_en_modelos', retraso=0, perdida=0.0,
                 eventos=None, bateria_inicial=100.0, consumo_por_paso=0.5,
                 radio=5.0, usar_relevos=True):
        if drones < 1 or pasos < 1:
            raise ValueError('drones y pasos deben ser positivos')
        self.pasos = pasos
        self.entorno = generar_mapa_industrial(semilla=semilla)
        posiciones = colocar_drones_aleatorios(self.entorno, drones, random.Random(semilla + 100))
        self.drones = [crear_dron(arquitectura, i+1, pos, bateria=bateria_inicial,
                    consumo_por_paso=consumo_por_paso, radio_observacion=radio,
                    semilla=semilla + i + 1) for i, pos in enumerate(posiciones)]
        self.radio = radio
        self.canal = CanalComunicacion(retraso=retraso, prob_perdida=perdida, semilla=semilla + 200)
        self.coordinador = crear_coordinador(mecanismo, self.entorno.sectores, self.canal)
        self.energia = GestorEnergia()
        self.relevos = ControladorRelevos(self.entorno, self.energia, self.coordinador)
        self.robustez = GestorRobustez(eventos)
        self.usar_relevos = usar_relevos
        self.registros: list[RegistroPaso] = []
        self.vistas_acumuladas = set()
        self.eventos_observados = []

    def ejecutar(self):
        for t in range(1, self.pasos + 1):
            self.eventos_observados.extend(self.robustez.aplicar(t, self.drones, self.entorno, self.coordinador, self.canal))
            self.coordinador.paso(t, self.drones)
            # Un relevo controla directamente el movimiento de su sustituto.
            if self.usar_relevos:
                for dron in self.drones:
                    if dron.esta_operativo and dron.estado_operativo == EstadoOperativo.VIGILANDO:
                        if dron.id not in self.relevos.relevos:
                            self.relevos.iniciar(dron, self.drones, t)
                self.relevos.avanzar(self.drones, t)
                self.relevos.avanzar_recargas(self.drones)
            ocupados_relevo = {r.sustituto_id for r in self.relevos.relevos.values()}
            ocupados_relevo.update(self.relevos.drones_recargando)
            ocupados_relevo.update(self.relevos.relevos)
            for dron in self.drones:
                if not dron.esta_operativo or dron.id in ocupados_relevo:
                    continue
                if dron.estado_operativo in (EstadoOperativo.RESERVA, EstadoOperativo.EN_RECARGA, EstadoOperativo.EN_RELEVO):
                    continue
                # Compatibilidad: sin sector_asignado en DronBase, el adaptador es requerido
                # para patrullaje restringido. Aquí se conserva la política original.
                dron.ejecutar_paso(self.entorno, t)
            activos = [d for d in self.drones if d.esta_operativo and d.estado_operativo == EstadoOperativo.VIGILANDO]
            cobertura = calcular_cobertura(self.entorno, [d.posicion for d in activos], self.radio)
            self.vistas_acumuladas.update(cobertura.cubiertas)
            self.registros.append(RegistroPaso(t, 100*cobertura.cobertura,
                100*cobertura_prioritaria(self.entorno, cobertura),
                100*cobertura.cobertura_redundante, len(cobertura.puntos_ciegos),
                len(activos), sum(100*d.bateria/d.bateria_max for d in self.drones)/len(self.drones),
                self.relevos.completados, self.relevos.fallidos,
                int(self.canal.metricas()['enviados'])))
        return self.resumen()

    def resumen(self):
        if not self.registros:
            raise RuntimeError('Ejecuta la simulación antes de obtener el resumen')
        n = len(self.registros)
        return {
            'pasos': n,
            'cobertura_inst_media_pct': round(sum(x.cobertura_pct for x in self.registros)/n, 3),
            'cobertura_acumulada_pct': round(100*len(self.vistas_acumuladas)/len(self.entorno.celdas_transitables()), 3),
            'cobertura_prioritaria_media_pct': round(sum(x.cobertura_prioritaria_pct for x in self.registros)/n, 3),
            'redundancia_media_pct': round(sum(x.redundancia_pct for x in self.registros)/n, 3),
            'puntos_ciegos_medios': round(sum(x.puntos_ciegos for x in self.registros)/n, 3),
            'relevos_completados': self.relevos.completados,
            'relevos_fallidos': self.relevos.fallidos,
            'mensajes_enviados': self.canal.metricas()['enviados'],
            'eventos_aplicados': len(self.robustez.aplicados),
        }

    def registros_dict(self):
        return [asdict(x) for x in self.registros]
