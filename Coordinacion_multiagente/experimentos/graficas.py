"""
Integrante 3 · Gráficas del experimento pizarrón vs. mensajería directa.

Convenciones visuales (iguales en todas las figuras):
    - Color = mecanismo (azul pizarrón, naranja mensajería, gris línea base).
    - Tipo de línea y marcador = pérdida de mensajes, para que la lectura no
      dependa solo del color (accesible para daltonismo e impresión en gris).
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # sin ventana: funciona en Docker/CI
import matplotlib.pyplot as plt  # noqa: E402

COLORES = {"pizarron": "#2a78d6", "mensajeria_directa": "#eb6834",
           "sin_coordinacion": "#52514e"}
NOMBRES = {"pizarron": "Pizarrón", "mensajeria_directa": "Mensajería directa",
           "sin_coordinacion": "Sin coordinación"}
ESTILOS_PERDIDA = {0.0: ("-", "o"), 0.1: ("--", "s"), 0.3: (":", "^")}
TINTA, TINTA_SEC, REJILLA = "#0b0b0b", "#52514e", "#e4e3df"


def _estilo_ejes(ax, titulo: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(titulo, fontsize=10, color=TINTA, loc="left")
    ax.set_xlabel(xlabel, fontsize=9, color=TINTA_SEC)
    ax.set_ylabel(ylabel, fontsize=9, color=TINTA_SEC)
    ax.grid(True, color=REJILLA, linewidth=0.8)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(REJILLA)
    ax.tick_params(colors=TINTA_SEC, labelsize=8)


def _filas(resumen, mecanismo, **filtros):
    salida = [f for f in resumen if f["mecanismo"] == mecanismo
              and all(f[k] == v for k, v in filtros.items())]
    return sorted(salida, key=lambda f: (f["drones"], f["retraso"] if f["retraso"] != "" else 0))


def figura_vs_retraso(resumen, drones: int, ruta: Path) -> Path:
    """Métricas de coordinación frente al retraso, para un número de drones."""
    paneles = [
        ("duplicados_evitables_medio", "Asignaciones redundantes evitables", "drones de más (media por paso)"),
        ("pasos_convergencia", "Tiempo hasta la primera asignación válida", "pasos"),
        ("recuperacion_falla", "Recuperación tras la falla de un dron", "pasos"),
        ("pasos_asignacion_valida_pct", "Pasos con asignación válida", "% de pasos"),
        ("redundancia_cobertura_pct", "Cobertura redundante (celdas vistas por 2+)", "% del mapa"),
        ("cobertura_inst_media_pct", "Cobertura instantánea media", "% del mapa"),
    ]
    fig, ejes = plt.subplots(2, 3, figsize=(13, 7.2))
    base = _filas(resumen, "sin_coordinacion", drones=drones)
    for ax, (clave, titulo, ylabel) in zip(ejes.flat, paneles):
        for mecanismo in ("pizarron", "mensajeria_directa"):
            for perdida, (linea, marca) in ESTILOS_PERDIDA.items():
                filas = _filas(resumen, mecanismo, drones=drones, perdida=perdida)
                if not filas:
                    continue
                ax.plot([f["retraso"] for f in filas], [f[clave] for f in filas],
                        color=COLORES[mecanismo], linestyle=linea, marker=marca,
                        markersize=5, linewidth=2,
                        label=f"{NOMBRES[mecanismo]} · pérdida {int(perdida * 100)} %")
        if base and base[0].get(clave, "") != "":
            ax.axhline(base[0][clave], color=COLORES["sin_coordinacion"], linewidth=1.5,
                       linestyle=(0, (6, 3)), label="Sin coordinación (referencia)")
        _estilo_ejes(ax, titulo, "retraso del canal (pasos)", ylabel)
    manejadores, etiquetas = ejes.flat[-1].get_legend_handles_labels()
    fig.legend(manejadores, etiquetas, loc="lower center", ncol=4, fontsize=8, frameon=False)
    fig.suptitle(f"Pizarrón vs. mensajería directa con {drones} drones "
                 f"(media de réplicas)", fontsize=12, color=TINTA, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.08, 1, 0.96))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return ruta


def figura_escalabilidad(resumen, retraso_ref: int, ruta: Path) -> Path:
    """Costo en mensajes y calidad de la coordinación al aumentar los drones."""
    fig, ejes = plt.subplots(1, 3, figsize=(13, 4.2))
    paneles = [
        ("mensajes_por_paso", "Mensajes enviados por paso (copias)", "mensajes / paso", 0.0),
        ("duplicados_evitables_medio", f"Redundancia evitable (retraso {retraso_ref}, pérdida 30 %)",
         "drones de más (media por paso)", 0.3),
        ("cobertura_inst_media_pct", f"Cobertura instantánea (retraso {retraso_ref}, pérdida 30 %)",
         "% del mapa", 0.3),
    ]
    for ax, (clave, titulo, ylabel, perdida) in zip(ejes, paneles):
        for mecanismo in ("pizarron", "mensajeria_directa"):
            filas = _filas(resumen, mecanismo, retraso=retraso_ref, perdida=perdida)
            ax.plot([f["drones"] for f in filas], [f[clave] for f in filas],
                    color=COLORES[mecanismo], marker="o", markersize=5, linewidth=2,
                    label=NOMBRES[mecanismo])
        if clave == "cobertura_inst_media_pct":
            base = _filas(resumen, "sin_coordinacion")
            ax.plot([f["drones"] for f in base], [f[clave] for f in base],
                    color=COLORES["sin_coordinacion"], marker="s", markersize=5,
                    linewidth=1.5, linestyle=(0, (6, 3)), label=NOMBRES["sin_coordinacion"])
        _estilo_ejes(ax, titulo, "número de drones", ylabel)
        ax.legend(fontsize=8, frameon=False)
    fig.tight_layout()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=150)
    plt.close(fig)
    return ruta


def generar_graficas(resumen, carpeta: Path) -> list[Path]:
    """Genera todas las figuras del experimento en ``carpeta``."""
    carpeta = Path(carpeta)
    drones = sorted({f["drones"] for f in resumen})
    retrasos = sorted({f["retraso"] for f in resumen if f["retraso"] != ""})
    rutas = [figura_vs_retraso(resumen, n, carpeta / f"coordinacion_vs_retraso_{n}_drones.png")
             for n in drones]
    if retrasos:
        rutas.append(figura_escalabilidad(resumen, retrasos[len(retrasos) // 2],
                                          carpeta / "escalabilidad_mensajes.png"))
    return rutas
