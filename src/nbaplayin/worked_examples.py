"""Recompute the six handwritten whiteboard pages from the raw data.

Each entry records what the page claims, what the data gives, and whether the
page needs changing. These are checks on hand arithmetic, not new results.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import build, config, model as model_mod, ratings as ratings_mod, tournament


def run(study=None) -> pd.DataFrame:
    study = study or build.load_study()
    games = study.workbook.games
    rows = []

    def check(page, quantity, workbook_value, computed, note=""):
        agrees = (workbook_value is None or
                  abs(float(workbook_value) - float(computed)) < 5e-9)
        rows.append(dict(page=page, quantity=quantity,
                         value_on_the_page=workbook_value,
                         recomputed=computed,
                         agrees=bool(agrees) if workbook_value is not None else None,
                         note=note))

    # -- Page 1: average scoring margin --------------------------------
    g25 = games[games["Season end"] == 2025].sort_values(["Game date", "ESPN game ID"])
    bos = g25[(g25.Home == "BOS") | (g25.Away == "BOS")].head(5)
    margins = [(r._6 - r._7) if r.Home == "BOS" else (r._7 - r._6)
               for r in bos.itertuples()]
    check(1, "Boston's first five margins, 2024-25", None, margins,
          "dates " + ", ".join(str(d.date()) for d in bos["Game date"]))
    check(1, "average scoring margin", 11.4, float(np.mean(margins)))

    # -- Page 2: four-team mini-league SRS ------------------------------
    mini_codes = ["BOS", "CLE", "NY", "IND"]
    mini = g25[g25.Home.isin(mini_codes) & g25.Away.isin(mini_codes)]
    idx = {c: i for i, c in enumerate(mini_codes)}
    counts = np.zeros((4, 4))
    totals = np.zeros(4)
    for r in mini.itertuples():
        i, j = idx[r.Home], idx[r.Away]
        m = r._6 - r._7
        counts[i, j] += 1
        counts[j, i] += 1
        totals[i] += m
        totals[j] -= m
    solved = ratings_mod.solve_srs(counts, totals)
    published = {"BOS": 6.105769230769236, "CLE": 3.3750000000000053,
                 "NY": -6.894230769230775, "IND": -2.5865384615384617}
    check(2, "games inside the four-team subset", 22, len(mini))
    for c in mini_codes:
        check(2, f"{c} games / total margin", None,
              f"{int(counts[idx[c]].sum())} games, {int(totals[idx[c]]):+d} margin")
        check(2, f"{c} restricted rating", published[c], float(solved[idx[c]]),
              "restricted mini-league rating, not NBA SRS")
    check(2, "ratings sum to zero", 0.0, float(solved.sum()))

    # -- Pages 3 to 8: the 2024-25 Western play-in ----------------------
    fit = model_mod.fit_window(study.features, 2025, config.BASELINE_WINDOW)
    m = build.season_model(study, 2025, fit)
    res = tournament.solve_season(m)
    gs, mem, sac, dal = (m.codes.index(c) for c in ("GS", "MEM", "SAC", "DAL"))
    check(3, "beta (3-season window ending 2023-24)", 0.11289078930596157, fit.beta)
    check(3, "h", 0.22249238011772254, fit.h)
    check(3, "P(Golden State beats Memphis at home)", 0.5207427031776123,
          m.p_game(gs, mem, 1))
    states = res.states["Western"]
    published_states = {("GS", "MEM"): 0.3545379556449871,
                        ("GS", "SAC"): 0.10245172318241284,
                        ("GS", "DAL"): 0.06375302435021239,
                        ("MEM", "GS"): 0.31143522500834026,
                        ("MEM", "SAC"): 0.10326529789028309,
                        ("MEM", "DAL"): 0.06455677392376435}
    for (s7, s8), p in states.items():
        key = (m.codes[s7], m.codes[s8])
        check(4, f"P(seed 7 = {key[0]}, seed 8 = {key[1]})",
              published_states[key], p)
    check(4, "six ordered outcomes sum to 1", 1.0, sum(states.values()))
    published_qual = {"GS": 0.8321779281859525, "MEM": 0.8337952524673748,
                      "SAC": 0.20571702107269593, "DAL": 0.12830979827397676}
    for code in ("GS", "MEM", "SAC", "DAL"):
        t = m.codes.index(code)
        check(5, f"P({code} qualifies)", published_qual[code], res.qualify_new[t])
    check(6, "the four qualification probabilities sum to 2", 2.0,
          sum(res.qualify_new[m.codes.index(c)] for c in ("GS", "MEM", "SAC", "DAL")))
    p_neutral = m.p_game(gs, mem, 0)
    check(8, "P(Golden State beats Memphis, neutral court)",
          0.4651879350133163, p_neutral)
    binomial = sum(math.comb(7, k) * p_neutral ** k * (1 - p_neutral) ** (7 - k)
                   for k in range(4, 8))
    check(8, "constant-p best-of-seven", 0.4242166807737399, binomial,
          "equals the backward recursion with a constant p")
    check(8, "backward recursion agrees with the binomial sum", binomial,
          tournament.series_probability([p_neutral] * 7))
    check(9, "series with home court: Golden State hosts Memphis", None,
          m.p_series(gs, mem, True), "venue sequence H,H,A,A,H,A,H")
    return pd.DataFrame(rows)
