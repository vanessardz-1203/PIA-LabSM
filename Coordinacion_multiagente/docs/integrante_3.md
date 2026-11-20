# Integrante 3 — Comunicación y coordinación (Práctica 2)

> Explicación detallada (conceptos, diagramas, fragmentos de código y preguntas de defensa):
> [`integrante_3_explicacion.pdf`](integrante_3_explicacion.pdf).

## 1. Qué hace este módulo

Permite que los drones **se repartan los sectores sin duplicarse**, compartan **qué sector vigila cada uno**, **detecten a un compañero caído** y **transporten los mensajes de relevo** del Integrante 4. Se implementan dos mecanismos intercambiables con la **misma API**, para compararlos con el mismo experimento:

| Mecanismo | Idea | Costo por difusión | Información |
|---|---|---|---|
| **Pizarrón compartido** (`CoordinadorPizarron`) | Una tabla central; los drones escriben en ella y la leen | 1 mensaje | Igual para todos (consistente) |
| **Mensajería directa** (`CoordinadorMensajeria`) | Cada dron tiene su buzón y su propia tabla | N − 1 mensajes | Cada dron puede saber cosas distintas |

El módulo **no modifica** a los drones de la Etapa 2: solo lee `id`, `posicion`, `estado_operativo` y `esta_operativo`.

## 2. Archivos

| Archivo | Contenido |
|---|---|
| `simulacion/coordinacion.py` | `TipoMensaje`, `Mensaje`, `CanalComunicacion`, `TablaReclamos`, `elegir_sector`, `evaluar_asignacion`, `CoordinadorBase`, `PizarronCompartido`, `CoordinadorPizarron`, `CoordinadorMensajeria`, `crear_coordinador` |
| `simulacion/dron_coordinado.py` | Adaptador **temporal**: subclase de `DronBasadoEnModelos` con `sector_asignado` (para el experimento) |
| `config.py` | Parámetros del protocolo y del experimento (semillas fijas) |
| `tests/test_coordinacion.py` | 44 pruebas con pytest |
| `experimentos/experimento_coordinacion.py` | Experimento pizarrón vs. mensajería |
| `experimentos/graficas.py` | Gráficas del experimento |
| `resultados/` | `comparacion_coordinacion.csv` (resumen), `replicas_coordinacion.csv` (crudo), `graficas/*.png` |
| `docs/generar_pdf.py` | Genera el PDF explicativo (requiere `reportlab`, que **no** está en `requirements.txt`) |

## 3. Protocolo

### 3.1 Tipos de mensaje (`TipoMensaje`)

| Tipo | Quién lo envía | Para qué |
|---|---|---|
| `reclamar_sector` | Dron que empieza a vigilar un sector | Anunciar "este sector es mío desde el paso t" |
| `liberar_sector` | Dron que va a recargar / reserva / relevado | Dejar el sector libre sin esperar el timeout |
| `informe_sector` *(agregado)* | Cada dron, cada `PERIODO_INFORME` pasos | Compartir qué sector vigila y si está dentro (**información de sectores vigilados**) y servir de **latido**: si deja de llegar, el dron se da por caído |
| `solicitar_relevo` | Dron que necesita relevo (decisión del Int. 4) | Pedir reemplazo a un candidato o a todos |
| `confirmar_relevo` | Sustituto | Aceptar el reemplazo |
| `rechazar_relevo` *(agregado)* | Candidato que no puede | Que quien pidió el relevo no espere para siempre (caso "no hay sustituto") |

`Mensaje(emisor, receptor, tipo, contenido, paso_envio)` es **inmutable** (`frozen=True`; `contenido` es de solo lectura). `receptor=None` significa difusión.

### 3.2 Ciclo por paso (`coordinador.paso(t, drones)`)

1. Entregar los mensajes cuyo retraso ya se cumplió.
2. Borrar reclamos de drones de los que no se sabe nada desde hace más de `TIMEOUT_INFORME` pasos (contados desde la **llegada** del último mensaje).
3. Para cada dron:
   * **INACTIVO**: silencio (un dron caído no puede avisar; se detecta por timeout).
   * **Operativo**: aplica `elegir_sector` con su información. Si cambia de sector, envía `reclamar_sector`; si no, cada `PERIODO_INFORME` pasos envía `informe_sector`.
   * **EN_RECARGA / RESERVA / EN_RELEVO** sin asignación fija: envía `liberar_sector` una vez.
