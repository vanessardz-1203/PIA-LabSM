"""
Parámetros globales de la simulación.

Centralizar los valores aquí permite cambiar el escenario sin tocar la lógica
de los módulos de entorno, cobertura, agentes o experimentos.
"""

# ----- Mapa industrial (Integrante 1) -----
ANCHO_MAPA = 40            # celdas en el eje x (se mantiene la cuadrícula existente)
ALTO_MAPA = 30             # celdas en el eje y
SEMILLA_MAPA = 42          # misma semilla -> mismo mapa (reproducibilidad)
NUM_EDIFICIOS = 8
ESTACIONES_RECARGA = 4
SECTORES_X = 2             # el mapa se divide en SECTORES_X x SECTORES_Y sectores
SECTORES_Y = 2
# Modificación Etapa 1: se agregan sectores prioritarios requeridos por el enunciado
SECTORES_PRIORITARIOS = (0, 3)  # IDs de sectores críticos (esquinas opuestas en 2x2)
PESO_SECTOR_PRIORITARIO = 2.0   # factor de prioridad para vigilancia y patrullaje

# ----- Observación de drones (Integrante 1) -----
USAR_LINEA_DE_VISTA = True  # si es False, los edificios no bloquean la visión

# ----- Experimento de cobertura (Integrante 1) -----
DRONES_EXPERIMENTO = [1, 2, 3, 4, 6, 8, 10]
RADIOS_EXPERIMENTO = [3, 5, 7]
REPLICAS = 30              # repeticiones con posiciones aleatorias distintas

