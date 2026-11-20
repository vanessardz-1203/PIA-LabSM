"""
Parámetros de simulación propios de la Etapa 3 (Comunicación y coordinación).

Reutiliza los parámetros del entorno (``Construccion_de_entorno/config.py``) y de
los agentes (``Programacion_de_agentes/config.py``) y centraliza únicamente las
variables de comunicación y del experimento pizarrón vs. mensajería directa.
"""

# ----- Protocolo de coordinación (Integrante 3) -----
PERIODO_INFORME = 5        # cada cuántos pasos un dron reenvía su INFORME_SECTOR (latido)
TIMEOUT_INFORME = 15       # pasos sin noticias para dar a un dron por caído (3 informes)
#   ¿Por qué 3 periodos? Con 1 solo periodo, perder UN informe ya provocaría una
#   falsa alarma; con 3, la falsa alarma exige perder 3 seguidos (p^3: 2.7 % con
#   p = 0.3). A cambio, detectar una falla real tarda hasta ~15 pasos + retraso.
#   El timeout se cuenta desde que LLEGA el último mensaje (no desde que se envió),
#   para que el retraso del canal no reduzca este margen.

# ----- Canal por defecto -----
RETRASO_DEFECTO = 0        # pasos
PROB_PERDIDA_DEFECTO = 0.0

# ----- Experimento: pizarrón compartido vs. mensajería directa -----
MECANISMOS_EXPERIMENTO = ("pizarron", "mensajeria_directa")
INCLUIR_LINEA_BASE = True              # agrega "sin_coordinacion" como referencia
DRONES_EXPERIMENTO_COORD = [3, 4, 6, 8]  # menos, igual y más drones que sectores (4)
RETRASOS_EXPERIMENTO = [0, 2, 5, 10]     # pasos de retraso del canal
PERDIDAS_EXPERIMENTO = [0.0, 0.1, 0.3]   # probabilidad de perder cada copia
PASOS_EXPERIMENTO_COORD = 150
PASO_FALLA = 75            # en este paso cae (INACTIVO) un dron que vigila un sector prioritario
REPLICAS_COORD = 10        # réplicas por configuración
SEMILLA_EXPERIMENTO_COORD = 3000   # posiciones iniciales y semillas de drones
SEMILLA_CANAL = 3500               # pérdida de mensajes (misma en ambos mecanismos)
