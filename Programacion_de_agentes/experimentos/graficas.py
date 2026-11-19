"""
Integrante 2 · Gráficas del experimento comparativo de arquitecturas (Etapa 2).

Usa el backend ``Agg`` para generar imágenes PNG sin requerir entorno gráfico.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def graficar_comparacion_arquitecturas(filas, curvas_medias, ruta):
    """Genera un panel comparativo 2x2 entre arquitectura reactiva y basada en modelos.

    Paneles incluidos:
      1. Cobertura acumulada final (%) vs. número de drones (con desviación estándar).
      2. Tiempo medio sin vigilancia (pasos) vs. número de drones.
      3. Eficiencia de patrullaje (%) vs. número de drones.
      4. Evolución temporal de cobertura acumulada (%) para el escenario intermedio.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    etiquetas = {
        "reactivo": "Reactivo",
        "basado_en_modelos": "Basado en modelos",
    }
    estilos = {
        "reactivo": {"color": "#d95f02", "marker": "s", "linestyle": "--"},
        "basado_en_modelos": {"color": "#1b9e77", "marker": "o", "linestyle": "-"},
    }

    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    ax_acum, ax_sin_vig, ax_efic, ax_curva = axes.flatten()

    arquitecturas = sorted({f["arquitectura"] for f in filas})
    drones_disponibles = sorted({int(f["drones"]) for f in filas})

    for arq in arquitecturas:
        serie = sorted((f for f in filas if f["arquitectura"] == arq), key=lambda x: x["drones"])
        xs = [int(f["drones"]) for f in serie]
        est = estilos.get(arq, {"marker": "o"})
        etiq = etiquetas.get(arq, arq)

        ax_acum.errorbar(
            xs,
            [float(f["cobertura_acum_media_pct"]) for f in serie],
            yerr=[float(f["cobertura_acum_desv_pct"]) for f in serie],
            capsize=3,
            label=etiq,
            **est,
        )
        ax_sin_vig.plot(
            xs,
            [float(f["tiempo_sin_vigilancia_medio"]) for f in serie],
            label=etiq,
            **est,
        )
        ax_efic.plot(
            xs,
            [float(f["eficiencia_patrullaje_pct"]) for f in serie],
            label=etiq,
            **est,
        )

    n_ref = 4 if 4 in drones_disponibles else drones_disponibles[len(drones_disponibles) // 2]
    for arq in arquitecturas:
        curva = curvas_medias.get((arq, n_ref))
        if not curva:
            continue
        est = estilos.get(arq, {})
        ax_curva.plot(
            range(1, len(curva) + 1),
            curva,
            color=est.get("color"),
            linestyle=est.get("linestyle", "-"),
            linewidth=2.0,
            label=etiquetas.get(arq, arq),
        )

    ax_acum.set_title("Cobertura acumulada final")
    ax_acum.set_xlabel("Número de drones")
    ax_acum.set_ylabel("Cobertura acumulada (%)")
    ax_acum.set_ylim(0, 105)
    ax_acum.grid(alpha=0.3)
    ax_acum.legend()

    ax_sin_vig.set_title("Tiempo promedio sin vigilancia")
    ax_sin_vig.set_xlabel("Número de drones")
    ax_sin_vig.set_ylabel("Pasos sin supervisión (menor es mejor)")
    ax_sin_vig.grid(alpha=0.3)
    ax_sin_vig.legend()

    ax_efic.set_title("Eficiencia de patrullaje (posiciones únicas / pasos)")
    ax_efic.set_xlabel("Número de drones")
    ax_efic.set_ylabel("Eficiencia (%)")
    ax_efic.set_ylim(0, 105)
    ax_efic.grid(alpha=0.3)
    ax_efic.legend()

    ax_curva.set_title(f"Evolución de cobertura acumulada ({n_ref} drones)")
    ax_curva.set_xlabel("Paso de simulación")
    ax_curva.set_ylabel("Cobertura acumulada (%)")
    ax_curva.set_ylim(0, 105)
    ax_curva.grid(alpha=0.3)
    ax_curva.legend()

    fig.suptitle("Etapa 2 · Comparación: Arquitectura Reactiva vs. Basada en Modelos", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
