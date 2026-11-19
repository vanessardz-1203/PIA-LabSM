# Guía de Desarrollo y Reproducción (Docker + CI/CD)

Esta guía permite a cualquier integrante del equipo levantar, probar y reproducir los experimentos de las **Etapas 1 y 2** sin instalar dependencias en su sistema operativo anfitrión, respetando la convención de **una carpeta independiente por cada etapa del plan de desarrollo**.

---

## 1. Requisitos previos

- **Git**
- **Docker** (o Podman compatible con CLI `docker`)

> No es necesario instalar Python, `pytest` ni `matplotlib` en la máquina local; todo se ejecuta dentro de la imagen definida en [`Dockerfile`](../Dockerfile).

---

## 2. Convención de carpetas del repositorio (una carpeta por etapa)

Cada punto del plan de desarrollo vive en su propia carpeta de paquete en la raíz del repositorio y reutiliza las etapas anteriores mediante importaciones explícitas (`from Construccion_de_entorno.simulacion...`, `from Programacion_de_agentes.simulacion...`):

```text
PIA-LabSM/
├── .github/workflows/ci.yml               # Pipeline de CI/CD (build + compileall + pytest)
├── Dockerfile                             # Imagen reproducible Python 3.12-slim (WORKDIR /app)
├── .dockerignore
├── requirements.txt                       # Dependencias exactas del contenedor
├── README.md                              # Especificación general y división de trabajo
├── docs/
│   └── guia_desarrollo.md                 # Esta guía para el siguiente desarrollador
│
├── Construccion_de_entorno/               # ETAPA 1 — Entorno y cobertura
│   ├── __init__.py
│   ├── config.py                          # Parámetros del mapa, recargas y sectores prioritarios
│   ├── simulacion/
│   │   ├── __init__.py
│   │   ├── entorno.py                     # Cuadrícula 40x30, edificios, recargas, sectores prioritarios
│   │   └── cobertura.py                   # Bresenham, visibilidad, cobertura, redundancia y prioritaria
│   ├── experimentos/
│   │   ├── __init__.py
│   │   ├── ejecutar_experimentos.py       # Experimento Etapa 1 (cobertura vs drones y radio)
│   │   └── graficas.py                    # Gráfica de Etapa 1
│   ├── tests/
│   │   ├── __init__.py
│   │   └── test_entorno.py                # 26 pruebas unitarias Etapa 1
│   ├── resultados/                        # CSV y PNG de Etapa 1
│   └── docs/
│       └── integrante_1.md                # Documentación y cambios de Etapa 1
│
└── Programacion_de_agentes/               # ETAPA 2 — Agentes y patrullaje (Práctica 1)
    ├── __init__.py
    ├── config.py                          # Parámetros de batería, radio y comparativa de arquitecturas
    ├── simulacion/
    │   ├── __init__.py
    │   ├── agentes.py                     # EstadoOperativo, Percepcion, ModeloInterno, DronReactivo, DronBasadoEnModelos
    │   └── patrullaje.py                  # Estrategia reactiva, BFS y patrullaje basado en modelos
    ├── experimentos/
    │   ├── __init__.py
    │   ├── experimento_agentes.py         # Experimento Etapa 2 (reactivo vs basado en modelos)
    │   └── graficas.py                    # Gráficas comparativas de Etapa 2
    ├── tests/
    │   ├── __init__.py
    │   └── test_agentes.py                # 12 pruebas unitarias Etapa 2
    ├── resultados/                        # CSV y PNG de Etapa 2
    └── docs/
        └── integrante_2.md                # Documentación, arquitecturas y resultados de Etapa 2
```

---

## 3. Reproducción paso a paso en Docker

Ejecuta todos los comandos desde la **raíz del repositorio** (`PIA-LabSM/`):

### 3.1 Construir la imagen Docker

```bash
docker build -t pia-drones:dev .
```

### 3.2 Ejecutar toda la suite de pruebas (`pytest`)

```bash
docker run --rm pia-drones:dev pytest -v
```

O ejecutar cada etapa de forma independiente:

```bash
# Etapa 1
docker run --rm pia-drones:dev pytest Construccion_de_entorno/tests -v

# Etapa 2
docker run --rm pia-drones:dev pytest Programacion_de_agentes/tests -v
```

### 3.3 Verificar compilación sintáctica de todas las etapas

```bash
docker run --rm pia-drones:dev python -m compileall -q Construccion_de_entorno Programacion_de_agentes
```

### 3.4 Reproducir el experimento de Etapa 1 (Cobertura vs. Drones y Radio)

```bash
docker run --rm \
  -v "$PWD/Construccion_de_entorno/resultados:/app/Construccion_de_entorno/resultados" \
  pia-drones:dev python -m Construccion_de_entorno.experimentos.ejecutar_experimentos
```

Genera:
- `Construccion_de_entorno/resultados/cobertura_drones_radio.csv`
- `Construccion_de_entorno/resultados/graficas/cobertura_vs_drones.png`

### 3.5 Reproducir el experimento de Etapa 2 (Reactivo vs. Basado en Modelos)

```bash
docker run --rm \
  -v "$PWD/Programacion_de_agentes/resultados:/app/Programacion_de_agentes/resultados" \
  pia-drones:dev python -m Programacion_de_agentes.experimentos.experimento_agentes
```

Genera:
- `Programacion_de_agentes/resultados/comparacion_arquitecturas.csv`
- `Programacion_de_agentes/resultados/graficas/comparacion_arquitecturas.png`

### 3.6 Desarrollo iterativo sin reconstruir la imagen en cada cambio

Mientras no cambie `requirements.txt`, puedes montar el repositorio directamente:

```bash
docker run --rm \
  -v "$PWD:/app" \
  pia-drones:dev pytest -v
```

---

## 4. Pipeline de CI/CD y guía para el siguiente desarrollador (Etapas 3, 4 y 5)

El flujo [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) se ejecuta automáticamente en cada `push` y `pull_request` hacia `main`:

1. Construye la imagen `pia-drones:ci` desde el `Dockerfile`.
2. Valida sintaxis con `python -m compileall -q Construccion_de_entorno Programacion_de_agentes`.
3. Ejecuta toda la suite `pytest -v`.

**Checklist al crear la siguiente etapa (p. ej. `Coordinacion_multiagente/`, `Sistema_de_relevos/`, `Robustez_e_integracion/`):**
1. Crea tu carpeta independiente con `__init__.py`, `config.py`, `simulacion/`, `experimentos/`, `tests/`, `resultados/` y `docs/`.
2. Importa las etapas previas por nombre de paquete completo (p. ej. `from Construccion_de_entorno.simulacion.entorno import Entorno` y `from Programacion_de_agentes.simulacion.agentes import DronBase, EstadoOperativo`).
3. Agrega la línea `COPY <Tu_carpeta> /app/<Tu_carpeta>` en [`Dockerfile`](../Dockerfile) y añádela al paso `compileall` en [`.github/workflows/ci.yml`](../.github/workflows/ci.yml); `pytest -v` descubrirá tus pruebas automáticamente.
4. Si necesitas nuevas dependencias Python, añádelas a `requirements.txt` y reconstruye la imagen Docker.
