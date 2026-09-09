"""Charts. Every figure is written as both PNG and SVG into outputs/figures.

Design rules followed here: one measure per axis, a fixed two-colour
categorical assignment (blue = old format, orange = play-in format) that never
changes between charts, a recessive grid, direct labels only where they carry
information, and a legend whenever two series share an axis.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config

OLD = "#2a78d6"        # categorical slot 1
NEW = "#eb6834"        # categorical slot 2
ACCENT = "#1baf7a"
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#d9d8d4"
SURFACE = "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE, "text.color": INK,
    "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.edgecolor": GRID, "grid.color": GRID, "grid.linewidth": 0.6,
    "font.size": 10, "axes.titlesize": 12, "axes.titleweight": "semibold",
    "axes.spines.top": False, "axes.spines.right": False,
    "figure.dpi": 130,
})


def _save(fig, name: str) -> list[str]:
    paths = []
    for ext in ("png", "svg"):
        p = config.OUT_FIGURES / f"{name}.{ext}"
        fig.savefig(p, bbox_inches="tight")
        paths.append(str(p))
    plt.close(fig)
    return paths


def _season_label(y: int) -> str:
    return f"{y - 1}-{str(y)[2:]}"


def difference_by_season(summary: pd.DataFrame, name="fig1_difference_by_season"):
    """The headline: change in the strongest team's title probability."""
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    x = np.arange(len(summary))
    d = summary["mc_difference_pp"].to_numpy()
    err = 1.96 * summary["mc_paired_se_pp"].to_numpy()
    colors = [NEW if v > 0 else OLD for v in d]
    ax.bar(x, d, color=colors, width=0.56, zorder=3)
    ax.errorbar(x, d, yerr=err, fmt="none", ecolor=INK, elinewidth=1.2,
                capsize=4, zorder=4)
    for xi, v, e in zip(x, d, err):
        top = v + e if v > 0 else v - e
        ax.annotate(f"{v:+.2f}", (xi, top), textcoords="offset points",
                    xytext=(0, 7 if v > 0 else -16), ha="center",
                    fontsize=9, color=INK)
    ax.axhline(0, color=INK, linewidth=1.0, zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{_season_label(s)}\n{t}" for s, t in
                        zip(summary.season, summary.strongest_team)])
    ax.set_ylabel("Change in title probability (percentage points)")
    ax.set_title("Play-in format minus old format, highest-rated team")
    ax.grid(axis="y", zorder=0)
    ax.margins(y=0.25)
    ax.annotate("Bars above zero: the play-in format makes the strongest team "
                "more likely to win.\nWhiskers are 95% Monte Carlo intervals "
                "for the simulated difference.",
                xy=(0, -0.30), xycoords="axes fraction", fontsize=8.5,
                color=MUTED)
    return _save(fig, name)


def exact_vs_simulated(check: pd.DataFrame, name="fig2_exact_vs_simulated"):
    fig, ax = plt.subplots(figsize=(5.4, 5.2))
    for fmt, color, marker in (("old", OLD, "o"), ("play-in", NEW, "^")):
        sub = check[check.format == fmt]
        ax.scatter(sub.exact, sub.simulated, s=26, facecolor="none",
                   edgecolor=color, linewidth=1.3, marker=marker,
                   label=f"{fmt} format", zorder=3)
    lim = max(check.exact.max(), check.simulated.max()) * 1.08
    ax.plot([0, lim], [0, lim], color=MUTED, linewidth=1.0, linestyle=(0, (4, 3)),
            zorder=2, label="exact = simulated")
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    ax.set_xlabel("Exact championship probability")
    ax.set_ylabel("Simulated share of tournaments won")
    ax.set_title("Simulation reproduces the exact calculation")
    ax.grid(zorder=0)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    return _save(fig, name)


def calibration(tbl: pd.DataFrame, name="fig3_calibration"):
    fig, ax = plt.subplots(figsize=(5.6, 4.6))
    ax.plot([0.2, 0.85], [0.2, 0.85], color=MUTED, linewidth=1.0,
            linestyle=(0, (4, 3)), zorder=2, label="perfect calibration")
    ax.errorbar(tbl.mean_predicted, tbl.observed,
                yerr=1.96 * tbl.standard_error, fmt="o", color=OLD,
                markersize=7, capsize=4, linewidth=1.4, zorder=3,
                label="held-out regular-season games")
    for r in tbl.itertuples():
        ax.annotate(f"{r.games:,}", (r.mean_predicted, r.observed),
                    textcoords="offset points", xytext=(7, -10), fontsize=8,
                    color=MUTED)
    ax.set_xlabel("Predicted home-win probability")
    ax.set_ylabel("Observed home-win rate")
    ax.set_title("Calibration, five study seasons pooled")
    ax.grid(zorder=0)
    ax.legend(frameon=False, fontsize=9, loc="upper left")
    ax.annotate("Labels give the number of games in each bin; whiskers are 95% "
                "intervals.", xy=(0, -0.22), xycoords="axes fraction",
                fontsize=8.5, color=MUTED)
    return _save(fig, name)


