"""
Integrante 1 · Gráficas del experimento de cobertura.

Usa el backend 'Agg' para generar imágenes sin necesidad de ventana gráfica.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def graficar_cobertura_vs_drones(filas, ruta):
    """Una curva por radio: eje x = número de drones, eje y = cobertura media (%)."""
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(7, 4.5))
    for radio in sorted({f["radio"] for f in filas}):
        serie = sorted((f for f in filas if f["radio"] == radio), key=lambda f: f["drones"])
        ax.errorbar(
            [f["drones"] for f in serie],
            [f["cobertura_media_pct"] for f in serie],
            yerr=[f["cobertura_desv_pct"] for f in serie],
            marker="o", capsize=3, label=f"radio = {radio} celdas",
        )

    ax.set_xlabel("Número de drones")
    ax.set_ylabel("Cobertura media (%)")
    ax.set_title("Cobertura de vigilancia vs. número de drones")
    ax.set_ylim(0, 105)
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
