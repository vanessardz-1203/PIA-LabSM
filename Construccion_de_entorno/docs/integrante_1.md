# Documentación · Integrante 1 — Entorno y Cobertura (Etapa 1)

## 1. Descripción general

El módulo de la **Etapa 1** modela la instalación industrial como una cuadrícula discreta de `40 × 30` celdas (`ANCHO_MAPA × ALTO_MAPA`) y cuantifica la cobertura instantánea de vigilancia, los puntos ciegos, la redundancia y la cobertura de sectores prioritarios.

### Módulos y funciones principales

| Archivo | Componente | Propósito |
|---|---|---|
| `config.py` | Constantes globales | Centraliza dimensiones, semillas, cantidad de edificios, estaciones de recarga y sectores prioritarios. |
| `simulacion/entorno.py` | `Sector`, `Entorno`, `generar_mapa_industrial`, `dividir_en_sectores`, `es_conectado`, `mapa_ascii` | Representación del mapa industrial, generación reproducible de edificios con halo libre, estaciones de recarga, partición en sectores (normales y prioritarios) y verificación de conectividad (BFS). |
| `simulacion/cobertura.py` | `linea_bresenham`, `hay_linea_de_vista`, `celdas_visibles`, `ResultadoCobertura`, `calcular_cobertura`, `cobertura_por_sector`, `cobertura_prioritaria`, `colocar_drones_aleatorios` | Cálculo geométrico de visibilidad con oclusión por edificios (Bresenham) y métricas de cobertura global, por sector, prioritaria y redundante. |
| `tests/test_entorno.py` | Suite de pruebas unitarias | Valida dimensiones, obstáculos, recargas, conectividad, línea de vista, cobertura, redundancia y sectores prioritarios. |

---

## 2. Revisión y cambios realizados sobre la Etapa 1

Al auditar la implementación original contra el enunciado del proyecto (Etapa 1), las 21 pruebas iniciales pasaron correctamente y se conservaron las dimensiones existentes (`40 × 30` celdas, 8 edificios y 4 estaciones de recarga), pero se detectaron y corrigieron los siguientes puntos:

1. **Soporte de sectores prioritarios (`simulacion/entorno.py` y `config.py`):**
   - *Por qué:* El enunciado de la Etapa 1 exige distinguir sectores prioritarios dentro de la instalación industrial, y `Sector` anteriormente solo almacenaba `id` y `celdas`.
   - *Cambio:* Se agregaron los atributos `prioritario: bool = False` y `peso: float = 1.0` a `Sector`, los parámetros `sectores_prioritarios` y `peso_prioritario` en `dividir_en_sectores` y `generar_mapa_industrial`, las consultas `Entorno.sectores_prioritarios()`, `Entorno.celdas_prioritarias()` y `Entorno.es_celda_prioritaria(c)`, la opción `mostrar_prioritarios=True` en `mapa_ascii`, y las constantes `SECTORES_PRIORITARIOS = (0, 3)` y `PESO_SECTOR_PRIORITARIO = 2.0` en `config.py`.
2. **Métrica de cobertura prioritaria y validación defensiva (`simulacion/cobertura.py`):**
   - *Por qué:* Se requiere medir la vigilancia sobre zonas prioritarias y evitar resultados inconsistentes si se consulta visibilidad desde una celda no transitable o con radio negativo.
   - *Cambio:* Se añadió `cobertura_prioritaria(entorno, resultado)` y una guarda al inicio de `celdas_visibles` que devuelve `set()` cuando `posicion` no es transitable o `radio < 0`.
3. **Limpieza del repositorio y ampliación de pruebas:**
   - *Por qué:* Existía un archivo vacío residual (`Construccion_de_entorno/simulacion/ms`) y faltaban pruebas unitarias para sectores prioritarios y casos borde de visibilidad.
   - *Cambio:* Se eliminó `simulacion/ms`, se actualizaron los parámetros en `experimentos/ejecutar_experimentos.py` y se añadieron 5 pruebas nuevas en `tests/test_entorno.py` (total: 26 pruebas).

---

## 3. Cómo reproducir pruebas y experimento de Etapa 1 (Docker)

```bash
# Construir imagen (desde la raíz del repositorio)
docker build -t pia-drones:dev .

# Ejecutar pruebas de Etapa 1
docker run --rm pia-drones:dev pytest Construccion_de_entorno/tests -v

# Ejecutar experimento de cobertura (guarda resultados en tu disco local)
docker run --rm \
  -v "$PWD/Construccion_de_entorno/resultados:/app/Construccion_de_entorno/resultados" \
  pia-drones:dev python -m Construccion_de_entorno.experimentos.ejecutar_experimentos
```
