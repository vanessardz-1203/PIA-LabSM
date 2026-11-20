
"""Animación de relevos energéticos con Matplotlib."""

import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.patches import Rectangle, Circle

from Construccion_de_entorno.simulacion.entorno import (
    Entorno,
    Sector,
)
from Programacion_de_agentes.simulacion.agentes import (
    DronReactivo,
    EstadoOperativo,
)
from Coordinacion_multiagente.simulacion.coordinacion import (
    crear_coordinador,
)
from Gestion_energetica_relevos.simulacion.energia import (
    GestorEnergia,
)
from Gestion_energetica_relevos.simulacion.controlador import (
    ControladorRelevos,
)


def main():
    # 1. Crear el entorno.
    ancho, alto = 8, 8

    edificios = {
        (4, 1), (4, 2),
        (5, 1), (5, 2),
        (1, 5), (2, 5),
    }

    recargas = {(0, 0), (7, 7)}

    sector = Sector(
        id=1,
        celdas={
            (x, y)
            for x in range(ancho)
            for y in range(alto)
        },
    )

    entorno = Entorno(
        ancho=ancho,
        alto=alto,
        edificios=edificios,
        recargas=recargas,
        sectores=[sector],
    )

    # 2. Crear los drones.
    original = DronReactivo(
        id_dron=1,
        posicion=(5, 5),
        bateria=25.0,
    )

    sustituto = DronReactivo(
        id_dron=2,
        posicion=(1, 2),
        bateria=90.0,
        estado_operativo=EstadoOperativo.RESERVA,
    )

    drones = [original, sustituto]

    # 3. Crear el coordinador.
    coordinador = crear_coordinador(
        "pizarron",
        entorno.sectores,
    )

    for dron in drones:
        coordinador.registrar_dron(dron.id)

    coordinador.fijar_sector(
        original.id,
        sector.id,
        0,
    )

    # 4. Crear el controlador energético.
    gestor = GestorEnergia()

    controlador = ControladorRelevos(
        entorno=entorno,
        gestor_energia=gestor,
        coordinador=coordinador,
    )

    iniciado = controlador.iniciar(
        original=original,
        candidatos=[sustituto],
        paso=0,
    )

    if not iniciado:
        raise RuntimeError(
            "No fue posible iniciar el relevo."
        )

    # 5. Configurar la gráfica.
    fig, ax = plt.subplots(figsize=(9, 8))

    fig.patch.set_facecolor("#f8fafc")

    def dibujar(paso):
        ax.clear()

        # Procesar un paso real de la simulación.
        if paso > 0:
            coordinador.paso(paso, drones)
            controlador.avanzar(drones, paso)

        ax.set_xlim(-0.5, ancho - 0.5)
        ax.set_ylim(-0.5, alto - 0.5)
        ax.set_aspect("equal")

        ax.set_xticks(range(ancho))
        ax.set_yticks(range(alto))
        ax.grid(
            color="#cbd5e1",
            linestyle="-",
            linewidth=0.8,
        )

        ax.set_facecolor("#eff6ff")

        # Dibujar edificios.
        for x, y in edificios:
            ax.add_patch(
                Rectangle(
                    (x - 0.45, y - 0.45),
                    0.9,
                    0.9,
                    facecolor="#64748b",
                    edgecolor="#334155",
                )
            )

        # Dibujar estaciones de recarga.
        for x, y in recargas:
            ax.add_patch(
                Rectangle(
                    (x - 0.45, y - 0.45),
                    0.9,
                    0.9,
                    facecolor="#bbf7d0",
                    edgecolor="#16a34a",
                    linewidth=2,
                )
            )
            ax.text(
                x, y, "R",
                ha="center",
                va="center",
                fontsize=14,
                fontweight="bold",
                color="#166534",
            )

        # Dibujar ruta prevista del sustituto.
        relevo = controlador.relevos.get(original.id)

        if relevo is not None and relevo.ruta:
            xs = [p[0] for p in relevo.ruta]
            ys = [p[1] for p in relevo.ruta]

            ax.plot(
                xs, ys,
                "--",
                color="#2563eb",
                alpha=0.5,
                linewidth=2,
            )

        # Dibujar dron original.
        x1, y1 = original.posicion

        ax.add_patch(
            Circle(
                (x1, y1),
                radius=0.3,
                facecolor="#f97316",
                edgecolor="white",
                linewidth=2,
                zorder=5,
            )
        )

        ax.text(
            x1, y1, "1",
            ha="center",
            va="center",
            color="white",
            fontweight="bold",
            zorder=6,
        )

        # Dibujar sustituto.
        x2, y2 = sustituto.posicion

        # Desplazamiento visual cuando ambos
        # drones ocupan la misma celda.
        if (x1, y1) == (x2, y2):
            x1 -= 0.18
            x2 += 0.18

        ax.add_patch(
            Circle(
                (x2, y2),
                radius=0.3,
                facecolor="#2563eb",
                edgecolor="white",
                linewidth=2,
                zorder=5,
            )
        )

        ax.text(
            x2, y2, "2",
            ha="center",
            va="center",
            color="white",
            fontweight="bold",
            zorder=6,
        )

        # Información de estado.
        if controlador.completados > 0:
            estado = "RELEVO COMPLETADO"
            color_estado = "#16a34a"
        elif relevo is not None:
            estado = relevo.fase.value.upper()
            color_estado = "#2563eb"
        else:
            estado = "ESPERANDO"
            color_estado = "#64748b"

        ax.set_title(
            f"GESTIÓN ENERGÉTICA Y RELEVOS\n"
            f"Paso {paso} | {estado}",
            fontsize=15,
            fontweight="bold",
            color=color_estado,
            pad=18,
        )

        informacion = (
            f"Dron 1 | Batería: {original.bateria:.1f}%"
            f" | Estado: {original.estado_operativo.value}\n"
            f"Dron 2 | Batería: {sustituto.bateria:.1f}%"
            f" | Estado: {sustituto.estado_operativo.value}\n"
            f"Relevos completados: {controlador.completados}"
        )

        ax.set_xlabel(
            informacion,
            fontsize=10,
            labelpad=15,
        )

    # La animación se detiene después de mostrar
    # algunos pasos adicionales al relevo.
    animacion = FuncAnimation(
        fig,
        dibujar,
        frames=range(16),
        interval=800,
        repeat=False,
    )

    # Mantener la referencia a la animación.
    fig._animacion = animacion

    plt.tight_layout()
    plt.show()


if __name__ == "__main__":
    main()
