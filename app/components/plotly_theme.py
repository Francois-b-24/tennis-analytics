"""Thème Plotly de l'app : palette accessible et mise en page sobre.

Les couleurs de texte, de fond et de grille ne sont **pas** codées en dur :
`st.plotly_chart` applique le thème Streamlit actif (clair ou sombre). Ce
module ne fixe que ce qui porte du sens : couleurs par surface et par
circuit, marges, légende et infobulles.

Palette surfaces : Okabe-Ito (distinguable par les daltoniens). Pour ne pas
dépendre de la seule couleur, les séries par surface utilisent aussi des
tirets différents (:data:`SURFACE_DASH`).
"""

from __future__ import annotations

from typing import Final

import plotly.graph_objects as go

FONT_FAMILY: Final[str] = "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"

#: Couleurs par surface (Okabe-Ito) — clés anglaises (données) et françaises (affichage).
SURFACE_COLORS: Final[dict[str, str]] = {
    "Hard": "#0072B2",
    "Clay": "#D55E00",
    "Grass": "#009E73",
    "Dur": "#0072B2",
    "Terre battue": "#D55E00",
    "Gazon": "#009E73",
    "Global": "#6B7A72",
}

#: Style de trait par surface (redondance avec la couleur).
SURFACE_DASH: Final[dict[str, str]] = {
    "Global": "solid",
    "Dur": "dash",
    "Terre battue": "dot",
    "Gazon": "dashdot",
}

#: Couleurs par circuit.
CIRCUIT_COLORS: Final[dict[str, str]] = {"ATP": "#3D5AFE", "WTA": "#C2185B"}

#: Victoire / défaite : bleu et orange (lisibles en daltonisme rouge-vert).
WIN_COLOR: Final[str] = "#0072B2"
LOSS_COLOR: Final[str] = "#E69F00"

#: Couleur d'accent (série unique).
ACCENT: Final[str] = "#1B7A4B"

PALETTE: Final[list[str]] = [
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#E69F00",
    "#56B4E9",
    "#6B7A72",
]

#: Libellés français des surfaces (valeurs normalisées en base).
SURFACE_LABELS: Final[dict[str, str]] = {
    "hard": "Dur",
    "clay": "Terre battue",
    "grass": "Gazon",
    "Hard": "Dur",
    "Clay": "Terre battue",
    "Grass": "Gazon",
    "Carpet": "Moquette",
}

# Compatibilité : anciens noms encore importés par certaines pages.
TENNIS_HARD: Final[str] = SURFACE_COLORS["Hard"]
TENNIS_CLAY: Final[str] = SURFACE_COLORS["Clay"]
TENNIS_GREEN: Final[str] = SURFACE_COLORS["Grass"]


def apply_tennis_theme(fig: go.Figure, *, height: int | None = None) -> go.Figure:
    """Applique la mise en page commune à une figure Plotly.

    Args:
        fig: Figure à styliser (mutée en place et retournée).
        height: Hauteur en pixels (facultatif).

    Returns:
        La même figure.
    """
    fig.update_layout(
        font=dict(family=FONT_FAMILY, size=13),
        colorway=PALETTE,
        margin=dict(l=8, r=8, t=24, b=8),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="left",
            x=0,
            title_text="",
        ),
        hoverlabel=dict(font=dict(family=FONT_FAMILY, size=12)),
        hovermode="x unified",
        title=None,
    )
    if height:
        fig.update_layout(height=height)
    fig.update_xaxes(automargin=True, showgrid=False)
    fig.update_yaxes(automargin=True, zeroline=False)
    return fig
