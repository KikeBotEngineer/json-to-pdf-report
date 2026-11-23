from dataclasses import dataclass
from datetime import date
from io import BytesIO

import pandas as pd
from matplotlib.dates import DateFormatter
from matplotlib.figure import Figure

from app.metrics import DONE
from app.models import Status

PALETTE = ["#334155", "#64748b", "#0f766e", "#94a3b8", "#b45309", "#cbd5e1", "#e2e8f0"]
INK = "#1e293b"
GRID = "#e2e8f0"
TOP_CATEGORIES = 6


@dataclass(frozen=True)
class ChartImage:
    title: str
    png: BytesIO


def _figure() -> tuple[Figure, object]:
    fig = Figure(figsize=(7, 3.6), dpi=150)
    ax = fig.add_subplot()
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=INK, labelsize=8)
    return fig, ax


def _render(title: str, fig: Figure) -> ChartImage:
    buf = BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png")
    buf.seek(0)
    return ChartImage(title, buf)


def _no_data(ax) -> None:
    ax.set_axis_off()
    ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", color=INK, transform=ax.transAxes)


def by_status(df: pd.DataFrame) -> ChartImage:
    counts = df["status"].value_counts().reindex(list(Status), fill_value=0)
    fig, ax = _figure()
    bars = ax.bar([s.value for s in counts.index], counts.values, color=PALETTE[0], width=0.6)
    ax.bar_label(bars, fontsize=8, color=INK)
    ax.set_ylabel("Tickets", color=INK, fontsize=9)
    ax.grid(axis="y", color=GRID)
    ax.set_axisbelow(True)
    return _render("Tickets por estado", fig)


def resolution_histogram(df: pd.DataFrame) -> ChartImage:
    hours = df.loc[df["status"].isin(DONE), "hours"]
    fig, ax = _figure()
    if hours.empty:
        _no_data(ax)
    else:
        # A few very slow tickets squash the rest; fold everything above P99 into the last bin.
        cap = hours.quantile(0.99)
        ax.hist(hours.clip(upper=cap), bins=30, color=PALETTE[2], edgecolor="white")
        label = f"Horas hasta resolución (la última barra incluye > {cap:.0f} h)"
        ax.set_xlabel(label, color=INK, fontsize=9)
        ax.set_ylabel("Tickets", color=INK, fontsize=9)
        ax.grid(axis="y", color=GRID)
        ax.set_axisbelow(True)
    return _render("Distribución del tiempo de resolución", fig)


def by_category(df: pd.DataFrame) -> ChartImage:
    counts = df["category"].value_counts()
    if len(counts) > TOP_CATEGORIES:
        rest = counts.iloc[TOP_CATEGORIES:].sum()
        counts = pd.concat([counts.iloc[:TOP_CATEGORIES], pd.Series({"Otras": rest})])
    fig, ax = _figure()
    pct = 100 * counts / counts.sum()
    _, labels = ax.pie(
        counts.values,
        labels=[f"{name} ({p:.0f}%)" for name, p in pct.items()],
        colors=PALETTE[: len(counts)],
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.4, "edgecolor": "white"},
        textprops={"fontsize": 8, "color": INK},
    )
    # Categories are user input: a "$...$" would otherwise be parsed as mathtext.
    for label in labels:
        label.set_parse_math(False)
    ax.set_aspect("equal")
    return _render("Tickets por categoría", fig)


def daily_flow(df: pd.DataFrame, start: date, end: date) -> ChartImage:
    days = pd.date_range(start, end, freq="D").date
    created = df["created_at"].dt.date.value_counts().reindex(days, fill_value=0)
    done = df[df["status"].isin(DONE)]
    resolved = done["resolved_at"].dt.date.value_counts().reindex(days, fill_value=0)
    fig, ax = _figure()
    ax.plot(days, created.values, color=PALETTE[0], label="Creados", linewidth=1.8)
    ax.plot(days, resolved.values, color=PALETTE[4], label="Resueltos", linewidth=1.8)
    ax.set_ylabel("Tickets", color=INK, fontsize=9)
    ax.grid(axis="y", color=GRID)
    ax.set_ylim(bottom=0)
    ax.xaxis.set_major_formatter(DateFormatter("%d/%m"))
    ax.legend(frameon=False, fontsize=8)
    return _render("Creados vs. resueltos por día", fig)


def build(df: pd.DataFrame, start: date, end: date) -> list[ChartImage]:
    return [
        by_status(df),
        resolution_histogram(df),
        by_category(df),
        daily_flow(df, start, end),
    ]