4. Entregar otra vez (con `retraso=0` todo llega en el mismo paso).

Las decisiones del paso 3 son **simultáneas**: por eso al inicio dos drones pueden elegir el mismo sector (conflicto), que se resuelve en cuanto se enteran el uno del otro.

### 3.3 Regla de asignación (`elegir_sector`)

* Cada sector se puntúa con `((ocupantes + 1) / peso, ocupantes)`; menor es mejor. Con 4 sectores (prioritarios 0 y 3, peso 2): con 4 drones queda **1 por sector**; con 6 drones, **2 en cada prioritario y 1 en cada normal**.
* **Conflictos**: en el sector actual solo cuentan los drones con más **precedencia** = (fijo primero, quien llegó antes, id menor). El de mayor precedencia se queda y el otro busca un sector mejor. Todos calculan lo mismo con la misma información, sin negociar.
* **Histéresis**: solo se cambia de sector si otro es *estrictamente* mejor (evita oscilaciones).
* **Empates**: el sector más cercano (al centroide) y luego el id menor (determinismo).
* **Asignación fija** (`fijar_sector`): no se reevalúa y tiene la máxima precedencia (para relevos).

### 3.4 Canal (`CanalComunicacion`)

* `retraso` fijo (+ `retraso_variable` opcional) en pasos; `prob_perdida` por **copia** con `semilla`.
* Métricas: `enviados`, `entregados`, `perdidos`, `pendientes`, `retraso_medio`, `tasa_perdida`, `enviados_por_tipo`.
* Puntos de inyección para el Integrante 5: los atributos `retraso`, `prob_perdida` y `retraso_variable` se pueden cambiar en cualquier paso; `hook_perdida(mensaje, destinatario) -> bool` permite pérdidas dirigidas (aislar un dron); `pizarron.disponible = False` simula la caída del pizarrón.

## 4. Decisiones de diseño (el porqué)

1. **Misma regla y mismo canal en ambos mecanismos.** Solo cambia por dónde viaja la información (tabla central vs. tablas por dron). Así la comparación mide el *mecanismo*, no una diferencia de algoritmo.
2. **`TablaReclamos` separada.** La usa el pizarrón (una) y la mensajería (una por dron): menos código duplicado y menos lugares para errores.
3. **Informe periódico = latido.** Un solo mensaje sirve para compartir lo vigilado y para detectar fallas. Un dron INACTIVO no puede avisar; la única forma de enterarse es notar su silencio.
4. **Timeout de 3 periodos (15 pasos).** Una falsa alarma exige perder 3 informes seguidos (p³ = 2.7 % con p = 0.3); a cambio, una falla real tarda ~15 pasos + retraso en detectarse.
5. **Timeout medido desde la llegada** *(corrección hecha durante el experimento)*. La primera versión medía desde el envío: con retraso 10 el margen real quedaba en 5 pasos y **perder un solo informe** producía una falsa alarma, con decenas de cambios de sector por réplica (72 con 6 drones, retraso 10 y pérdida 30 %). Medir desde la llegada lo bajó a ~11–14. Hay una prueba de regresión (`test_retraso_alto_y_un_informe_perdido_no_es_falsa_alarma`).
6. **Mensajes viejos se ignoran.** Si llegan desordenados, un `reclamar` viejo no pisa un `liberar` nuevo.
7. **Un reclamo nuevo reemplaza al anterior.** Perder un `liberar` al cambiar de sector no deja "basura".
8. **Mensajes inmutables.** En la difusión la misma instancia llega a varios buzones; nadie debe poder alterarla.
9. **Relevos: solo transporte.** Cuándo hace falta y quién es el sustituto lo decide el Integrante 4. Aquí solo se entregan los mensajes y se ofrece `fijar_sector` para concretar el cambio.
10. **Sin modificar a los drones.** El coordinador usa un `Protocol` (`DronCoordinable`); `DronBase` ya lo cumple. Para el experimento se usa una subclase propia (`DronCoordinado`) que, sin sector, se comporta igual que el original (hay una prueba que lo verifica).

