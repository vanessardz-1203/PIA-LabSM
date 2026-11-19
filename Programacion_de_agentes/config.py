"""
Parámetros de simulación propios de la Etapa 2 (Programación de agentes).

Reutiliza los parámetros del entorno definidos en ``Construccion_de_entorno/config.py``
y centraliza únicamente las variables propias de los agentes y la comparativa
entre las arquitecturas reactiva y basada en modelos.
"""

# ----- Estado físico y sensorial de los agentes (Integrante 2) -----
BATERIA_INICIAL = 100.0            # porcentaje de batería inicial de cada dron
BATERIA_MAXIMA = 100.0             # capacidad máxima de batería
CONSUMO_BATERIA_PASO = 0.5         # consumo energético por paso operativo
RADIO_OBSERVACION_AGENTE = 5       # radio de observación estándar para comparar arquitecturas

# ----- Parámetros de decisión por arquitectura -----
PROB_EXPLORACION_REACTIVA = 0.25   # probabilidad de exploración aleatoria en estímulos locales
PESO_SECTOR_PRIORITARIO = 2.0      # ponderación de zonas prioritarias en el modelo interno

# ----- Experimento comparativo de arquitecturas (Etapa 2) -----
PASOS_EXPERIMENTO_AGENTES = 100    # horizonte temporal de cada simulación
DRONES_EXPERIMENTO_AGENTES = [1, 2, 4, 6]
REPLICAS_AGENTES = 15              # réplicas con posiciones iniciales equivalentes
SEMILLA_EXPERIMENTO_AGENTES = 2000
