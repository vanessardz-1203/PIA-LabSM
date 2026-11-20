"""
Integrante 3 · Comunicación y coordinación multiagente (Etapa 3, Práctica 2)

Implementa la capa de comunicación entre drones y la asignación coordinada de
sectores. Está pensada para llamarse desde un ciclo de simulación por paso y NO
modifica a los drones de la Etapa 2: solo lee ``id``, ``posicion``,
``estado_operativo`` y ``esta_operativo`` de cada uno.

Piezas (en el orden en que se construyen unas sobre otras):

1. :class:`TipoMensaje` y :class:`Mensaje`: la unidad de información que viaja.
2. :class:`CanalComunicacion`: el "medio" por donde viajan los mensajes; aplica
   retraso (en pasos) y pérdida (probabilística con semilla) y lleva métricas.
3. :class:`TablaReclamos`: lo que un observador sabe sobre qué dron vigila qué
   sector (la usan tanto el pizarrón como cada dron en la mensajería directa).
4. :func:`elegir_sector`: regla de asignación que evita redundancias usando
   ``Sector.peso`` y resuelve conflictos con una precedencia determinista.
5. :class:`CoordinadorBase` y sus dos mecanismos intercambiables:
   :class:`CoordinadorPizarron` (pizarrón compartido) y
   :class:`CoordinadorMensajeria` (buzones dron a dron). Ambos exponen
   exactamente la misma API para poder compararlos con el mismo experimento.
6. Transporte de relevos (:meth:`CoordinadorBase.solicitar_relevo`,
   :meth:`CoordinadorBase.confirmar_relevo`, ...). La decisión de cuándo hace
   falta un relevo y quién es el sustituto pertenece al Integrante 4; aquí solo
   se transportan sus mensajes.

Uso típico desde un ciclo de simulación::

    coord = crear_coordinador("pizarron", entorno.sectores,
                              canal=CanalComunicacion(retraso=2, prob_perdida=0.1, semilla=7))
    for paso in range(1, pasos + 1):
        coord.paso(paso, drones)                  # entrega mensajes y (re)asigna sectores
        for dron in drones:
            sector = coord.asignacion_de(dron.id) # sector que le toca vigilar
            ...
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Protocol

from Construccion_de_entorno.simulacion.entorno import Celda, Sector
from Programacion_de_agentes.simulacion.agentes import EstadoOperativo

# Identificador reservado del pizarrón como destinatario dentro del canal.
# Se usa un entero negativo porque los drones del repositorio usan ids >= 0.
ID_PIZARRON = -1


# =============================================================================
# 1. Mensajes
# =============================================================================
class TipoMensaje(str, Enum):
    """Tipos de mensaje del protocolo de coordinación.

    Los cuatro primeros los pide el enunciado. Se agregan dos más:

    - ``INFORME_SECTOR``: informe periódico "sigo vigilando el sector X". Cumple
      dos funciones con un solo mensaje: (a) compartir qué sectores se están
      vigilando y cuándo fue la última vez, y (b) servir de *latido* (señal de
      vida). Si un dron deja de enviar informes (falla, se queda sin batería),
      los demás borran su reclamo tras un tiempo y reasignan el sector. Sin este
      mensaje no habría forma de detectar a un dron que "dejó de responder".
    - ``RECHAZAR_RELEVO``: respuesta negativa a una solicitud de relevo, para que
      quien pidió el relevo no se quede esperando indefinidamente una
      confirmación que nunca llegará (por ejemplo, si el candidato tiene poca
      batería). Es el caso "no existe sustituto disponible" del Integrante 4.
    """

    RECLAMAR_SECTOR = "reclamar_sector"
    LIBERAR_SECTOR = "liberar_sector"
    INFORME_SECTOR = "informe_sector"
    SOLICITAR_RELEVO = "solicitar_relevo"
    CONFIRMAR_RELEVO = "confirmar_relevo"
    RECHAZAR_RELEVO = "rechazar_relevo"


# Mensajes que modifican "quién vigila qué" (los procesa la tabla de reclamos).
TIPOS_ASIGNACION: frozenset[TipoMensaje] = frozenset({
    TipoMensaje.RECLAMAR_SECTOR,
    TipoMensaje.LIBERAR_SECTOR,
    TipoMensaje.INFORME_SECTOR,
})
# Mensajes de relevo: solo se transportan hasta el buzón/pizarrón del receptor.
TIPOS_RELEVO: frozenset[TipoMensaje] = frozenset({
    TipoMensaje.SOLICITAR_RELEVO,
    TipoMensaje.CONFIRMAR_RELEVO,
    TipoMensaje.RECHAZAR_RELEVO,
})


@dataclass(frozen=True)
class Mensaje:
    """Unidad de información que un dron envía a otro (o a todos).

    Atributos:
        emisor: Id del dron que envía.
        receptor: Id del dron destinatario, o ``None`` para difusión (a todos).
        tipo: Clase de mensaje (:class:`TipoMensaje`).
        contenido: Datos del mensaje (por ejemplo ``{"sector": 2}``).
        paso_envio: Paso de simulación en el que se envió.

    Decisión de diseño: es inmutable (``frozen=True``) y ``contenido`` se
    envuelve en un ``MappingProxyType`` de solo lectura. En la mensajería
    directa la misma instancia se entrega a varios buzones; si un receptor
    pudiera modificarla, alteraría lo que leen los demás. Así un mensaje se
    comporta como algo que "ya se dijo" y no se puede cambiar.
    """

    emisor: int
    receptor: int | None
    tipo: TipoMensaje
    # hash=False: un diccionario no es "hasheable"; el mensaje se compara por
    # valor pero se identifica por sus demás campos.
    contenido: Mapping[str, Any] = field(default_factory=dict, hash=False)
    paso_envio: int = 0

    def __post_init__(self) -> None:
        if self.paso_envio < 0:
            raise ValueError("paso_envio debe ser mayor o igual a 0")
        # Permite crear mensajes con el texto del tipo ("reclamar_sector").
        if not isinstance(self.tipo, TipoMensaje):
            object.__setattr__(self, "tipo", TipoMensaje(self.tipo))
        # Copia defensiva + vista de solo lectura (ver docstring).
        object.__setattr__(self, "contenido", MappingProxyType(dict(self.contenido)))

    @property
    def es_difusion(self) -> bool:
        """``True`` si el mensaje va dirigido a todos los drones."""
        return self.receptor is None


# =============================================================================
# 2. Canal de comunicación (retraso + pérdida + métricas)
# =============================================================================
@dataclass(frozen=True)
class Entrega:
    """Copia de un mensaje en camino hacia un destinatario concreto."""

    destinatario: int
    mensaje: Mensaje
    paso_entrega: int

    @property
    def retraso(self) -> int:
        """Pasos transcurridos entre el envío y la entrega."""
        return self.paso_entrega - self.mensaje.paso_envio


class CanalComunicacion:
    """Medio de transmisión compartido por ambos mecanismos de coordinación.

    Modela dos imperfecciones de una red real:

    - **Retraso**: un mensaje enviado en el paso ``t`` llega en el paso
      ``t + retraso (+ variación aleatoria opcional)``.
    - **Pérdida**: cada copia se pierde con probabilidad ``prob_perdida``.

    Decisión de diseño: el pizarrón y la mensajería directa usan *el mismo*
    canal. Así, cuando se comparan, la única diferencia es cómo se organiza la
    información (central vs. distribuida), no la calidad de la red.

    Cada destinatario recibe una copia independiente: en una difusión a 5
    drones pueden perderse 2 copias y llegar 3. Esto es lo que hace que, con
    pérdida, en la mensajería directa cada dron pueda tener una visión distinta.

    Puntos de inyección para el Integrante 5 (robustez):
        - ``retraso``, ``retraso_variable`` y ``prob_perdida`` se pueden cambiar
          en cualquier paso (son atributos públicos).
        - ``hook_perdida(mensaje, destinatario) -> bool``: función opcional que
          fuerza la pérdida de mensajes concretos (por ejemplo, aislar a un dron
          o cortar la comunicación con el pizarrón).
    """

    def __init__(
        self,
        retraso: int = 0,
        prob_perdida: float = 0.0,
        semilla: int | None = None,
        retraso_variable: int = 0,
    ) -> None:
        """Crea el canal.

        Args:
            retraso: Retraso fijo en pasos (>= 0). ``0`` = llega en el mismo paso.
            prob_perdida: Probabilidad de perder cada copia, en ``[0, 1]``.
            semilla: Semilla del generador aleatorio (reproducibilidad).
            retraso_variable: Variación máxima extra (uniforme en ``[0, v]``).
        """
        if retraso < 0 or retraso_variable < 0:
            raise ValueError("retraso y retraso_variable deben ser >= 0")
        if not 0.0 <= prob_perdida <= 1.0:
            raise ValueError("prob_perdida debe estar en [0, 1]")
        self.retraso: int = int(retraso)
        self.retraso_variable: int = int(retraso_variable)
        self.prob_perdida: float = float(prob_perdida)
        self.rng: random.Random = random.Random(semilla)
        self.hook_perdida: Callable[[Mensaje, int], bool] | None = None

        self._pendientes: list[Entrega] = []
        # Métricas (se cuentan copias, porque cada copia consume red).
        self.enviados: int = 0
        self.entregados: int = 0
        self.perdidos: int = 0
        self._suma_retrasos: int = 0
        self.enviados_por_tipo: dict[str, int] = {}

    def enviar(self, mensaje: Mensaje, destinatarios: Iterable[int]) -> int:
        """Pone en camino una copia del mensaje para cada destinatario.

        Returns:
            Número de copias que NO se perdieron (llegarán más adelante).
        """
        en_camino = 0
        for destinatario in destinatarios:
            self.enviados += 1
            clave = mensaje.tipo.value
            self.enviados_por_tipo[clave] = self.enviados_por_tipo.get(clave, 0) + 1
            # Se sortea SIEMPRE, aunque prob_perdida sea 0, para que la secuencia
            # aleatoria no dependa de los valores configurados.
            perdido = self.rng.random() < self.prob_perdida
            if self.hook_perdida is not None and self.hook_perdida(mensaje, destinatario):
                perdido = True
            if perdido:
                self.perdidos += 1
                continue
            extra = self.rng.randint(0, self.retraso_variable) if self.retraso_variable else 0
            self._pendientes.append(
                Entrega(destinatario, mensaje, mensaje.paso_envio + self.retraso + extra)
            )
            en_camino += 1
        return en_camino

    def entregar(self, paso_actual: int) -> list[Entrega]:
        """Saca del canal las copias cuyo paso de entrega ya llegó.

        Se devuelven ordenadas por paso de entrega (y por orden de envío en
        caso de empate) para que la simulación sea determinista.
        """
        listas = [e for e in self._pendientes if e.paso_entrega <= paso_actual]
        if not listas:
            return []
        self._pendientes = [e for e in self._pendientes if e.paso_entrega > paso_actual]
        listas.sort(key=lambda e: e.paso_entrega)  # sort es estable
        self.entregados += len(listas)
        self._suma_retrasos += sum(e.retraso for e in listas)
        return listas

    @property
    def pendientes(self) -> int:
        """Copias que siguen viajando (enviadas, ni entregadas ni perdidas)."""
        return len(self._pendientes)

    @property
    def retraso_medio(self) -> float:
        """Retraso medio (en pasos) de los mensajes efectivamente entregados."""
        return self._suma_retrasos / self.entregados if self.entregados else 0.0

    @property
    def tasa_perdida(self) -> float:
        """Fracción de copias perdidas sobre las enviadas."""
        return self.perdidos / self.enviados if self.enviados else 0.0

    def metricas(self) -> dict[str, float | int]:
        """Resumen de métricas del canal."""
        return {
            "enviados": self.enviados,
            "entregados": self.entregados,
            "perdidos": self.perdidos,
            "pendientes": self.pendientes,
            "retraso_medio": round(self.retraso_medio, 4),
            "tasa_perdida": round(self.tasa_perdida, 4),
        }


# =============================================================================
# 3. Tabla de reclamos: "quién vigila qué" según un observador
# =============================================================================
@dataclass(frozen=True)
class Reclamo:
    """Afirmación "el dron X vigila el sector S".

    Atributos:
        id_dron: Dron que reclama el sector.
        sector: Id del sector reclamado.
        paso_reclamo: Paso en que el dron empezó a vigilar este sector.
        ultimo_informe: Paso en que LLEGÓ el último mensaje de ese dron.
        fijo: ``True`` si la asignación fue impuesta desde fuera (por ejemplo,
            un relevo del Integrante 4) y no debe reevaluarse.
    """

    id_dron: int
    sector: int
    paso_reclamo: int
    ultimo_informe: int
    fijo: bool = False

    @property
    def precedencia(self) -> tuple[int, int, int]:
        """Clave de prioridad para resolver conflictos (menor = gana).

        Orden: primero los reclamos fijos (relevos), después el que llegó antes
        al sector y, si empatan, el de id menor. Es determinista y todos los
        drones la calculan igual sin tener que negociar, así que con la misma
        información todos llegan a la misma conclusión.
        """
        return (0 if self.fijo else 1, self.paso_reclamo, self.id_dron)


class TablaReclamos:
    """Conocimiento de un observador sobre qué sectores vigila cada dron.

    En el pizarrón hay UNA tabla compartida por todos. En la mensajería directa
    cada dron tiene la SUYA y la va llenando con los mensajes que le llegan.
    Separarla así permite que ambos mecanismos usen exactamente la misma lógica
    de asignación y solo cambie cómo viaja la información.
    """

    def __init__(self) -> None:
        self._por_dron: dict[int, Reclamo] = {}
        self._ultimo_paso_de: dict[int, int] = {}
        self.ultima_vigilancia: dict[int, int] = {}

    def aplicar(self, mensaje: Mensaje, paso_llegada: int | None = None) -> bool:
        """Incorpora un mensaje de asignación. Devuelve ``True`` si cambió algo.

        Args:
            mensaje: Mensaje recibido.
            paso_llegada: Paso en que llegó. Se guarda como ``ultimo_informe``
                para medir el "tiempo sin noticias" desde la LLEGADA y no desde
                el envío. Decisión tomada tras el experimento: si se mide desde
                el envío, el retraso se "come" el margen del timeout (con
                retraso 10 y timeout 15 bastaba perder un solo informe para dar
                por caído a un dron sano). Si es ``None`` se usa ``paso_envio``.

        Se ignoran mensajes más viejos que el último conocido de ese emisor:
        con retraso variable pueden llegar desordenados, y un "reclamo" viejo no
        debe pisar un "liberar" más reciente.
        """
        if mensaje.tipo not in TIPOS_ASIGNACION:
            return False
        if mensaje.paso_envio < self._ultimo_paso_de.get(mensaje.emisor, -1):
            return False
        self._ultimo_paso_de[mensaje.emisor] = mensaje.paso_envio

        if mensaje.tipo is TipoMensaje.LIBERAR_SECTOR:
            return self._por_dron.pop(mensaje.emisor, None) is not None

        sector = int(mensaje.contenido["sector"])
        # Un dron solo vigila un sector: el nuevo reclamo sustituye al anterior.
        # Por eso perder un LIBERAR al cambiar de sector no deja basura.
        self._por_dron[mensaje.emisor] = Reclamo(
            id_dron=mensaje.emisor,
            sector=sector,
            paso_reclamo=int(mensaje.contenido.get("paso_reclamo", mensaje.paso_envio)),
            ultimo_informe=paso_llegada if paso_llegada is not None else mensaje.paso_envio,
            fijo=bool(mensaje.contenido.get("fijo", False)),
        )
        if mensaje.contenido.get("en_sector", False):
            previo = self.ultima_vigilancia.get(sector, -1)
            self.ultima_vigilancia[sector] = max(previo, mensaje.paso_envio)
        return True

    def expirar(self, paso_actual: int, timeout: int) -> list[int]:
        """Borra los reclamos de drones que no informan desde hace ``timeout`` pasos.

        Es el mecanismo de detección de drones caídos: un dron INACTIVO no puede
        enviar mensajes, así que su reclamo "caduca" y el sector queda libre.

        Returns:
            Ids de los drones cuyos reclamos expiraron.
        """
        caducos = [
            r.id_dron for r in self._por_dron.values()
            if paso_actual - r.ultimo_informe > timeout
        ]
        for id_dron in caducos:
            del self._por_dron[id_dron]
        return caducos

    def reclamos(self) -> list[Reclamo]:
        """Todos los reclamos vigentes, ordenados por id de dron."""
        return [self._por_dron[k] for k in sorted(self._por_dron)]

    def reclamo_de(self, id_dron: int) -> Reclamo | None:
        """Reclamo vigente de un dron, si lo hay."""
        return self._por_dron.get(id_dron)

    def reclamantes(self, sector: int, excluir: int | None = None) -> list[int]:
        """Ids de los drones que reclaman ``sector`` (opcionalmente sin ``excluir``)."""
        return sorted(
            r.id_dron for r in self._por_dron.values()
            if r.sector == sector and r.id_dron != excluir
        )


# =============================================================================
# 4. Regla de asignación (evita redundancias y resuelve conflictos)
# =============================================================================
def clave_sector(sector: Sector, ocupantes: int) -> tuple[float, int]:
    """Qué tan conveniente es sumarse a ``sector`` si ya tiene ``ocupantes``.

    Menor es mejor. El primer término ``(ocupantes + 1) / peso`` reparte los
    drones en proporción al peso: un sector prioritario (peso 2) "aguanta" dos
    drones antes de parecer tan cargado como un sector normal con uno. El
    segundo término desempata a favor del sector con menos drones, de modo que
    nunca se duplica un sector mientras haya otro de igual valor vacío.
    """
    return ((ocupantes + 1) / sector.peso, ocupantes)


def centroide(sector: Sector) -> Celda:
    """Celda media (redondeada) del sector; se usa solo para desempatar por cercanía."""
    if not sector.celdas:
        return (0, 0)
    xs = sum(c[0] for c in sector.celdas)
    ys = sum(c[1] for c in sector.celdas)
    n = len(sector.celdas)
    return (round(xs / n), round(ys / n))


def elegir_sector(
    id_dron: int,
    posicion: Celda,
    sectores: Sequence[Sector],
    reclamos_ajenos: Iterable[Reclamo],
    actual: Reclamo | None = None,
    centroides: Mapping[int, Celda] | None = None,
) -> int | None:
    """Decide qué sector debe vigilar un dron según lo que sabe de los demás.

    Reglas:
        1. Cada sector se evalúa con :func:`clave_sector`, contando los drones
           que (según esta información) ya lo reclaman.
        2. Para el sector **actual** solo cuentan los que tienen más
           precedencia que este dron (:attr:`Reclamo.precedencia`). Así, en un
           conflicto (dos drones en el mismo sector) el de mayor precedencia se
           queda y el otro ve su sector "ocupado" y busca otro.
        3. Solo se cambia si otro sector es *estrictamente* mejor (histéresis):
           evita que el dron oscile entre sectores equivalentes.
        4. Empates entre candidatos: el más cercano (al centroide) y luego el id
           menor, para que el resultado sea determinista.
        5. Si la asignación es fija (relevo), no se reevalúa.

    Es una función pura (no guarda estado), así se prueba de forma aislada.

    Returns:
        Id del sector elegido, o ``None`` si no hay sectores con celdas.
    """
    if actual is not None and actual.fijo:
        return actual.sector
    validos = [s for s in sectores if s.celdas]
    if not validos:
        return None
    if centroides is None:
        centroides = {s.id: centroide(s) for s in validos}

    ajenos = [r for r in reclamos_ajenos if r.id_dron != id_dron]
    ocupantes = {s.id: 0 for s in validos}
    for r in ajenos:
        if r.sector in ocupantes:
            ocupantes[r.sector] += 1

    def distancia(s: Sector) -> int:
        cx, cy = centroides[s.id]
        return abs(posicion[0] - cx) + abs(posicion[1] - cy)

    mejor = min(validos, key=lambda s: (clave_sector(s, ocupantes[s.id]), distancia(s), s.id))
    if actual is None:
        return mejor.id

    sector_actual = next((s for s in validos if s.id == actual.sector), None)
    if sector_actual is None:  # su sector ya no existe: se mueve al mejor
        return mejor.id
    con_precedencia = sum(
        1 for r in ajenos
        if r.sector == actual.sector and r.precedencia < actual.precedencia
    )
    if clave_sector(mejor, ocupantes[mejor.id]) < clave_sector(sector_actual, con_precedencia):
        return mejor.id
    return actual.sector


@dataclass(frozen=True)
class EvaluacionAsignacion:
    """Calidad de una asignación global (vista "desde fuera", con la verdad).

    Atributos:
        drones: Drones operativos considerados.
        sin_sector: Drones operativos que no tienen sector.
        sectores_vacios: Sectores sin ningún dron.
        prioritarios_vacios: Sectores prioritarios sin ningún dron.
        duplicados_evitables: Drones "sobrantes" en un sector compartido que
            podrían estar cubriendo un sector vacío. Es la medida de
            **asignación redundante**: tener 2 drones en un sector solo es un
            desperdicio si hay otro sector sin nadie.
        valida: ``True`` si no hay duplicados evitables, nadie está sin sector
            y no queda un prioritario vacío que se pudiera haber cubierto.
    """

    drones: int
    sin_sector: int
    sectores_vacios: int
    prioritarios_vacios: int
    duplicados_evitables: int
    valida: bool


def evaluar_asignacion(
    asignaciones: Mapping[int, int | None],
    sectores: Sequence[Sector],
) -> EvaluacionAsignacion:
    """Mide qué tan buena es la asignación ``{id_dron: sector}`` de drones operativos."""
    validos = [s for s in sectores if s.celdas]
    conteo = {s.id: 0 for s in validos}
    sin_sector = 0
    for sector in asignaciones.values():
        if sector is None or sector not in conteo:
            sin_sector += 1
        else:
            conteo[sector] += 1
    vacios = sum(1 for k in conteo.values() if k == 0)
    prioritarios = [s for s in validos if s.prioritario]
    prio_vacios = sum(1 for s in prioritarios if conteo[s.id] == 0)
    sobrantes = sum(max(0, k - 1) for k in conteo.values())
    duplicados = min(sobrantes, vacios)
    n = len(asignaciones)
    # Con n drones como mucho se pueden cubrir n prioritarios.
    prio_inevitables = max(0, len(prioritarios) - n)
    valida = duplicados == 0 and sin_sector == 0 and prio_vacios <= prio_inevitables
    return EvaluacionAsignacion(n, sin_sector, vacios, prio_vacios, duplicados, valida)


# =============================================================================
# 5. Coordinadores (API común + pizarrón + mensajería directa)
# =============================================================================
class DronCoordinable(Protocol):
    """Lo mínimo que el coordinador necesita leer de un dron.

    ``DronBase`` del Integrante 2 ya cumple este protocolo sin cambios; también
    sirve cualquier objeto de prueba con estos atributos.
    """

    id: int
    posicion: Celda
    estado_operativo: EstadoOperativo

    @property
    def esta_operativo(self) -> bool: ...


@dataclass
class _EstadoPropio:
    """Lo que cada dron sabe de sí mismo (no depende de mensajes)."""

    reclamo: Reclamo | None = None
    ultimo_envio: int = -(10**9)


class CoordinadorBase(ABC):
    """API común de coordinación. Las subclases solo cambian cómo viaja la información.

    Protocolo por paso (:meth:`paso`):
        1. Entregar los mensajes cuyo retraso ya se cumplió.
        2. Borrar reclamos de drones que no informan (detección de fallas).
        3. Para cada dron, según su estado:
           - INACTIVO: no hace nada (un dron caído no puede comunicarse).
           - Operativo: aplica :func:`elegir_sector` con su visión; si cambia de
             sector envía ``RECLAMAR_SECTOR``; si no, cada ``periodo_informe``
             pasos envía ``INFORME_SECTOR`` (latido).
           - En recarga / reserva / en relevo (sin asignación fija): envía
             ``LIBERAR_SECTOR`` una vez para que otro tome su sector.
        4. Entregar otra vez, para que con ``retraso=0`` todo llegue en el mismo
           paso.

    Las decisiones del paso 3 son *simultáneas*: los drones deciden con la
    información que tenían al empezar el paso, como agentes concurrentes
    reales. Por eso, al inicio, dos drones pueden elegir el mismo sector; el
    conflicto se resuelve en cuanto se enteran el uno del otro.
    """

    mecanismo: str = "base"

    def __init__(
        self,
        sectores: Sequence[Sector],
        canal: CanalComunicacion | None = None,
        periodo_informe: int = 5,
        timeout_informe: int = 15,
    ) -> None:
        """Crea el coordinador.

        Args:
            sectores: Sectores del entorno (``entorno.sectores``).
            canal: Canal compartido; por defecto uno perfecto (sin retraso ni pérdida).
            periodo_informe: Cada cuántos pasos un dron reenvía su informe/latido.
            timeout_informe: Pasos sin noticias de un dron para darlo por caído.
                Debe ser mayor que ``periodo_informe``; si no, un dron sano se
                daría por caído entre dos informes.
        """
        if periodo_informe < 1:
            raise ValueError("periodo_informe debe ser >= 1")
        if timeout_informe <= periodo_informe:
            raise ValueError("timeout_informe debe ser mayor que periodo_informe")
        self.sectores: list[Sector] = list(sectores)
        self.canal: CanalComunicacion = canal if canal is not None else CanalComunicacion()
        self.periodo_informe: int = periodo_informe
        self.timeout_informe: int = timeout_informe
        self.centroides: dict[int, Celda] = {s.id: centroide(s) for s in self.sectores}
        self._sector_de_celda: dict[Celda, int] = {
            c: s.id for s in self.sectores for c in s.celdas
        }
        self._propios: dict[int, _EstadoPropio] = {}
        self.paso_actual: int = 0
        self.cambios_sector: int = 0
        self.expiraciones: int = 0

    # ---- registro y ciclo por paso ------------------------------------------
    def registrar_dron(self, id_dron: int) -> None:
        """Da de alta un dron (idempotente). :meth:`paso` lo hace automáticamente."""
        if id_dron == ID_PIZARRON:
            raise ValueError(f"El id {ID_PIZARRON} está reservado para el pizarrón")
        if id_dron not in self._propios:
            self._propios[id_dron] = _EstadoPropio()
            self._al_registrar(id_dron)

    @property
    def ids_drones(self) -> list[int]:
        """Ids registrados, ordenados."""
        return sorted(self._propios)

    def paso(self, paso_actual: int, drones: Iterable[DronCoordinable]) -> None:
        """Ejecuta un paso del protocolo de coordinación (ver docstring de la clase)."""
        drones = list(drones)
        for dron in drones:
            self.registrar_dron(dron.id)
        self.paso_actual = paso_actual
        self._entregar(paso_actual)
        self.expiraciones += self._expirar(paso_actual)
        for dron in drones:
            self._actualizar_dron(dron, paso_actual)
        self._entregar(paso_actual)

    def _actualizar_dron(self, dron: DronCoordinable, paso: int) -> None:
        propio = self._propios[dron.id]
        caido = (
            dron.estado_operativo == EstadoOperativo.INACTIVO
            or getattr(dron, "bateria", 1.0) <= 0.0
        )
        if caido:
            return  # silencio: los demás lo detectarán por timeout

        fijo = propio.reclamo is not None and propio.reclamo.fijo
        if not (dron.esta_operativo or fijo):
            if propio.reclamo is not None:  # salida ordenada (p. ej. va a recargar)
                self._publicar(Mensaje(dron.id, None, TipoMensaje.LIBERAR_SECTOR,
                                       {"sector": propio.reclamo.sector}, paso))
                propio.reclamo = None
                propio.ultimo_envio = paso
            return

        ajenos = [r for r in self._vista(dron.id).reclamos() if r.id_dron != dron.id]
        nuevo = elegir_sector(dron.id, dron.posicion, self.sectores, ajenos,
                              propio.reclamo, self.centroides)
        if nuevo is None:
            return
        if propio.reclamo is None or nuevo != propio.reclamo.sector:
            if propio.reclamo is not None:
                self.cambios_sector += 1
            propio.reclamo = Reclamo(dron.id, nuevo, paso, paso, fijo=False)
            self._enviar_reclamo(dron, TipoMensaje.RECLAMAR_SECTOR, paso)
        elif paso - propio.ultimo_envio >= self.periodo_informe:
            self._enviar_reclamo(dron, TipoMensaje.INFORME_SECTOR, paso)

    def _enviar_reclamo(self, dron: DronCoordinable, tipo: TipoMensaje, paso: int) -> None:
        reclamo = self._propios[dron.id].reclamo
        assert reclamo is not None
        contenido = {
            "sector": reclamo.sector,
            "paso_reclamo": reclamo.paso_reclamo,
            "fijo": reclamo.fijo,
            # Compartir información de sectores vigilados: si el dron está
            # físicamente dentro, el informe cuenta como "sector vigilado ahora".
            "en_sector": self._sector_de_celda.get(dron.posicion) == reclamo.sector,
        }
        self._publicar(Mensaje(dron.id, None, tipo, contenido, paso))
        self._propios[dron.id].ultimo_envio = paso

    def _entregar(self, paso: int) -> None:
        for entrega in self.canal.entregar(paso):
            self._procesar(entrega)

    # ---- consultas (API pública) --------------------------------------------
    def asignacion_de(self, id_dron: int) -> int | None:
        """Sector que el dron ``id_dron`` tiene asignado ahora (o ``None``)."""
        propio = self._propios.get(id_dron)
        return propio.reclamo.sector if propio and propio.reclamo else None

    def asignaciones(self) -> dict[int, int | None]:
        """``{id_dron: sector}`` de todos los drones registrados."""
        return {i: self.asignacion_de(i) for i in self.ids_drones}

    def vista_de(self, id_dron: int) -> TablaReclamos:
        """Información de asignación que ve ``id_dron`` (solo lectura por convención)."""
        self.registrar_dron(id_dron)
        return self._vista(id_dron)

    def sectores_libres(self, id_dron: int) -> list[int]:
        """Sectores que, según lo que sabe ``id_dron``, nadie más vigila."""
        vista = self.vista_de(id_dron)
        return [s.id for s in self.sectores if s.celdas and not vista.reclamantes(s.id, id_dron)]

    def ultima_vigilancia(self, id_dron: int, sector: int) -> int | None:
        """Último paso en que ``id_dron`` sabe que alguien vigiló ``sector``."""
        return self.vista_de(id_dron).ultima_vigilancia.get(sector)

    # ---- asignaciones impuestas desde fuera (para relevos) ------------------
    def fijar_sector(self, id_dron: int, sector: int, paso: int) -> None:
        """Asigna ``sector`` a ``id_dron`` de forma fija (no se reevalúa).

        Pensado para el Integrante 4: cuando un sustituto confirma un relevo,
        su módulo llama a este método. El reclamo fijo tiene la mayor
        precedencia, así que los demás drones le ceden el sector.
        """
        self.registrar_dron(id_dron)
        self._propios[id_dron].reclamo = Reclamo(id_dron, sector, paso, paso, fijo=True)
        self._publicar(Mensaje(id_dron, None, TipoMensaje.RECLAMAR_SECTOR,
                               {"sector": sector, "paso_reclamo": paso, "fijo": True}, paso))
        self._propios[id_dron].ultimo_envio = paso

    def soltar_fijo(self, id_dron: int) -> None:
        """Vuelve a la asignación automática conservando el sector actual."""
        propio = self._propios.get(id_dron)
        if propio and propio.reclamo and propio.reclamo.fijo:
            r = propio.reclamo
            propio.reclamo = Reclamo(r.id_dron, r.sector, r.paso_reclamo, r.ultimo_informe, False)

    def liberar_sector(self, id_dron: int, paso: int) -> None:
        """Libera explícitamente el sector de ``id_dron`` y lo anuncia."""
        propio = self._propios.get(id_dron)
        if propio is None or propio.reclamo is None:
            return
        self._publicar(Mensaje(id_dron, None, TipoMensaje.LIBERAR_SECTOR,
                               {"sector": propio.reclamo.sector}, paso))
        propio.reclamo = None
        propio.ultimo_envio = paso

    # ---- transporte de relevos (la decisión es del Integrante 4) ------------
    def solicitar_relevo(self, emisor: int, sector: int, paso: int,
                         receptor: int | None = None,
                         datos: Mapping[str, Any] | None = None) -> Mensaje:
        """Envía una solicitud de relevo (a un candidato o a todos si ``receptor=None``)."""
        return self._enviar_relevo(emisor, receptor, TipoMensaje.SOLICITAR_RELEVO,
                                   sector, paso, datos)

    def confirmar_relevo(self, emisor: int, receptor: int, sector: int, paso: int,
                         datos: Mapping[str, Any] | None = None) -> Mensaje:
        """El sustituto (``emisor``) confirma que reemplazará a ``receptor``."""
        return self._enviar_relevo(emisor, receptor, TipoMensaje.CONFIRMAR_RELEVO,
                                   sector, paso, datos)

    def rechazar_relevo(self, emisor: int, receptor: int, sector: int, paso: int,
                        motivo: str = "", datos: Mapping[str, Any] | None = None) -> Mensaje:
        """El candidato (``emisor``) avisa que no puede hacer el relevo."""
        extra = dict(datos or {})
        extra["motivo"] = motivo
        return self._enviar_relevo(emisor, receptor, TipoMensaje.RECHAZAR_RELEVO,
                                   sector, paso, extra)

    def _enviar_relevo(self, emisor: int, receptor: int | None, tipo: TipoMensaje,
                       sector: int, paso: int, datos: Mapping[str, Any] | None) -> Mensaje:
        self.registrar_dron(emisor)
        if receptor is not None:
            self.registrar_dron(receptor)
        contenido = dict(datos or {})
        contenido["sector"] = sector
        mensaje = Mensaje(emisor, receptor, tipo, contenido, paso)
        self._publicar(mensaje)
        return mensaje

    # ---- métricas -----------------------------------------------------------
    def metricas(self) -> dict[str, float | int | str]:
        """Métricas de coordinación + métricas del canal."""
        datos: dict[str, float | int | str] = {
            "mecanismo": self.mecanismo,
            "cambios_sector": self.cambios_sector,
            "expiraciones": self.expiraciones,
        }
        datos.update(self.canal.metricas())
        return datos

    # ---- lo único que cambia entre mecanismos -------------------------------
    @abstractmethod
    def _al_registrar(self, id_dron: int) -> None:
        """Prepara las estructuras del mecanismo para un dron nuevo."""

    @abstractmethod
    def _vista(self, id_dron: int) -> TablaReclamos:
        """Tabla de reclamos que consulta ``id_dron`` para decidir."""

    @abstractmethod
    def _publicar(self, mensaje: Mensaje) -> None:
        """Pone un mensaje en el canal según el mecanismo."""

    @abstractmethod
    def _procesar(self, entrega: Entrega) -> None:
        """Aplica una copia que acaba de llegar."""

    @abstractmethod
    def _expirar(self, paso: int) -> int:
        """Borra reclamos caducos; devuelve cuántos se borraron."""

    @abstractmethod
    def recibir(self, id_dron: int) -> list[Mensaje]:
        """Mensajes de relevo nuevos para ``id_dron`` (dirigidos a él o a todos)."""


class PizarronCompartido:
    """Estructura central donde se escribe y se lee la coordinación.

    Contiene una única :class:`TablaReclamos` (quién vigila qué y cuándo se
    vigiló cada sector) y un tablón de anuncios para los mensajes de relevo.

    ``disponible`` permite al Integrante 5 simular la caída del pizarrón: si es
    ``False``, las escrituras se descartan y la información se queda congelada.
    Es el punto débil natural de un esquema centralizado.
    """

    def __init__(self) -> None:
        self.tabla: TablaReclamos = TablaReclamos()
        self.anuncios: list[Mensaje] = []
        self.disponible: bool = True
        self.escrituras_rechazadas: int = 0

    def escribir(self, mensaje: Mensaje, paso_llegada: int | None = None) -> bool:
        """Aplica un mensaje que llegó por el canal. ``False`` si estaba caído."""
        if not self.disponible:
            self.escrituras_rechazadas += 1
            return False
        if mensaje.tipo in TIPOS_ASIGNACION:
            self.tabla.aplicar(mensaje, paso_llegada)
        else:
            self.anuncios.append(mensaje)
        return True


class CoordinadorPizarron(CoordinadorBase):
    """Mecanismo 1: pizarrón compartido (comunicación indirecta y centralizada).

    - **Escribir** cuesta UN mensaje por dron (al pizarrón), y viaja por el canal
      con su retraso y su pérdida.
    - **Leer** es consultar la tabla central: todos ven la misma información.
      Si un mensaje se pierde, nadie se entera; si llega, se enteran todos a la
      vez. Esto hace que la información sea *consistente* entre drones.
    - El propio pizarrón borra los reclamos caducos (detección de fallas).
    """

    mecanismo = "pizarron"

    def __init__(self, sectores: Sequence[Sector], canal: CanalComunicacion | None = None,
                 periodo_informe: int = 5, timeout_informe: int = 15) -> None:
        self.pizarron: PizarronCompartido = PizarronCompartido()
        self._cursor_anuncios: dict[int, int] = {}
        super().__init__(sectores, canal, periodo_informe, timeout_informe)

    def _al_registrar(self, id_dron: int) -> None:
        self._cursor_anuncios[id_dron] = 0

    def _vista(self, id_dron: int) -> TablaReclamos:
        return self.pizarron.tabla

    def _publicar(self, mensaje: Mensaje) -> None:
        self.canal.enviar(mensaje, [ID_PIZARRON])

    def _procesar(self, entrega: Entrega) -> None:
        self.pizarron.escribir(entrega.mensaje, entrega.paso_entrega)

    def _expirar(self, paso: int) -> int:
        if not self.pizarron.disponible:
            return 0  # pizarrón caído: nadie mantiene la tabla
        return len(self.pizarron.tabla.expirar(paso, self.timeout_informe))

    def recibir(self, id_dron: int) -> list[Mensaje]:
        self.registrar_dron(id_dron)
        inicio = self._cursor_anuncios[id_dron]
        nuevos = self.pizarron.anuncios[inicio:]
        self._cursor_anuncios[id_dron] = len(self.pizarron.anuncios)
        return [m for m in nuevos
                if m.emisor != id_dron and m.receptor in (None, id_dron)]

    def metricas(self) -> dict[str, float | int | str]:
        datos = super().metricas()
        datos["escrituras_rechazadas"] = self.pizarron.escrituras_rechazadas
        return datos


class CoordinadorMensajeria(CoordinadorBase):
    """Mecanismo 2: mensajería directa (comunicación distribuida dron a dron).

    - Cada dron tiene su **buzón** (mensajes de relevo) y su propia
      :class:`TablaReclamos` (lo que él sabe de los demás).
    - Un mensaje con ``receptor=None`` se difunde: se envía una copia a cada uno
      de los otros ``N - 1`` drones, y cada copia puede perderse por separado.
      Por eso cuesta más mensajes y, con pérdida, cada dron puede tener una
      visión diferente (información *inconsistente*).
    - No hay un componente central que pueda caerse.
    """

    mecanismo = "mensajeria_directa"

    def __init__(self, sectores: Sequence[Sector], canal: CanalComunicacion | None = None,
                 periodo_informe: int = 5, timeout_informe: int = 15) -> None:
        self._tablas: dict[int, TablaReclamos] = {}
        self._buzones: dict[int, list[Mensaje]] = {}
        super().__init__(sectores, canal, periodo_informe, timeout_informe)

    def _al_registrar(self, id_dron: int) -> None:
        self._tablas[id_dron] = TablaReclamos()
        self._buzones[id_dron] = []

    def _vista(self, id_dron: int) -> TablaReclamos:
        return self._tablas[id_dron]

    def _publicar(self, mensaje: Mensaje) -> None:
        if mensaje.receptor is not None:
            destinos = [mensaje.receptor]
        else:
            destinos = [i for i in self.ids_drones if i != mensaje.emisor]
        self.canal.enviar(mensaje, destinos)

    def _procesar(self, entrega: Entrega) -> None:
        self.registrar_dron(entrega.destinatario)
        if entrega.mensaje.tipo in TIPOS_ASIGNACION:
            self._tablas[entrega.destinatario].aplicar(entrega.mensaje, entrega.paso_entrega)
        else:
            self._buzones[entrega.destinatario].append(entrega.mensaje)

    def _expirar(self, paso: int) -> int:
        return sum(len(t.expirar(paso, self.timeout_informe)) for t in self._tablas.values())

    def recibir(self, id_dron: int) -> list[Mensaje]:
        self.registrar_dron(id_dron)
        mensajes, self._buzones[id_dron] = self._buzones[id_dron], []
        return mensajes


MECANISMOS: dict[str, type[CoordinadorBase]] = {
    CoordinadorPizarron.mecanismo: CoordinadorPizarron,
    CoordinadorMensajeria.mecanismo: CoordinadorMensajeria,
}


def crear_coordinador(
    mecanismo: str,
    sectores: Sequence[Sector],
    canal: CanalComunicacion | None = None,
    periodo_informe: int = 5,
    timeout_informe: int = 15,
) -> CoordinadorBase:
    """Fábrica: ``"pizarron"`` o ``"mensajeria_directa"``."""
    clave = mecanismo.strip().lower()
    if clave not in MECANISMOS:
        raise ValueError(
            f"Mecanismo desconocido: {mecanismo!r}. Valores: {sorted(MECANISMOS)}"
        )
    return MECANISMOS[clave](sectores, canal, periodo_informe, timeout_informe)