## 5. API pública (para integrar)

```python
from Coordinacion_multiagente.simulacion.coordinacion import CanalComunicacion, crear_coordinador

canal = CanalComunicacion(retraso=2, prob_perdida=0.1, semilla=7)
coord = crear_coordinador("pizarron", entorno.sectores, canal,
                          periodo_informe=5, timeout_informe=15)   # o "mensajeria_directa"

for paso in range(1, pasos + 1):
    coord.paso(paso, drones)                     # 1) entregar, detectar caídos y (re)asignar
    for dron in drones:
        dron.sector_asignado = coord.asignacion_de(dron.id)   # 2) requiere el hook del Int. 2
        dron.ejecutar_paso(entorno, paso)        # 3) moverse

# Consultas
coord.asignaciones()            # {id_dron: sector}
coord.sectores_libres(id_dron)  # según lo que sabe ese dron
coord.ultima_vigilancia(id_dron, sector)
coord.metricas()                # cambios_sector, expiraciones + métricas del canal

# Relevos (los llama el módulo del Integrante 4)
coord.solicitar_relevo(emisor, sector, paso, receptor=None, datos={"bateria": 18})
coord.confirmar_relevo(emisor=sustituto, receptor=saliente, sector=s, paso=t)
coord.rechazar_relevo(emisor=candidato, receptor=saliente, sector=s, paso=t, motivo="bateria")
coord.recibir(id_dron)          # mensajes de relevo nuevos para ese dron
coord.fijar_sector(sustituto, sector, paso)   # asignación fija con máxima precedencia
coord.soltar_fijo(id_dron); coord.liberar_sector(id_dron, paso)
```

## 6. Pruebas

```bash
python -m pytest Coordinacion_multiagente/tests -v      # 44 passed
```

Cubren: mensaje (campos, inmutabilidad, validación); canal (retraso fijo y variable, pérdida reproducible con semilla, métricas que cuadran, extremos, `hook_perdida`); tabla (reclamar/cambiar/liberar, mensajes desordenados, información de vigilancia, expiración desde la llegada); regla de asignación (prioritarios, reparto por peso, conflictos por precedencia, histéresis, fijo); evaluación; pizarrón (retraso, visión compartida, caída); mensajería (N − 1 copias, visiones distintas con pérdida); convergencia sin duplicados con conflicto inicial, con más drones que sectores y con pérdida; reasignación cuando un dron queda INACTIVO; liberación al ir a recargar; flujo de relevo completo y `fijar_sector`; integración con `crear_dron` y el mapa real **sin modificarlos**; el adaptador.

## 7. Experimento: pizarrón vs. mensajería directa

### Método

* Mapa oficial (`generar_mapa_industrial` con la config del Integrante 1): 40×30, 4 sectores, prioritarios 0 y 3 (peso 2).
* Factores: mecanismo × drones {3, 4, 6, 8} × retraso {0, 2, 5, 10} × pérdida {0, 10 %, 30 %}; **10 réplicas** por configuración, 150 pasos (1000 simulaciones).
* En la réplica *r* ambos mecanismos usan **las mismas posiciones iniciales, las mismas semillas de los drones y la misma semilla del canal**.
* En el paso 75 cae (INACTIVO) el dron de menor id que vigila un sector prioritario.
* Línea base `sin_coordinacion`: los mismos drones sin coordinador (= dron basado en modelos original).
* Métricas: **redundancia evitable** (drones de más en un sector compartido mientras otro está vacío), **pasos hasta la primera asignación válida**, **recuperación tras la falla**, % de pasos con asignación válida, cobertura instantánea, acumulada y redundante (celdas vistas por 2 o más drones), cambios de sector, expiraciones, **mensajes por paso** y retraso medido.

Reproducir (≈5 min con 8 núcleos):

```bash
python -m Coordinacion_multiagente.experimentos.experimento_coordinacion            # en paralelo
python -m Coordinacion_multiagente.experimentos.experimento_coordinacion --procesos 1
```

### Resultados clave

**1. Coordinar (con cualquiera de los dos) mejora la vigilancia frente a no coordinar** (retraso 0, sin pérdida):

