"""The whole study, start to finish.

Run with ``python run_all.py``. Every table it writes lands in outputs/tables,
every chart in outputs/figures, and a machine-readable copy of the headline
numbers in outputs/tables/results.json.
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from . import (audit, build, config, figures, model as model_mod, montecarlo,
               sensitivity, tournament, validation)


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(replicates: int = config.MC_REPLICATES, seed: int = config.MC_SEED,
        skip_audit: bool = False) -> dict:
    config.ensure_dirs()
    t_start = time.time()

    if not skip_audit:
        _log("step 1/8  auditing the workbook against independent sources")
        audit.run()

    _log("step 2/8  building ratings and pregame features")
    study = build.load_study()
    study.features.to_csv(config.DATA_PROCESSED / "pregame_features.csv", index=False)
    study.workbook.games.to_csv(
        config.DATA_PROCESSED / "regular_season_games.csv", index=False)
    ratings_rows = []
    for season, tab in study.season_tables.items():
        for code, i in study.index.items():
            ratings_rows.append(dict(season=season, team=code,
                                     srs=tab["srs"][i], bradley_terry=tab["bt"][i],
                                     games=int(tab["counts"][i].sum()),
                                     total_margin=float(tab["totals"][i])))
    pd.DataFrame(ratings_rows).to_csv(
        config.DATA_PROCESSED / "team_ratings.csv", index=False)
    _log(f"          {len(study.features):,} feature rows, "
         f"{len(study.workbook.games):,} games, 150 team-seasons")

    _log("step 3/8  fitting the game model and validating it out of sample")
    coeffs = validation.coefficient_table(study)
    coeffs.to_csv(config.OUT_TABLES / "coefficients.csv", index=False)
    valid = validation.evaluate(study)
    valid.to_csv(config.OUT_TABLES / "validation.csv", index=False)
    calib = validation.pooled_calibration(study)
    calib.to_csv(config.OUT_TABLES / "calibration.csv", index=False)

    _log("step 4/8  solving both formats exactly")
    exact = sensitivity.exact_results(study)
    summary_rows, team_rows, state_rows, adv_rows = [], [], [], []
    for season, (m, res, fit) in exact.items():
        s = res.strongest
        summary_rows.append(dict(
            season=season, strongest_team=m.codes[s],
            strongest_rating=float(m.ratings[s]),
            strongest_position=m.rank[s], strongest_conference=m.conference[s],
            beta=fit.beta, h=fit.h, train_games=fit.n_train,
            exact_old=res.title_old[s], exact_playin=res.title_new[s],
            exact_difference=res.title_new[s] - res.title_old[s],
            champion_rating_old=res.expected_champion_rating[0],
            champion_rating_playin=res.expected_champion_rating[1],
            field_old=res.expected_field_rating[0],
            field_playin=res.expected_field_rating[1]))
        for t in range(len(m.codes)):
            team_rows.append(dict(
                season=season, team=m.codes[t], conference=m.conference[t],
                position=m.rank[t], rating=float(m.ratings[t]),
                wins=m.wins[t], losses=m.games_played[t] - m.wins[t],
                qualify_old=res.qualify_old[t], qualify_playin=res.qualify_new[t],
                title_old=res.title_old[t], title_playin=res.title_new[t],
                title_difference=res.title_new[t] - res.title_old[t]))
            adv_rows.append(dict(
                season=season, team=m.codes[t],
                old_round1=res.rounds_old[t][0] if res.rounds_old[t] else 0.0,
                old_round2=res.rounds_old[t][1] if res.rounds_old[t] else 0.0,
                old_conference=res.rounds_old[t][2] if res.rounds_old[t] else 0.0,
                old_title=res.title_old[t],
                playin_round1=res.rounds_new[t][0],
                playin_round2=res.rounds_new[t][1],
                playin_conference=res.rounds_new[t][2],
                playin_title=res.title_new[t]))
        for conf, states in res.states.items():
            for k, ((s7, s8), p) in enumerate(states.items(), 1):
                state_rows.append(dict(season=season, conference=conf, state=k,
                                       seed7=m.codes[s7], seed8=m.codes[s8],
                                       probability=p))
    summary = pd.DataFrame(summary_rows)
    team_tbl = pd.DataFrame(team_rows)
    states_tbl = pd.DataFrame(state_rows)
    adv_tbl = pd.DataFrame(adv_rows)
    team_tbl.to_csv(config.OUT_TABLES / "exact_team_results.csv", index=False)
    states_tbl.to_csv(config.OUT_TABLES / "playin_states.csv", index=False)
    adv_tbl.to_csv(config.OUT_TABLES / "advancement.csv", index=False)

    _log(f"step 5/8  simulating {replicates:,} tournaments per format per season")
    mc_rows, check_rows = [], []
    for season, (m, res, _) in exact.items():
        t0 = time.time()
        mc = montecarlo.simulate_season(m, replicates=replicates, seed=seed)
        p_old = mc.wins_old / mc.replicates
        p_new = mc.wins_new / mc.replicates
        mc_rows.append(dict(
            season=season, strongest_team=m.codes[mc.strongest],
            replicates=mc.replicates, seed=seed,
            wins_old=mc.wins_old, wins_playin=mc.wins_new,
            mc_old=p_old, mc_playin=p_new,
            mc_se_old=float(np.sqrt(p_old * (1 - p_old) / mc.replicates)),
            mc_se_playin=float(np.sqrt(p_new * (1 - p_new) / mc.replicates)),
            mc_difference=mc.paired_mean, mc_paired_se=mc.paired_se,
            mc_independent_se=mc.independent_se,
            exact_old=res.title_old[mc.strongest],
            exact_playin=res.title_new[mc.strongest],
            exact_difference=res.title_new[mc.strongest] - res.title_old[mc.strongest]))
        for t in range(len(m.codes)):
            for fmt, counts, exact_p in (
                    ("old", mc.champion_counts["old"], res.title_old[t]),
                    ("play-in", mc.champion_counts["play-in"], res.title_new[t])):
                check_rows.append(dict(season=season, team=m.codes[t], format=fmt,
                                       exact=exact_p,
                                       simulated=counts[t] / mc.replicates,
                                       wins=int(counts[t])))
        _log(f"          {season}: {mc.replicates:,} x 2 formats in "
             f"{time.time() - t0:.1f}s, difference "
             f"{mc.paired_mean * 100:+.3f} pp (se {mc.paired_se * 100:.3f})")
    mc_tbl = pd.DataFrame(mc_rows)
    check = pd.DataFrame(check_rows)
    mc_tbl.to_csv(config.OUT_TABLES / "monte_carlo_summary.csv", index=False)
    check.to_csv(config.OUT_TABLES / "monte_carlo_vs_exact.csv", index=False)

    merged = summary.merge(mc_tbl.drop(columns=["exact_old", "exact_playin",
                                                "exact_difference",
                                                "strongest_team"]), on="season")
    merged["mc_difference_pp"] = merged.mc_difference * 100
    merged["mc_paired_se_pp"] = merged.mc_paired_se * 100
    merged.to_csv(config.OUT_TABLES / "season_summary.csv", index=False)

    page6 = pd.DataFrame({
        "Season": [f"{s - 1}-{str(s)[2:]}" for s in merged.season],
        "Highest-rated team": merged.strongest_team,
        "Old-format simulated title probability":
            merged.mc_old.map(lambda v: f"{v * 100:.2f}%"),
        "Play-in simulated title probability":
            merged.mc_playin.map(lambda v: f"{v * 100:.2f}%"),
        "Difference in percentage points":
            merged.mc_difference_pp.map(lambda v: f"{v:+.2f}"),
    })
    page6.to_csv(config.OUT_TABLES / "page6_table.csv", index=False)

    _log("step 6/8  sensitivity analysis")
    sens_window = sensitivity.window_and_spec(study)
    sens_finals = sensitivity.finals_hosting(study)
    sens_margin = sensitivity.standings_margin_variant(study)
    sens_date = sensitivity.date_defect_variant(study)
    sens_window.to_csv(config.OUT_TABLES / "sensitivity_window_and_spec.csv", index=False)
    sens_finals.to_csv(config.OUT_TABLES / "sensitivity_finals_hosting.csv", index=False)
    pd.concat([sens_margin, sens_date]).to_csv(
        config.OUT_TABLES / "sensitivity_data_issues.csv", index=False)
    finals_notes = pd.DataFrame(
        [n for season, (m, _, _) in exact.items() for n in m.finals_notes])
    finals_notes.to_csv(config.OUT_TABLES / "finals_hosting_ties.csv", index=False)

    _log("step 7/8  drawing charts")
    figures.difference_by_season(merged)
    figures.exact_vs_simulated(check)
    figures.calibration(calib)
    figures.title_probabilities(team_tbl, 2025)
    figures.qualification(team_tbl)
    figures.sensitivity_grid(sens_window)
    figures.field_strength(merged)

    _log("step 8/8  writing the results file")
    results = _collect(merged, mc_tbl, check, valid, coeffs, calib, sens_window,
                       sens_finals, sens_margin, sens_date, finals_notes,
                       team_tbl, states_tbl, replicates, seed)
    (config.OUT_TABLES / "results.json").write_text(json.dumps(results, indent=2))
    _log(f"done in {time.time() - t_start:.1f}s")
    return dict(results=results, summary=merged, team_table=team_tbl,
                validation=valid, coefficients=coeffs, calibration=calib,
                sensitivity_window=sens_window, sensitivity_finals=sens_finals,
                sensitivity_data=pd.concat([sens_margin, sens_date]),
                monte_carlo=mc_tbl, check=check, states=states_tbl,
                advancement=adv_tbl, finals_notes=finals_notes, study=study)


def _collect(merged, mc_tbl, check, valid, coeffs, calib, sens_window,
             sens_finals, sens_margin, sens_date, finals_notes, team_tbl,
             states_tbl, replicates, seed) -> dict:
    gap = (check.simulated - check.exact).abs()
    mean_exact = float(merged.exact_difference.mean())
    mean_mc = float(merged.mc_difference.mean())
    se_mean = float(np.sqrt((merged.mc_paired_se ** 2).sum()) / len(merged))
    return dict(
        replicates=int(replicates), seed=int(seed),
        seasons=[int(s) for s in merged.season],
        five_season_mean_exact_pp=mean_exact * 100,
        five_season_mean_mc_pp=mean_mc * 100,
        five_season_mean_se_pp=se_mean * 100,
        seasons_where_playin_helps=int((merged.exact_difference > 0).sum()),
        max_abs_exact_minus_simulated=float(gap.max()),
        mean_abs_exact_minus_simulated=float(gap.mean()),
        worst_z_exact_vs_simulated=float(
            (gap / np.sqrt(np.maximum(check.exact * (1 - check.exact), 1e-12)
                           / replicates)).max()),
        unresolved_finals_ties=int((finals_notes.rule.str.startswith("unresolved")).sum())
        if len(finals_notes) else 0,
        finals_tie_pairs=int(len(finals_notes)),
        window_spec_range_pp=[float(sens_window.difference.min() * 100),
                              float(sens_window.difference.max() * 100)],
        finals_rule_max_shift_pp=float(
            (sens_finals.groupby("season").difference.max()
             - sens_finals.groupby("season").difference.min()).max() * 100),
        standings_margin_max_shift_pp=float(
            (sens_margin.set_index("season").difference
             - merged.set_index("season").exact_difference).abs().max() * 100),
        date_defect_max_shift_pp=float(
            (sens_date.set_index("season").difference
             - merged.set_index("season").exact_difference).abs().max() * 100),
    )