def title_probabilities(team_tbl: pd.DataFrame, season: int,
                        name=None, top: int = 10):
    name = name or f"fig4_title_probabilities_{season}"
    sub = (team_tbl[team_tbl.season == season]
           .sort_values("rating", ascending=False).head(top))
    y = np.arange(len(sub))[::-1]
    fig, ax = plt.subplots(figsize=(7.0, 0.42 * len(sub) + 1.8))
    ax.barh(y + 0.19, sub.title_old * 100, height=0.34, color=OLD,
            label="old format", zorder=3)
    ax.barh(y - 0.19, sub.title_playin * 100, height=0.34, color=NEW,
            label="play-in format", zorder=3)
    for yi, r in zip(y, sub.itertuples()):
        ax.annotate(f"{r.title_old * 100:.1f}", (r.title_old * 100, yi + 0.19),
                    xytext=(4, -3), textcoords="offset points", fontsize=8,
                    color=MUTED)
        ax.annotate(f"{r.title_playin * 100:.1f}", (r.title_playin * 100, yi - 0.19),
                    xytext=(4, -3), textcoords="offset points", fontsize=8,
                    color=MUTED)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{t} ({c[0]}{int(p)})" for t, c, p in
                        zip(sub.team, sub.conference, sub.position)])
    ax.set_xlabel("Championship probability (%)")
    ax.set_title(f"{_season_label(season)}: ten highest-rated teams "
                 "(conference and regular-season position in brackets)")
    ax.grid(axis="x", zorder=0)
    ax.legend(frameon=False, fontsize=9, loc="lower right")
    ax.margins(x=0.12)
    return _save(fig, name)


def qualification(team_tbl: pd.DataFrame, name="fig5_qualification"):
    sub = team_tbl[team_tbl.position.between(7, 10)].copy()
    fig, axes = plt.subplots(1, 5, figsize=(11.5, 3.4), sharey=True)
    for ax, season in zip(axes, config.STUDY_SEASONS):
        s = sub[sub.season == season].sort_values(["conference", "position"])
        x = np.arange(len(s))
        ax.bar(x, s.qualify_playin * 100, color=NEW, width=0.62, zorder=3)
        for xi, (code, v, pos) in enumerate(zip(s.team, s.qualify_playin,
                                                s.position)):
            ax.annotate(code, (xi, v * 100), xytext=(0, 3), fontsize=7.5,
                        textcoords="offset points", ha="center", rotation=90,
                        color=MUTED)
        ax.axhline(100, color=OLD, linewidth=1.2, linestyle=(0, (4, 3)), zorder=4)
        ax.set_xticks(x)
        ax.set_xticklabels(list(s.position), fontsize=8)
        ax.set_title(_season_label(season), fontsize=10)
        ax.grid(axis="y", zorder=0)
        ax.axvline(3.5, color=GRID, linewidth=1.0, zorder=1)
        ax.set_xlabel("position  (East | West)")
    axes[0].set_ylabel("Probability of reaching the playoffs (%)")
    fig.suptitle("Play-in format: what positions 7 to 10 are playing for "
                 "(dashed line: positions 7 and 8 were automatic under the old "
                 "format)", fontsize=11, y=1.04)
    return _save(fig, "fig5_qualification")


def sensitivity_grid(sens: pd.DataFrame, name="fig6_sensitivity"):
    sub = sens[sens.target_rule != "baseline SRS strongest team"].copy()
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    variants = sorted(sub.variant.unique())
    width = 0.8 / len(variants)
    x = np.arange(len(config.STUDY_SEASONS))
    shades = [OLD, "#6aa2e4", "#a9c8ef", NEW, "#f29a74", "#f7c4ab"]
    for k, v in enumerate(variants):
        s = sub[sub.variant == v].set_index("season").reindex(config.STUDY_SEASONS)
        ax.bar(x + k * width - 0.4 + width / 2, s.difference * 100, width=width,
               color=shades[k % len(shades)], label=v, zorder=3)
    ax.axhline(0, color=INK, linewidth=1.0, zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels([_season_label(s) for s in config.STUDY_SEASONS])
    ax.set_ylabel("Change in title probability (pp)")
    ax.set_title("Sensitivity: training window and rating specification")
    ax.grid(axis="y", zorder=0)
    ax.legend(frameon=False, fontsize=8, ncol=3, loc="upper center",
              bbox_to_anchor=(0.5, -0.12))
    ax.margins(y=0.12)
    return _save(fig, name)


def field_strength(summary: pd.DataFrame, name="fig7_field_strength"):
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    x = np.arange(len(summary))
    ax.bar(x - 0.19, summary.field_old / 16, width=0.34, color=OLD,
           label="old format", zorder=3)
    ax.bar(x + 0.19, summary.field_playin / 16, width=0.34, color=NEW,
           label="play-in format", zorder=3)
    for xi, (a, b) in enumerate(zip(summary.field_old / 16,
                                    summary.field_playin / 16)):
        ax.annotate(f"{a:.2f}", (xi - 0.19, a), xytext=(0, 3), fontsize=8,
                    textcoords="offset points", ha="center", color=MUTED)
        ax.annotate(f"{b:.2f}", (xi + 0.19, b), xytext=(0, 3), fontsize=8,
                    textcoords="offset points", ha="center", color=MUTED)
    ax.set_xticks(x)
    ax.set_xticklabels([_season_label(s) for s in summary.season])
    ax.set_ylabel("Mean SRS of the 16-team playoff field")
    ax.set_title("Expected strength of the playoff field")
    ax.grid(axis="y", zorder=0)
    ax.legend(frameon=False, fontsize=9)
    return _save(fig, name)
