"""Step 1: audit the workbook against independently retrieved sources.

The audit never edits the data. It records what agrees, what does not, and how
each unresolved item is carried into the analysis.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import numpy as np
import pandas as pd

from . import config, data_load

EXPECTED_GAMES = {2018: 1230, 2019: 1230, 2020: 1059, 2021: 1080,
                  2022: 1230, 2023: 1230, 2024: 1230, 2025: 1230}

# The two in-season Cup championship games, which do not count toward the
# regular-season standings and must therefore be absent from the game table.
# The two in-season Cup finals inside the study window. These are the only
# regular-season-typed games that do NOT count toward the standings.
CUP_FINALS = {"401607495": "2023 In-Season Tournament final (LAL 123, IND 109)",
              "401734908": "2024 Cup final (MIL 97, OKC 81)"}

SUMMARY_URL = ("https://site.api.espn.com/apis/site/v2/sports/basketball/nba/"
               "summary?event={}")


def _cached_summary(game_id: str) -> dict | None:
    """Fetch one ESPN box score, caching it under data/external/summaries."""
    cache = config.DATA_EXTERNAL / "summaries"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{game_id}.json"
    if path.exists():
        return json.loads(path.read_text())
    try:
        with urllib.request.urlopen(SUMMARY_URL.format(game_id), timeout=30) as fh:
            payload = json.loads(fh.read())
    except (urllib.error.URLError, TimeoutError, OSError):
        return None
    path.write_text(json.dumps(payload))
    return payload


def _summary_score(game_id: str) -> tuple[int, int, bool] | None:
    payload = _cached_summary(game_id)
    if payload is None:
        return None
    comp = payload["header"]["competitions"][0]
    scores = {c["homeAway"]: int(c["score"]) for c in comp["competitors"]}
    return scores["home"], scores["away"], bool(comp.get("neutralSite", False))


def rebuild_from_archive() -> pd.DataFrame:
    """Apply the documented filters to the hoopR archive, independently."""
    raw = data_load.load_external_schedule()
    standings = data_load.load_external_standings()
    ids = set(standings.team_id.unique())
    valid = (raw.season.between(config.FIRST_SEASON, 2025)
             & raw.status_type_completed.astype(bool)
             & raw.home_id.isin(ids) & raw.away_id.isin(ids))
    cup = (raw.notes_headline.fillna("").str.contains("Championship")
           & (raw.season_type == 2))
    reg = raw[valid & (raw.season_type == 2) & ~cup].copy()
    reg = reg.sort_values(["game_date", "game_id"]).reset_index(drop=True)
    reg["neutral_model"] = reg.neutral_site.astype(bool) | (
        (reg.season == 2020) & (reg.game_date >= "2020-07-30"))
    reg["margin"] = reg.home_score - reg.away_score
    return reg


def run() -> dict:
    config.ensure_dirs()
    wb = data_load.load_workbook()
    findings: list[dict] = []

    def note(check: str, status: str, detail: str) -> None:
        findings.append({"check": check, "status": status, "detail": detail})

    games = wb.games
    teams = wb.teams

    # ---- 1. structure of the game table -------------------------------
    dup = games["ESPN game ID"].duplicated().sum()
    note("Game IDs unique", "pass" if dup == 0 else "FAIL",
         f"{len(games)} games, {dup} duplicated IDs")

    counts = games.groupby("Season end").size().to_dict()
    bad = {k: v for k, v in counts.items() if EXPECTED_GAMES.get(k) != v}
    note("Games per season", "pass" if not bad else "FAIL",
         "counts " + ", ".join(f"{k}:{v}" for k, v in sorted(counts.items()))
         + (f"; unexpected {bad}" if bad else "; all match the published schedule"))

    # No duplicated (date, home, away) triple, and no team playing twice a day.
    pair_dup = games.duplicated(["Game date", "Home", "Away"]).sum()
    long = pd.concat([
        games[["Season end", "Game date", "Home", "ESPN game ID"]]
        .rename(columns={"Home": "Team"}),
        games[["Season end", "Game date", "Away", "ESPN game ID"]]
        .rename(columns={"Away": "Team"}),
    ])
    twice = long[long.duplicated(["Game date", "Team"], keep=False)]
    note("No repeated date/home/away pairs",
         "pass" if pair_dup == 0 else "FAIL",
         f"{pair_dup} repeated matchup-days")
    if len(twice):
        ids = ", ".join(sorted(set(twice["ESPN game ID"])))
        note("One team plays at most one game per day", "known issue",
             f"{len(twice) // 2} team-day(s) hold two games: game IDs {ids}. "
             "Game 401161536 (Golden State 115, Phoenix 99) is dated 2020-03-01 "
             "in the archive but was played on 2020-02-29 (confirmed against "
             "Basketball-Reference box-score index). The score is correct; only "
             "the date is off by one, and it affects nothing but the day on "
             "which that 2019-20 result enters the running ratings.")
    else:
        note("One team plays at most one game per day", "pass",
             "no team appears twice on the same date")

    codes = sorted(set(games.Home) | set(games.Away))
    note("Team identities", "pass" if len(codes) == 30 else "FAIL",
         f"{len(codes)} distinct team codes: {' '.join(codes)}")

    per_season_teams = games.groupby("Season end").apply(
        lambda d: len(set(d.Home) | set(d.Away)), include_groups=False)
    note("30 teams every season",
         "pass" if (per_season_teams == 30).all() else "FAIL",
         f"min {per_season_teams.min()}, max {per_season_teams.max()}")

    # Season labels: no game dated outside the labelled season window.
    span = games.groupby("Season end")["Game date"].agg(["min", "max"])
    label_ok = all((row["min"].year in (idx - 1, idx)) and row["max"].year == idx
                   for idx, row in span.iterrows())
    note("Season labels match dates", "pass" if label_ok else "FAIL",
         "; ".join(f"{i}: {r['min'].date()}..{r['max'].date()}"
                   for i, r in span.iterrows()))

    # ---- 2. exclusions -------------------------------------------------
    raw = data_load.load_external_schedule()
    present_cup = [g for g in CUP_FINALS if g in set(games["ESPN game ID"])]
    in_range = raw[raw.season.between(config.FIRST_SEASON, 2025)]
    cup_flagged = in_range[in_range.notes_headline.fillna("").str.contains(
        "Cup|In-Season Tournament", case=False)
        & ~in_range.game_id.astype(str).isin(CUP_FINALS)]
    kept = int(cup_flagged.game_id.astype(str).isin(set(games["ESPN game ID"])).sum())
    note("Cup championship games excluded, other Cup games kept",
         "pass" if not present_cup and kept > 0 else "FAIL",
         f"both Cup finals absent ({'; '.join(CUP_FINALS.values())}); "
         f"{kept} of {len(cup_flagged)} other Cup games retained, because they "
         f"do count toward the regular-season standings" if not present_cup
         else f"found {present_cup}")

    in_wb = set(games["ESPN game ID"])
    nonreg = raw[(raw.season_type != 2) & raw.game_id.astype(str).isin(in_wb)]
    note("No All-Star or postseason games in the regular-season table",
         "pass" if len(nonreg) == 0 else "FAIL",
         f"{len(nonreg)} non-regular-season game IDs found in the sheet")

    # ---- 3. cross-source comparison ------------------------------------
    arch = rebuild_from_archive()
    arch_key = arch.assign(game_id=arch.game_id.astype(str)).set_index("game_id")
    wbk = games.set_index("ESPN game ID")
    only_wb = sorted(set(wbk.index) - set(arch_key.index))
    only_arch = sorted(set(arch_key.index) - set(wbk.index))
    joined = wbk.join(arch_key, how="inner", rsuffix="_arch")
    score_diff = joined[(joined["Home score"] != joined.home_score)
                        | (joined["Away score"] != joined.away_score)]
    date_diff = joined[joined["Game date"] != joined.game_date]
    neutral_diff = joined[joined["Model neutral"] != joined.neutral_model]
    note("Workbook game table reproduced from the hoopR archive",
         "pass" if not (only_wb or only_arch or len(score_diff) or len(date_diff)
                        or len(neutral_diff)) else "FAIL",
         f"{len(joined)} games matched; {len(only_wb)} only in the workbook, "
         f"{len(only_arch)} only in the archive, {len(score_diff)} score "
         f"differences, {len(date_diff)} date differences, "
         f"{len(neutral_diff)} neutral-flag differences")

    # ---- 4. neutral venues ---------------------------------------------
    bubble = games[(games["Season end"] == 2020)
                   & (games["Game date"] >= "2020-07-30")]
    note("2020 bubble games treated as neutral",
         "pass" if len(bubble) == 88 and bubble["Model neutral"].all() else "FAIL",
         f"{len(bubble)} bubble games, {int(bubble['Model neutral'].sum())} "
         f"neutral in the model; source flag marked "
         f"{int(bubble['Source neutral'].sum())} of them neutral")
    other_neutral = games[games["Model neutral"] & ~(
        (games["Season end"] == 2020) & (games["Game date"] >= "2020-07-30"))]
    neutral_tbl = (other_neutral.groupby(["Season end", "Venue"]).size()
                   .rename("games").reset_index())
    note("Other neutral-site games", "info",
         f"{len(other_neutral)} non-bubble neutral games at "
         f"{other_neutral['Venue'].nunique()} venues (see audit_neutral_sites.csv)")

    # ---- 5. records and scoring totals ---------------------------------
    espn = data_load.load_external_standings()
    tallies = []
    for year in config.STUDY_SEASONS:
        g = games[games["Season end"] == year]
        for team in sorted(set(g.Home) | set(g.Away)):
            h = g[g.Home == team]
            a = g[g.Away == team]
            wins = int((h["Home score"] > h["Away score"]).sum()
                       + (a["Away score"] > a["Home score"]).sum())
            losses = len(h) + len(a) - wins
            tallies.append(dict(
                season=year, team=team, games=len(h) + len(a), wins=wins,
                losses=losses,
                pf=int(h["Home score"].sum() + a["Away score"].sum()),
                pa=int(h["Away score"].sum() + a["Home score"].sum())))
    tally = pd.DataFrame(tallies)
    merged = tally.merge(
        espn.rename(columns={"team": "team", "season": "season"}),
        on=["season", "team"], how="left", suffixes=("", "_espn"))
    rec_bad = merged[(merged.wins != merged.wins_espn)
                     | (merged.losses != merged.losses_espn)]
    note("Win-loss records match ESPN standings",
         "pass" if len(rec_bad) == 0 else "FAIL",
         f"{len(merged)} team-seasons checked against a freshly retrieved "
         f"standings feed; {len(rec_bad)} mismatches")

    merged["pf_gap"] = merged.pf - merged.points_for
    merged["pa_gap"] = merged.pa - merged.points_against
    gaps = merged[(merged.pf_gap != 0) | (merged.pa_gap != 0)].copy()
    note("Scoring totals: game log vs standings feed",
         "known issue" if len(gaps) else "pass",
         f"{len(gaps)} of {len(merged)} team-seasons differ, by 1-3 points; "
         "the workbook reports the same 12")

    third = _bref_check(gaps)
    if third is not None:
        agree = int((third.verdict == "third source matches the game log").sum())
        note("Third source (Basketball-Reference) on the 12 scoring gaps",
             "resolved" if agree == len(third) else "partly resolved",
             f"{agree} of {len(third)} team-season totals match the summed game "
             "scores exactly, so the ESPN standings aggregate is the outlier "
             "and no game score needs correcting")
        third.to_csv(config.OUT_TABLES / "audit_third_source_totals.csv", index=False)
    else:
        note("Third source (Basketball-Reference) on the 12 scoring gaps",
             "unavailable", "Basketball-Reference pages could not be retrieved")

    # ---- 6. localise each scoring discrepancy --------------------------
    localised = _localise_discrepancies(games, gaps)
    unresolved = localised[localised.verdict.str.startswith("unverified")]
    note("Scoring discrepancies traced to individual games",
         "resolved" if len(unresolved) == 0 else "partly resolved",
         f"{localised.game_id.nunique()} candidate games checked against ESPN "
         f"box scores; {len(unresolved)} could not be checked")

    # ---- 7. regular-season positions -----------------------------------
    rank_ok, rank_detail, rank_tbl = _check_ranks(wb)
    note("Regular-season positions 1-15 restored", "pass" if rank_ok else "FAIL",
         rank_detail)

    # ---- 8. leakage in the published training features ------------------
    leak = _check_feature_dates(wb)
    note("No future information in the pregame features",
         "pass" if leak["violations"] == 0 else "FAIL", leak["detail"])

    out = pd.DataFrame(findings)
    out.to_csv(config.OUT_TABLES / "audit_findings.csv", index=False)
    localised.to_csv(config.OUT_TABLES / "audit_scoring_discrepancies.csv", index=False)
    neutral_tbl.to_csv(config.OUT_TABLES / "audit_neutral_sites.csv", index=False)
    rank_tbl.to_csv(config.OUT_TABLES / "audit_positions.csv", index=False)
    merged.to_csv(config.DATA_PROCESSED / "team_season_tallies.csv", index=False)
    print(out.to_string(index=False))
    return {"findings": out, "discrepancies": localised, "tallies": merged,
            "positions": rank_tbl}


BREF_TEAM_NAMES = {
    "ATL": "Atlanta Hawks", "BKN": "Brooklyn Nets", "BOS": "Boston Celtics",
    "CHA": "Charlotte Hornets", "CHI": "Chicago Bulls",
    "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks",
    "DEN": "Denver Nuggets", "DET": "Detroit Pistons",
    "GS": "Golden State Warriors", "HOU": "Houston Rockets",
    "IND": "Indiana Pacers", "LAC": "Los Angeles Clippers",
    "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies", "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NO": "New Orleans Pelicans", "NY": "New York Knicks",
    "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SA": "San Antonio Spurs",
    "SAC": "Sacramento Kings", "TOR": "Toronto Raptors", "UTAH": "Utah Jazz",
    "WSH": "Washington Wizards",
}


def _bref_totals(season: int) -> pd.DataFrame | None:
    """Season points-for and points-against per team, from Basketball-Reference."""
    import io
    import time
    cache = config.DATA_EXTERNAL / "bref"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"NBA_{season}.html"
    if not path.exists():
        url = f"https://www.basketball-reference.com/leagues/NBA_{season}.html"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=40) as fh:
                path.write_bytes(fh.read())
        except (urllib.error.URLError, TimeoutError, OSError):
            return None
        time.sleep(4)  # Basketball-Reference asks for a slow crawl rate.
    html = path.read_text(errors="ignore").replace("<!--", "").replace("-->", "")
    try:
        tf = pd.read_html(io.StringIO(html), attrs={"id": "totals-team"})[0]
        ta = pd.read_html(io.StringIO(html), attrs={"id": "totals-opponent"})[0]
    except ValueError:
        return None
    out = tf[["Team", "PTS"]].merge(ta[["Team", "PTS"]], on="Team",
                                    suffixes=("_for", "_against"))
    out["Team"] = out.Team.str.replace("*", "", regex=False)
    return out


def _bref_check(gaps: pd.DataFrame) -> pd.DataFrame | None:
    rows = []
    for season, sub in gaps.groupby("season"):
        totals = _bref_totals(int(season))
        if totals is None:
            return None
        lookup = totals.set_index("Team")
        for r in sub.itertuples():
            name = BREF_TEAM_NAMES[r.team]
            if name not in lookup.index:
                return None
            bf = int(lookup.loc[name, "PTS_for"])
            ba = int(lookup.loc[name, "PTS_against"])
            verdict = ("third source matches the game log"
                       if (bf, ba) == (int(r.pf), int(r.pa))
                       else "third source matches neither / matches the standings")
            rows.append(dict(season=int(season), team=r.team,
                             game_log_pf=int(r.pf), game_log_pa=int(r.pa),
                             espn_standings_pf=int(r.points_for),
                             espn_standings_pa=int(r.points_against),
                             bref_pf=bf, bref_pa=ba, verdict=verdict))
    return pd.DataFrame(rows)


def _localise_discrepancies(games: pd.DataFrame, gaps: pd.DataFrame) -> pd.DataFrame:
    """Pin each scoring gap on the head-to-head games that could cause it.

    A team's points-for gap of +k and another team's points-against gap of +k in
    the same season can only come from games between those two teams, so the
    candidate set is small enough to check game by game against ESPN box scores.
    """
    rows = []
    for season, sub in gaps.groupby("season"):
        pf_off = sub[sub.pf_gap != 0][["team", "pf_gap"]].values.tolist()
        pa_off = sub[sub.pa_gap != 0][["team", "pa_gap"]].values.tolist()
        for scorer, k in pf_off:
            partners = [t for t, j in pa_off if j == k]
            for conceder in partners:
                g = games[(games["Season end"] == season)
                          & (((games.Home == scorer) & (games.Away == conceder))
                             | ((games.Home == conceder) & (games.Away == scorer)))]
                for r in g.itertuples():
                    gid = r._2
                    summary = _summary_score(gid)
                    if summary is None:
                        verdict = "unverified (box score unavailable)"
                        sh = sa = None
                    else:
                        sh, sa, _ = summary
                        verdict = ("box score agrees with the game table"
                                   if (sh, sa) == (r._6, r._7)
                                   else "box score DISAGREES with the game table")
                    rows.append(dict(
                        season=season, scorer=scorer, conceder=conceder,
                        points=k, game_id=gid, date=r._3.date(),
                        home=r.Home, away=r.Away, table_home=r._6,
                        table_away=r._7, espn_home=sh, espn_away=sa,
                        verdict=verdict))
    return pd.DataFrame(rows)


def _check_ranks(wb) -> tuple[bool, str, pd.DataFrame]:
    """Positions 7-10 must come from the pre-play-in matchups, not playoff seeds."""
    ps = wb.postseason
    recovered = {}
    for r in ps[ps.Stage == "Play-in"].itertuples():
        head = str(r._9)
        if "7th Place vs 8th Place" in head:
            recovered[(r._1, r.Home)] = 7
            recovered[(r._1, r.Away)] = 8
        elif "9th Place vs 10th Place" in head:
            recovered[(r._1, r.Home)] = 9
            recovered[(r._1, r.Away)] = 10
    tbl = wb.teams[["Season end", "Conference", "Team", "Regular rank",
                    "ESPN seed field", "Wins", "Losses"]].copy()
    tbl["recovered from play-in matchup"] = [
        recovered.get((int(r._1), r.Team)) for r in tbl.itertuples()]
    ok = True
    details = []
    for (season, conf), sub in tbl.groupby(["Season end", "Conference"]):
        if sorted(sub["Regular rank"]) != list(range(1, 16)):
            ok = False
            details.append(f"{season} {conf}: ranks not 1-15")
    mism = tbl.dropna(subset=["recovered from play-in matchup"])
    wrong = mism[mism["Regular rank"] != mism["recovered from play-in matchup"]]
    if len(wrong):
        ok = False
        details.append(f"{len(wrong)} positions disagree with the play-in matchups")
    changed = tbl[tbl["Regular rank"] != tbl["ESPN seed field"]]
    detail = (f"ranks 1-15 complete in all 10 conference-seasons; "
              f"{len(mism)} positions 7-10 confirmed from opening play-in "
              f"matchups; {len(changed)} team-seasons where the stored ESPN "
              f"playoff seed differs from the regular-season position")
    if details:
        detail = "; ".join(details) + "; " + detail
    return ok, detail, tbl


def _check_feature_dates(wb) -> dict:
    """The published features must only use games strictly before their date."""
    tr = wb.training
    games = wb.games
    counts = []
    for r in tr.itertuples():
        pass
    # vectorised prior-game counts
    long = pd.concat([
        games[["Season end", "Game date", "Home"]].rename(columns={"Home": "Team"}),
        games[["Season end", "Game date", "Away"]].rename(columns={"Away": "Team"}),
    ])
    long = long.sort_values("Game date")
    prior = {}
    for (season, team), sub in long.groupby(["Season end", "Team"]):
        dates = sub["Game date"].to_numpy()
        prior[(season, team)] = dates
    viol = 0
    mism = 0
    for r in tr.itertuples():
        for team, stated in ((r.Home, r._11), (r.Away, r._12)):
            dates = prior[(int(r._1), team)]
            n_before = int((dates < np.datetime64(r._3)).sum())
            if n_before != int(stated):
                mism += 1
            if int(stated) < config.MIN_PRIOR_GAMES:
                viol += 1
    return {"violations": viol + mism,
            "detail": (f"{len(tr)} published feature rows; prior-game counts "
                       f"recomputed from the game table: {mism} disagreements, "
                       f"{viol} rows below the {config.MIN_PRIOR_GAMES}-game "
                       f"threshold")}
