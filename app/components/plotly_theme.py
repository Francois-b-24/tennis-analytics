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

    Args:
        fig: Figure à styliser (mutée en place et retournée).

    Returns:
        La même figure stylisée.
    """
    fig.update_layout(
        template="plotly_white",
        font=dict(family=FONT_FAMILY, color=TENNIS_LINE),
        title_font=dict(size=18, color=TENNIS_LINE),
        legend_title_text="Légende",
        colorway=TENNIS_PALETTE,
        hoverlabel=dict(font=dict(family=FONT_FAMILY)),
    )
    fig.update_xaxes(
        title_font=dict(size=14),
        tickfont=dict(size=12),
        showline=True,
        linewidth=1,
        linecolor="#D0D0D0",
        mirror=True,
    )
    fig.update_yaxes(
        title_font=dict(size=14),
        tickfont=dict(size=12),
        showline=True,
        linewidth=1,
        linecolor="#D0D0D0",
        mirror=True,
    )
    return fig
