"""
Integrante 1 · Experimento de cobertura

Pregunta: ¿cómo cambia la cobertura, los puntos ciegos y la redundancia
al variar el número de drones y el radio de observación?

Metodología:
  - Se usa el mismo mapa (misma semilla) en todas las pruebas.
  - Para cada combinación (radio, drones) se repiten REPLICAS veces los drones
    en posiciones aleatorias distintas.
  - Se reportan la media y la desviación estándar de cada métrica.

Uso (desde la raíz del proyecto):
    python -m experimentos.ejecutar_experimentos
"""
import csv
import random
import statistics
from pathlib import Path

import config
from experimentos.graficas import graficar_cobertura_vs_drones
from simulacion.cobertura import calcular_cobertura, colocar_drones_aleatorios
from simulacion.entorno import generar_mapa_industrial, mapa_ascii

RAIZ = Path(__file__).resolve().parent.parent
RESULTADOS = RAIZ / "resultados"


def ejecutar_experimento_cobertura(entorno, drones_lista, radios, replicas,
                                   semilla_base=1000, usar_linea_de_vista=True):
    """Devuelve una lista de diccionarios, uno por combinación (radio, drones)."""
    filas = []
    for radio in radios:
        for n in drones_lista:
            coberturas, ciegos, redundancias = [], [], []
            for r in range(replicas):
                rng = random.Random(semilla_base + r)
                posiciones = colocar_drones_aleatorios(entorno, n, rng)
                res = calcular_cobertura(entorno, posiciones, radio, usar_linea_de_vista)
                coberturas.append(res.cobertura * 100)
                ciegos.append(len(res.puntos_ciegos))
                redundancias.append(res.cobertura_redundante * 100)

            filas.append({
                "radio": radio,
                "drones": n,
                "cobertura_media_pct": round(statistics.mean(coberturas), 2),
                "cobertura_desv_pct": round(statistics.stdev(coberturas), 2) if replicas > 1 else 0.0,
                "puntos_ciegos_medio": round(statistics.mean(ciegos), 1),
                "redundancia_media_pct": round(statistics.mean(redundancias), 2),
            })
    return filas


def guardar_csv(filas, ruta):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        writer.writeheader()
        writer.writerows(filas)


def imprimir_tabla(filas):
    encabezado = f"{'radio':>5} {'drones':>6} {'cobertura %':>22} {'ciegos':>8} {'redundancia %':>14}"
    print(encabezado)
    print("-" * len(encabezado))
    for f in filas:
        cob = f"{f['cobertura_media_pct']:6.2f} ± {f['cobertura_desv_pct']:5.2f}"
        print(f"{f['radio']:>5} {f['drones']:>6} {cob:>22} "
              f"{f['puntos_ciegos_medio']:>8.1f} {f['redundancia_media_pct']:>14.2f}")


def main():
    entorno = generar_mapa_industrial(
        ancho=config.ANCHO_MAPA,
        alto=config.ALTO_MAPA,
        num_edificios=config.NUM_EDIFICIOS,
        num_recargas=config.ESTACIONES_RECARGA,
        sectores_x=config.SECTORES_X,
        sectores_y=config.SECTORES_Y,
        semilla=config.SEMILLA_MAPA,
    )
    print("Mapa de la instalación (# edificio, R recarga, . libre):\n")
    print(mapa_ascii(entorno))
    print()

    filas = ejecutar_experimento_cobertura(
        entorno,
        config.DRONES_EXPERIMENTO,
        config.RADIOS_EXPERIMENTO,
        config.REPLICAS,
        usar_linea_de_vista=config.USAR_LINEA_DE_VISTA,
    )

    guardar_csv(filas, RESULTADOS / "cobertura_drones_radio.csv")
    graficar_cobertura_vs_drones(filas, RESULTADOS / "graficas" / "cobertura_vs_drones.png")

    imprimir_tabla(filas)
    print(f"\nCSV guardado en {RESULTADOS / 'cobertura_drones_radio.csv'}")


if __name__ == "__main__":
    main()
