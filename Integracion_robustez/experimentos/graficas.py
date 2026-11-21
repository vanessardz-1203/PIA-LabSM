"""Gráficas a partir de un CSV real generado por ejecutar_robustez.py.
No produce datos de resultados por sí mismo.
"""
import csv
from collections import defaultdict
from pathlib import Path


def generar(archivo_csv=None, carpeta_salida=None):
    import matplotlib.pyplot as plt
    base = Path(__file__).resolve().parents[1] / 'resultados'
    archivo_csv = Path(archivo_csv) if archivo_csv else base / 'comparacion_robustez.csv'
    carpeta_salida = Path(carpeta_salida) if carpeta_salida else base / 'graficas'
    if not archivo_csv.is_file():
        raise FileNotFoundError('No existe el CSV real. Ejecuta primero el experimento; no se generan cifras ficticias.')
    with archivo_csv.open(newline='', encoding='utf-8') as f:
        filas = list(csv.DictReader(f))
    if not filas:
        raise ValueError('El archivo de resultados está vacío')
    grupos = defaultdict(list)
    for fila in filas:
        grupos[fila['escenario']].append(float(fila['cobertura_inst_media_pct']))
    etiquetas = list(grupos)
    promedios = [sum(grupos[n]) / len(grupos[n]) for n in etiquetas]
    carpeta_salida.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(etiquetas, promedios)
    ax.set_ylabel('Cobertura instantánea media (%)')
    ax.set_xlabel('Escenario')
    ax.set_title('Comparación experimental de robustez')
    ax.tick_params(axis='x', rotation=18)
    fig.tight_layout()
    ruta = carpeta_salida / 'cobertura_por_escenario.png'
    fig.savefig(ruta, dpi=180)
    plt.close(fig)
    return ruta


if __name__ == '__main__':
    print(generar())
