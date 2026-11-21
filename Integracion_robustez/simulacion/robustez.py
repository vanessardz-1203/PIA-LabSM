"""Inyección reproducible de perturbaciones en una simulación discreta."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from Programacion_de_agentes.simulacion.agentes import EstadoOperativo


@dataclass(frozen=True)
class Evento:
    paso: int
    tipo: str
    dron_id: int | None = None
    valor: float | int | None = None
    posicion: tuple[int, int] | None = None


class GestorRobustez:
    TIPOS = {'falla_dron', 'perdida_mensajes', 'retraso_mensajes', 'caida_pizarron', 'restaurar_pizarron', 'obstaculo', 'retirar_obstaculo'}

    def __init__(self, eventos: list[Evento] | None = None):
        self.eventos = sorted(eventos or [], key=lambda e: e.paso)
        self.aplicados: list[dict[str, Any]] = []
        for e in self.eventos:
            if e.paso < 1 or e.tipo not in self.TIPOS:
                raise ValueError(f'Evento no válido: {e}')

    def aplicar(self, paso: int, drones: list, entorno, coordinador, canal) -> list[Evento]:
        aplicados = []
        for e in self.eventos:
            if e.paso != paso:
                continue
            if e.tipo == 'falla_dron':
                objetivo = next((d for d in drones if d.id == e.dron_id), None)
                if objetivo is None:
                    raise ValueError(f'Dron inexistente: {e.dron_id}')
                objetivo.estado_operativo = EstadoOperativo.INACTIVO
            elif e.tipo == 'perdida_mensajes':
                if e.valor is None or not 0 <= float(e.valor) <= 1:
                    raise ValueError('La pérdida debe estar entre 0 y 1')
                canal.prob_perdida = float(e.valor)
            elif e.tipo == 'retraso_mensajes':
                if e.valor is None or int(e.valor) < 0:
                    raise ValueError('El retraso no puede ser negativo')
                canal.retraso = int(e.valor)
            elif e.tipo in ('caida_pizarron', 'restaurar_pizarron'):
                pizarron = getattr(coordinador, 'pizarron', None)
                if pizarron is None:
                    raise ValueError('Este evento requiere coordinación por pizarrón')
                pizarron.disponible = e.tipo == 'restaurar_pizarron'
            elif e.tipo == 'obstaculo':
                if e.posicion is None or not entorno.es_transitable(e.posicion):
                    raise ValueError('El obstáculo debe situarse en celda transitable')
                if any(d.posicion == e.posicion and d.esta_operativo for d in drones):
                    raise ValueError('No se puede colocar un obstáculo sobre un dron activo')
                if e.posicion in entorno.recargas:
                    raise ValueError('No se puede bloquear una estación de recarga')
                entorno.edificios.add(e.posicion)
            elif e.tipo == 'retirar_obstaculo':
                if e.posicion is None:
                    raise ValueError('Se requiere la posición del obstáculo')
                entorno.edificios.discard(e.posicion)
            self.aplicados.append({'paso': paso, 'tipo': e.tipo, 'dron_id': e.dron_id, 'valor': e.valor, 'posicion': e.posicion})
            aplicados.append(e)
        return aplicados
