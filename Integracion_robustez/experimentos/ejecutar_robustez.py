"""Escenarios emparejados. Ejecutar desde raíz con python -m Integracion_robustez.experimentos.ejecutar_robustez"""
import csv
from pathlib import Path
from Integracion_robustez.simulacion.motor import MotorSimulacion
from Integracion_robustez.simulacion.robustez import Evento


def ejecutar(destino=None):
    archivo = Path(destino or Path(__file__).resolve().parents[1] / 'resultados' / 'comparacion_robustez.csv')
    archivo.parent.mkdir(parents=True, exist_ok=True)
    filas = []
    for semilla in (42, 43, 44, 45, 46):
        for escenario, eventos in [
            ('normal', []),
            ('falla_dron', [Evento(75, 'falla_dron', dron_id=1)]),
            ('perdida_30pct', [Evento(75, 'perdida_mensajes', valor=0.30)]),
            ('retraso_10', [Evento(75, 'retraso_mensajes', valor=10)]),
        ]:
            sim = MotorSimulacion(semilla=semilla, eventos=eventos, pasos=150)
            filas.append({'escenario': escenario, 'semilla': semilla, **sim.ejecutar()})
    with archivo.open('w', newline='', encoding='utf-8') as f:
        escritor = csv.DictWriter(f, fieldnames=filas[0].keys())
        escritor.writeheader()
        escritor.writerows(filas)
    print(f'Resultados guardados: {archivo}')


if __name__ == '__main__':
    ejecutar()
