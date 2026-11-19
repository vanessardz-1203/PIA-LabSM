# Documentación · Integrante 2 — Programación de Agentes y Patrullaje (Etapa 2 · Práctica 1)

## 1. Objetivo y ubicación

Esta carpeta (`Programacion_de_agentes/`) agrupa de forma independiente todos los artefactos correspondientes al **Punto 2 del plan de desarrollo** (*Programar los agentes*), respetando la convención de una carpeta por etapa iniciada con `Construccion_de_entorno/`:

- Modela para cada dron su **posición**, **batería**, **radio de observación**, **estado operativo** y **capacidad de toma de decisiones**.
- Reutiliza el entorno y cálculo de visibilidad de `Construccion_de_entorno` sin duplicar código.
- Compara las dos arquitecturas de la Práctica 1: **Reactiva** (`DronReactivo`) y **Basada en Modelos** (`DronBasadoEnModelos`).

> **Límite de alcance:** En esta etapa los drones operan de forma individual y autónoma, sin coordinación inter-dron (Etapa 3), sin relevos autónomos (Etapa 4) y sin inyección de fallas/obstáculos dinámicos (Etapa 5).

---

## 2. Arquitectura del módulo y documentación de componentes

### 2.1 `Programacion_de_agentes/simulacion/agentes.py`

| Símbolo | Tipo | Responsabilidad |
|---|---|---|
| `EstadoOperativo` | `Enum(str)` | Estados operativos del dron: `ACTIVO`, `VIGILANDO`, `EN_RECARGA`, `RESERVA`, `EN_RELEVO`, `INACTIVO`. |
| `Percepcion` | `@dataclass(frozen=True)` | Instantánea inmutable percibida en el paso `paso`: posición, `celdas_visibles`, `vecinos_transitables`, `tipos_visibles`, `celdas_prioritarias_visibles`, `vecinos_prioritarios`, `sector_actual`, `en_sector_prioritario`, `bateria`, `estado_operativo` y `dimensiones_entorno`. |
| `ModeloInterno` | `@dataclass` | Memoria espacial y temporal del agente basado en modelos: mapa incremental de celdas transitables, obstáculos adyacentes inferidos, estaciones de recarga, celdas prioritarias, `ultima_observacion[c]` y `visitas_posicion[c]`. Expone `actualizar()`, `antiguedad()`, `contar_vecinos_desconocidos()` y `celdas_frontera()`. |
| `DronBase` | `ABC` | Clase base con `id`, `posicion`, `bateria`, `bateria_max`, `consumo_por_paso`, `radio_observacion`, `estado_operativo`, historial y ciclo `percibir() -> decidir() -> actuar()` en `ejecutar_paso()`. |
| `DronReactivo` | Subclase de `DronBase` | Arquitectura estímulo-respuesta sin memoria ni mapa interno; delega `decidir()` a `elegir_movimiento_reactivo()`. |
| `DronBasadoEnModelos` | Subclase de `DronBase` | Arquitectura con `ModeloInterno` y objetivo persistente; actualiza su memoria en cada paso y delega `decidir()` a `elegir_movimiento_basado_en_modelos()`. |
| `crear_dron(...)` | Función fábrica | Instancia `"reactivo"` o `"basado_en_modelos"` validando parámetros. |

### 2.2 `Programacion_de_agentes/simulacion/patrullaje.py`

| Función | Propósito |
|---|---|
| `distancia_manhattan(a, b)` | Distancia Manhattan en cuadrícula 4-conectada. |
| `bfs_desde(origen, celdas_transitables)` | Búsqueda en anchura (BFS) en una sola pasada que devuelve `(distancias, padres)` rodeando edificios. |
| `reconstruir_camino(origen, destino, padres)` | Reconstruye el camino más corto `[origen, ..., destino]`. |
| `camino_mas_corto_bfs(origen, destino, celdas_transitables)` | Calcula la ruta más corta en 4 direcciones entre dos celdas. |
| `siguiente_paso_hacia(origen, destino, celdas_transitables, padres)` | Obtiene la celda adyacente inmediata para avanzar hacia el destino. |
| `elegir_movimiento_reactivo(percepcion, rng, prob_exploracion)` | Política estímulo-respuesta pura sobre la percepción actual. |
| `seleccionar_objetivo_modelo(posicion, modelo, distancias, peso_prioritario, ...)` | Selección en dos fases: **Fase A (Exploración de frontera)** y **Fase B (Vigilancia por antigüedad ponderada por prioridad)**. |
| `elegir_movimiento_basado_en_modelos(...)` | Mantiene persistencia del objetivo para evitar oscilaciones y navega paso a paso mediante BFS. |

