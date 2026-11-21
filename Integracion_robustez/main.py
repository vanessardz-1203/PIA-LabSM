"""Punto de entrada ilustrativo de la integración del Integrante 5.
Desde la raíz del repositorio: python -m Integracion_robustez.main
Punto de entrada para escenarios de simulación multiagente.
"""
import json
from Integracion_robustez import config
from Integracion_robustez.simulacion.motor import MotorSimulacion


def main():
    motor = MotorSimulacion(
        drones=config.NUM_DRONES,
        pasos=config.PASOS,
        semilla=config.SEMILLA,
        mecanismo=config.MECANISMO,
        arquitectura=config.ARQUITECTURA,
        retraso=config.RETRASO_MENSAJES,
        perdida=config.PROB_PERDIDA,
        radio=config.RADIO_OBSERVACION,
        bateria_inicial=config.BATERIA_INICIAL,
        consumo_por_paso=config.CONSUMO_POR_PASO,
        usar_relevos=config.USAR_RELEVOS,
    )
    print(json.dumps(motor.ejecutar(), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
