"""Thème Plotly tennis (surfaces) et application cohérente aux figures."""

from __future__ import annotations

from typing import Final

import plotly.graph_objects as go

TENNIS_GREEN: Final[str] = "#3A7D44"
TENNIS_CLAY: Final[str] = "#C27940"
TENNIS_HARD: Final[str] = "#1F4E79"
TENNIS_LINE: Final[str] = "#2F2F2F"
FONT_FAMILY: Final[str] = "Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif"

TENNIS_PALETTE: Final[list[str]] = [TENNIS_HARD, TENNIS_CLAY, TENNIS_GREEN]


def apply_tennis_theme(fig: go.Figure) -> go.Figure:
    """Applique le thème tennis (couleurs, polices, axes) à une figure Plotly.

    Le layout est optimisé mobile : marges réduites, légende en bas (mieux que
    sur le côté quand l'écran est étroit), hovermode adapté au tactile.

    Args:
        fig: Figure à styliser (mutée en place et retournée).

    Returns:
        La même figure stylisée.
    """
    fig.update_layout(
        template="plotly_white",
        font=dict(family=FONT_FAMILY, color=TENNIS_LINE, size=13),
        title_font=dict(size=16, color=TENNIS_LINE),
        colorway=TENNIS_PALETTE,
        hoverlabel=dict(
            font=dict(family=FONT_FAMILY, size=12),
            bgcolor="rgba(30, 45, 36, 0.95)",
            bordercolor="rgba(0, 0, 0, 0)",
        ),
        # Marges resserrées pour maximiser la zone de tracé sur mobile
        margin=dict(l=40, r=20, t=50, b=40),
        # Légende en bas, horizontale : nettement mieux sur mobile que sur le côté
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.25,
            xanchor="center",
            x=0.5,
            font=dict(size=11),
            bgcolor="rgba(255, 255, 255, 0)",
        ),
        # Touch-friendly : zone de hover plus généreuse
        hovermode="closest",
        # Pas de fond gris, fond blanc pur
        paper_bgcolor="rgba(0, 0, 0, 0)",
        plot_bgcolor="rgba(0, 0, 0, 0)",
        # Autosize pour que Plotly recalcule la largeur sur resize
        autosize=True,
    )
    fig.update_xaxes(
        title_font=dict(size=12),
        tickfont=dict(size=11),
        showline=True,
        linewidth=1,
        linecolor="#D0D0D0",
        mirror=False,  # Pas de bordure en haut → moins encombré
        gridcolor="#F0F0F0",
        zerolinecolor="#E0E0E0",
        # Auto-rotation des labels longs (utile sur mobile pour les dates)
        automargin=True,
    )
    fig.update_yaxes(
        title_font=dict(size=12),
        tickfont=dict(size=11),
        showline=True,
        linewidth=1,
        linecolor="#D0D0D0",
        mirror=False,
        gridcolor="#F0F0F0",
        zerolinecolor="#E0E0E0",
        automargin=True,
    )
    return fig