---

## 3. Resultados experimentales (Reactivo vs. Basado en Modelos)

**Condiciones experimentales:** mapa `40 × 30` de `Construccion_de_entorno/config.py` (`SEMILLA_MAPA = 42`, 8 edificios, 4 recargas, sectores prioritarios `(0, 3)` con peso `2.0`), radio de observación `5` celdas con línea de vista (`USAR_LINEA_DE_VISTA = True`), `100` pasos por réplica, `15` réplicas con posiciones iniciales idénticas para ambas arquitecturas (`Programacion_de_agentes/config.py`).

| Arquitectura | Drones | Cob. Inst. Media (%) | Cob. Acumulada (%) | Cob. Prioritaria Acum. (%) | Tiempo sin Vigilancia (pasos) | Redundancia Media (%) | Eficiencia Patrullaje (%) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Reactivo | 1 | 5.98 | 16.93 ± 5.45 | 22.90 | 44.68 | 0.00 | 39.80 |
| **Basado en modelos** | 1 | 5.25 | **52.32 ± 7.37** | **65.92** | **38.31** | 0.00 | **93.14** |
| Reactivo | 2 | 11.99 | 33.76 ± 6.89 | 43.32 | 38.90 | 0.08 | 40.40 |
| **Basado en modelos** | 2 | 10.39 | **71.94 ± 11.52** | **85.77** | **30.34** | 0.30 | **93.33** |
| Reactivo | 4 | 22.09 | 54.24 ± 9.37 | 68.80 | 30.83 | 1.96 | 41.58 |
| **Basado en modelos** | 4 | 19.32 | **89.10 ± 6.82** | **98.36** | **21.18** | 1.91 | **93.73** |
| Reactivo | 6 | 29.46 | 64.94 ± 8.69 | 79.52 | 26.00 | 6.17 | 41.39 |
| **Basado en modelos** | 6 | 26.16 | **92.46 ± 5.52** | **99.71** | **17.31** | **4.92** | **93.58** |

Evidencia generada:
- Tabla CSV: `Programacion_de_agentes/resultados/comparacion_arquitecturas.csv`
- Gráfica comparativa: `Programacion_de_agentes/resultados/graficas/comparacion_arquitecturas.png`

### Análisis de hallazgos

1. **Exploración y cobertura acumulada:** Con 4 drones, la arquitectura basada en modelos cubre **89.10 %** del área transitable (**98.36 %** de los sectores prioritarios) frente a **54.24 %** (**68.80 %** prioritario) de la arquitectura reactiva. Con 6 drones alcanza **92.46 %** global y **99.71 %** en sectores prioritarios.
2. **Reducción del tiempo sin supervisión:** La memoria temporal y el enrutamiento BFS reducen el tiempo medio sin vigilancia en **31.3 %** con 4 drones (`30.83 -> 21.18` pasos) y **33.4 %** con 6 drones (`26.00 -> 17.31` pasos).
3. **Eficiencia de trayectoria:** Los agentes basados en modelos logran **~93.5 %** de posiciones únicas por trayectoria frente a **~40.8 %** en los reactivos.
4. **Compensación cobertura instantánea vs. total:** La cobertura instantánea media es ligeramente menor en el modelo (`26.16 %` vs. `29.46 %` con 6 drones) porque explora pasillos perimetrales y esquinas bloqueadas por edificios para eliminar puntos ciegos.

---

## 4. Reproducción en Docker

Ejecuta desde la **raíz del repositorio**:

```bash
# Construir imagen
docker build -t pia-drones:dev .

# Ejecutar pruebas unitarias de la Etapa 2
docker run --rm pia-drones:dev pytest Programacion_de_agentes/tests -v

# Reproducir experimento y guardar CSV + gráfica en Programacion_de_agentes/resultados/
docker run --rm \
  -v "$PWD/Programacion_de_agentes/resultados:/app/Programacion_de_agentes/resultados" \
  pia-drones:dev python -m Programacion_de_agentes.experimentos.experimento_agentes
```