| Drones | Cob. instantánea sin coord. → con coord. | Cob. redundante sin → con | Cob. acumulada sin → con |
|---|---|---|---|
| 3 | 12.51 % → 14.13 % | 0.85 % → 0.10 % | 85.9 % → 85.3 % |
| 4 | 17.00 % → 19.00 % | 1.70 % → 0.30 % | 88.6 % → 100 % |
| 6 | 24.80 % → 27.75 % | 4.25 % → 3.12 % | 92.9 % → 100 % |
| 8 | 30.95 % → 34.61 % | 7.78 % → 6.93 % | 96.3 % → 100 % |

Aproximadamente **+12 % de cobertura instantánea relativa** y mucha menos vigilancia duplicada. Con 3 drones la cobertura acumulada no mejora: el sector normal que queda sin dron casi no se visita (la regla manda a los drones a los prioritarios).

**2. Con canal sin pérdida, ambos mecanismos producen exactamente las mismas asignaciones.** Es lo esperado: con la misma regla y el mismo retraso, todos los drones reciben la misma información en el mismo paso. Por eso, en las gráficas, la línea del pizarrón con 0 % de pérdida queda tapada por la de mensajería.

**3. La diferencia clara es el costo: la mensajería directa envía N − 1 veces más mensajes.**

| Drones | Mensajes/paso pizarrón | Mensajes/paso mensajería | Razón |
|---|---|---|---|
| 3 | 0.51 | 1.02 | 2× |
| 4 | 0.73 | 2.18 | 3× |
| 6 | 1.15 | 5.74 | 5× |
| 8 | 1.57 | 11.03 | 7× |

El pizarrón crece de forma lineal con N; la mensajería, de forma cuadrática.

**4. El retraso es el factor que más afecta a la coordinación** (4 drones, sin pérdida, de retraso 0 a 10): redundancia evitable 0.03 → 0.28; pasos hasta asignación válida 2.8 → 19; recuperación tras falla 13 → 32 pasos; % de pasos con asignación válida 90 % → 67 %. Aun así, la cobertura instantánea casi no cambia (19.0 % → 18.9 %).

**5. Con pérdida, ningún mecanismo domina.** Comparando réplica contra réplica (mismas semillas), la mayoría de las diferencias son menores que su error estándar. Las que sí son claras (|diferencia| > 2 errores estándar) van en direcciones distintas:

* **4 drones, retraso 5–10, pérdida 30 %: la mensajería se recupera ~10 pasos antes de la falla** (14.3 vs. 24.0 y 24.0 vs. 34.0 pasos). Motivo: hay N − 1 observadores independientes y basta con que **uno** detecte la falla para que se mueva a cubrir el sector; en el pizarrón hay un solo observador.
* **6 drones, retraso 5–10, pérdida 30 %: el pizarrón mantiene más tiempo una asignación válida** (94.1 % vs. 89.7 % y 91.1 % vs. 84.6 %). Motivo: con pérdida, en la mensajería cada dron tiene una visión distinta y hay más cambios de sector (16.0 vs. 11.2 con retraso 5).
* Las mismas visiones locales que aceleran la detección generan más expiraciones en total (8 drones, pérdida 30 %: 36 vs. 4.7). La comparación justa es por observador: unas 4–5 por tabla en ambos casos, así que no hay más falsas alarmas por dron, sino más tablas que pueden tenerlas.

Con 10 réplicas y 32 comparaciones por métrica cabe esperar ~1–2 diferencias "significativas" por azar; por eso no se afirma una ventaja general de ninguno en calidad de coordinación.

### Respuesta a la pregunta secundaria 2

En este modelo, **ambos mecanismos reducen igual las asignaciones redundantes cuando la red es confiable**. Con pérdida, las diferencias son pequeñas y dependen del escenario. **El pizarrón logra lo mismo con N − 1 veces menos mensajes**, por lo que es la opción más eficiente; su punto débil, que este experimento **no** mide, es ser un punto único de falla (`pizarron.disponible = False` existe para que el Integrante 5 lo evalúe). La mensajería directa es más cara pero no tiene componente central y detecta antes las fallas cuando hay pocos drones y mucha pérdida.

Gráficas: `resultados/graficas/coordinacion_vs_retraso_{3,4,6,8}_drones.png` y `resultados/graficas/escalabilidad_mensajes.png`.

## 8. Limitaciones

* Los drones de la Etapa 2 aún no aceptan un sector; el experimento usa el adaptador `DronCoordinado` (subclase en esta carpeta).
* El adaptador planea rutas con el plano completo de la instalación (simplificación).
* La batería no influye (150 pasos × 0.5 = 75 % de consumo; nadie se descarga). Los relevos solo se probaron con pruebas unitarias, porque la lógica es del Integrante 4.
* Retraso fijo en el experimento (el canal soporta variable, pero no se varió).
* No se simuló la caída del pizarrón ni particiones de red en el experimento (hay ganchos para el Integrante 5).
* Solo 4 sectores; con más sectores las diferencias de costo serían mayores.
* Las decisiones son simultáneas y la información de un paso se aplica en ese mismo paso (`retraso=0`): es un modelo discreto, no una red real.

## 9. Integración: lo que hay que pedir a cada integrante

* **Integrante 1**: `Construccion_de_entorno/tests/test_entorno.py` importa `from simulacion...` en vez de `from Construccion_de_entorno.simulacion...`. Falla con `python -m pytest` desde la raíz (`ModuleNotFoundError: No module named 'simulacion'`). Solo funciona en Docker porque el `Dockerfile` agrega `/app/Construccion_de_entorno` al `PYTHONPATH`. No se corrigió.
* **Integrante 2**: agregar a `DronBase` un atributo `sector_asignado: int | None = None` y hacer que `decidir()`, en la estrategia basada en modelos, restrinja sus objetivos a ese sector cuando no sea `None`, como hace `DronCoordinado._planear`. Con eso, `dron_coordinado.py` sobra.
* **Integrante 4**: usar `solicitar_relevo`, `confirmar_relevo`, `rechazar_relevo` y `recibir` para el diálogo, y `fijar_sector(sustituto, sector, paso)` al confirmar. Al poner al saliente en `EN_RECARGA` el coordinador libera su sector solo. Ojo: `EN_RELEVO` no es "operativo" en `DronBase`, así que el sustituto conserva el sector solo si se fijó con `fijar_sector`.
* **Integrante 5**: en el motor, llamar `coord.paso(t, drones)` antes de mover a los drones. Inyectar fallas con `estado_operativo = INACTIVO`, y retraso o pérdida con `canal.retraso`, `canal.prob_perdida` y `canal.hook_perdida`. La caída del pizarrón se simula con `coord.pizarron.disponible`.

### Líneas a agregar al integrar (no se modificaron)

`Dockerfile`, después de `COPY Programacion_de_agentes /app/Programacion_de_agentes`:

```dockerfile
COPY Coordinacion_multiagente /app/Coordinacion_multiagente
```

`.github/workflows/ci.yml`, paso "Verificar sintaxis de todas las etapas":

```yaml
run: docker run --rm pia-drones:ci python -m compileall -q Construccion_de_entorno Programacion_de_agentes Coordinacion_multiagente
```

(Opcional) en `docs/guia_desarrollo.md`, sección 3.3, el mismo cambio al `compileall`. También convendría un `.gitignore` con `__pycache__/` y `.pytest_cache/`.

## Conclusión individual 

En esta parte del proyecto me tocó que los drones se comunicaran y se pusieran de acuerdo sobre qué sector vigilar cada uno, y lo que más me llevo es que no basta con que se manden mensajes: también necesitan una regla clara para decidir, porque si no terminan varios en el mismo lugar y otras zonas se quedan sin vigilancia. Comparé dos formas de comunicarse, el pizarrón compartido y la mensajería directa, y vi que si la red funciona bien las dos dan prácticamente lo mismo; la diferencia aparece cuando se pierden mensajes o tardan en llegar, y ahí el retraso fue lo que más complicó que los drones se reacomodaran cuando uno fallaba. En general, coordinarlos sí mejoró la vigilancia y evitó que anduvieran repitiendo recorridos, y el pizarrón me pareció más eficiente porque necesita muchos menos mensajes, aunque la mensajería no depende de un punto central. Quedaron cosas pendientes, como probar qué pasa si el pizarrón se cae o integrar la batería y los relevos con el resto del sistema, pero me llevo que una buena coordinación depende tanto de las reglas como de qué tan confiable sea la comunicación.
