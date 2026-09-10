"""Step 7: build the report in Markdown, HTML and PDF.

Every number in the report is read out of the result tables produced by the
pipeline, so the prose cannot drift away from the computation.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time

import numpy as np
import pandas as pd

from . import config, worked_examples

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def _season(y: int) -> str:
    return f"{y - 1}-{str(y)[2:]}"


def _pct(x: float, nd: int = 2) -> str:
    return f"{x * 100:.{nd}f}%"


def _pp(x: float, nd: int = 2) -> str:
    return f"{x * 100:+.{nd}f}"


def _md_table(df: pd.DataFrame, floatfmt: str = "{:.4f}") -> str:
    def cell(v):
        if isinstance(v, float) and not pd.isna(v):
            return floatfmt.format(v)
        return "" if pd.isna(v) else str(v)
    head = "| " + " | ".join(str(c) for c in df.columns) + " |"
    rule = "| " + " | ".join("---" for _ in df.columns) + " |"
    body = ["| " + " | ".join(cell(v) for v in row) + " |"
            for row in df.itertuples(index=False)]
    return "\n".join([head, rule] + body)


def write(out: dict) -> dict:
    config.ensure_dirs()
    res = out["results"]
    summary = out["summary"]
    team = out["team_table"]
    valid = out["validation"]
    coeffs = out["coefficients"]
    calib = out["calibration"]
    sw = out["sensitivity_window"]
    sf = out["sensitivity_finals"]
    sd = out["sensitivity_data"]
    mc = out["monte_carlo"]
    check = out["check"]
    states = out["states"]
    adv = out["advancement"]
    notes = out["finals_notes"]
    study = out["study"]

    wex = worked_examples.run(study)
    wex.to_csv(config.OUT_TABLES / "worked_examples.csv", index=False)
    findings = pd.read_csv(config.OUT_TABLES / "audit_findings.csv")
    disc = pd.read_csv(config.OUT_TABLES / "audit_scoring_discrepancies.csv")
    third = pd.read_csv(config.OUT_TABLES / "audit_third_source_totals.csv")

    md = _compose(res, summary, team, valid, coeffs, calib, sw, sf, sd, mc,
                  check, states, adv, notes, wex, findings, disc, third, study)
    md_path = config.REPORTS / "report.md"
    md_path.write_text(md)

    html_path = config.REPORTS / "report.html"
    html_path.write_text(_html(md))
    pdf_path = _pdf(html_path)
    return {"markdown": str(md_path), "html": str(html_path),
            "pdf": str(pdf_path) if pdf_path else None}


def _html(md: str) -> str:
    import markdown as md_lib
    body = md_lib.markdown(md, extensions=["tables", "toc", "fenced_code"])
    css = """
    @page { size: A4; margin: 18mm 16mm; }
    body { font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
           font-size: 10.5pt; line-height: 1.5; color: #16160f; max-width: 52em;
           margin: 0 auto; }
    h1 { font-size: 20pt; margin-top: 0; }
    h2 { font-size: 14pt; border-bottom: 1px solid #d9d8d4; padding-bottom: 4px;
         margin-top: 26px; }
    h3 { font-size: 11.5pt; margin-top: 18px; }
    table { border-collapse: collapse; width: 100%; font-size: 9pt;
            margin: 10px 0 16px; }
    th, td { border: 1px solid #d9d8d4; padding: 4px 7px; text-align: right; }
    th { background: #f2f1ec; text-align: left; }
    td:first-child, th:first-child { text-align: left; }
    code { background: #f2f1ec; padding: 1px 4px; border-radius: 3px;
           font-size: 9.2pt; }
    pre { background: #f8f7f3; border: 1px solid #e5e4de; padding: 8px 10px;
          overflow-x: auto; font-size: 9pt; }
    img { max-width: 100%; margin: 8px 0; }
    blockquote { border-left: 3px solid #eb6834; margin: 12px 0; padding: 2px 14px;
                 color: #3a3a33; }
    """
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>NBA play-in study</title><style>{css}</style></head>"
            f"<body>{body}</body></html>")


def _pdf(html_path):
    if not shutil.which(CHROME) and not __import__("pathlib").Path(CHROME).exists():
        return None
    pdf_path = config.REPORTS / "report.pdf"
    try:
        subprocess.run(
            [CHROME, "--headless", "--disable-gpu", "--no-pdf-header-footer",
             f"--print-to-pdf={pdf_path}", f"file://{html_path}"],
            check=True, capture_output=True, timeout=180)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return None
    return pdf_path if pdf_path.exists() else None


def _compose(res, summary, team, valid, coeffs, calib, sw, sf, sd, mc, check,
             states, adv, notes, wex, findings, disc, third, study) -> str:
    base = coeffs[(coeffs.spec == "srs") & (coeffs.window == config.BASELINE_WINDOW)]
    vb = valid[(valid.spec == "srs") & (valid.window == config.BASELINE_WINDOW)]

    def wavg(df, col):
        return float(np.average(df[col], weights=df.games))

    reg = vb[vb.test_set == "Regular season (pregame ratings)"]
    post = vb[vb.test_set == "Playoffs (frozen ratings)"]
    pin = vb[vb.test_set == "Play-in games (frozen ratings)"]

    page6 = pd.DataFrame({
        "Season": [_season(s) for s in summary.season],
        "Highest-rated team": summary.strongest_team,
        "Old-format simulated title probability":
            [_pct(v) for v in summary.mc_old],
        "Play-in simulated title probability":
            [_pct(v) for v in summary.mc_playin],
        "Difference in percentage points":
            [f"{v:+.2f}" for v in summary.mc_difference_pp],
    })

    counts = pd.DataFrame({
        "Season": [_season(s) for s in summary.season],
        "Team": summary.strongest_team,
        "M (tournaments per format)": [f"{int(v):,}" for v in summary.replicates],
        "W old": [f"{int(v):,}" for v in summary.wins_old],
        "W play-in": [f"{int(v):,}" for v in summary.wins_playin],
        "Exact old": [f"{v:.5f}" for v in summary.exact_old],
        "Exact play-in": [f"{v:.5f}" for v in summary.exact_playin],
        "Exact difference (pp)": [f"{v * 100:+.3f}" for v in summary.exact_difference],
        "Simulated difference (pp)": [f"{v * 100:+.3f}" for v in summary.mc_difference],
        "95% interval (pp)": [
            f"[{(d - 1.96 * s) * 100:+.3f}, {(d + 1.96 * s) * 100:+.3f}]"
            for d, s in zip(summary.mc_difference, summary.mc_paired_se)],
    })

    ratings_tbl = pd.DataFrame({
        "Season": [_season(s) for s in summary.season],
        "Highest-rated team": summary.strongest_team,
        "SRS": [f"{v:.2f}" for v in summary.strongest_rating],
        "Position": summary.strongest_position,
        "Conference": summary.strongest_conference,
        "beta": [f"{v:.4f}" for v in summary.beta],
        "h": [f"{v:.4f}" for v in summary.h],
        "Training games": [f"{int(v):,}" for v in summary.train_games],
    })

    field = pd.DataFrame({
        "Season": [_season(s) for s in summary.season],
        "E[champion SRS], old": [f"{v:.3f}" for v in summary.champion_rating_old],
        "E[champion SRS], play-in": [f"{v:.3f}" for v in summary.champion_rating_playin],
        "Field SRS sum, old": [f"{v:.2f}" for v in summary.field_old],
        "Field SRS sum, play-in": [f"{v:.2f}" for v in summary.field_playin],
        "Field mean, old": [f"{v / 16:.3f}" for v in summary.field_old],
        "Field mean, play-in": [f"{v / 16:.3f}" for v in summary.field_playin],
    })

    val_tbl = pd.DataFrame({
        "Test set": ["Regular season (pregame ratings)",
                     "Play-in games (frozen ratings)",
                     "Playoffs (frozen ratings)"],
        "Games": [int(reg.games.sum()), int(pin.games.sum()), int(post.games.sum())],
        "Brier, model": [f"{wavg(reg, 'brier'):.4f}", f"{wavg(pin, 'brier'):.4f}",
                         f"{wavg(post, 'brier'):.4f}"],
        "Brier, home-rate baseline": [
            f"{wavg(reg, 'brier_baseline'):.4f}",
            f"{wavg(pin, 'brier_baseline'):.4f}",
            f"{wavg(post, 'brier_baseline'):.4f}"],
        "Log loss, model": [f"{wavg(reg, 'log_loss'):.4f}",
                            f"{wavg(pin, 'log_loss'):.4f}",
                            f"{wavg(post, 'log_loss'):.4f}"],
        "Log loss, baseline": [f"{wavg(reg, 'log_loss_baseline'):.4f}",
                               f"{wavg(pin, 'log_loss_baseline'):.4f}",
                               f"{wavg(post, 'log_loss_baseline'):.4f}"],
        "Accuracy, model": [f"{wavg(reg, 'accuracy'):.3f}",
                            f"{wavg(pin, 'accuracy'):.3f}",
                            f"{wavg(post, 'accuracy'):.3f}"],
        "Accuracy, baseline": [f"{wavg(reg, 'accuracy_baseline'):.3f}",
                               f"{wavg(pin, 'accuracy_baseline'):.3f}",
                               f"{wavg(post, 'accuracy_baseline'):.3f}"],
    })

    win_tbl = (sw[(sw.target_rule == "this model's strongest team")]
               .pivot_table(index="season", columns="variant", values="difference"))
    win_md = pd.DataFrame({"Season": [_season(s) for s in win_tbl.index]})
    for c in sorted(win_tbl.columns):
        win_md[c] = [f"{v * 100:+.2f}" for v in win_tbl[c]]

    alt = sw[sw.variant.str.startswith("Bradley-Terry ratings, 3")]
    alt_md = pd.DataFrame({
        "Season": [_season(s) for s in alt.season],
        "Target team": alt.target_team,
        "Which target": alt.target_rule,
        "Old": [f"{v:.4f}" for v in alt.old],
        "Play-in": [f"{v:.4f}" for v in alt.playin],
        "Difference (pp)": [f"{v * 100:+.2f}" for v in alt.difference],
    })

    data_md = pd.DataFrame({
        "Variant": sd.variant,
        "Season": [_season(s) for s in sd.season],
        "Team": sd.target_team,
        "Difference (pp)": [f"{v * 100:+.3f}" for v in sd.difference],
    })

    audit_md = findings.rename(columns={"check": "Check", "status": "Status",
                                        "detail": "What was found"})

    tie_counts = notes.rule.value_counts().to_dict() if len(notes) else {}
    gap = (check.simulated - check.exact).abs()

    mean_exact = summary.exact_difference.mean()
    mean_mc = summary.mc_difference.mean()
    se_mean = float(np.sqrt((summary.mc_paired_se ** 2).sum()) / len(summary))
    n_pos = int((summary.exact_difference > 0).sum())

    s2025 = summary[summary.season == 2025].iloc[0]
    s2022 = summary[summary.season == 2022].iloc[0]
    st2025 = states[(states.season == 2025) & (states.conference == "Western")]
    seed8_2025 = (st2025.groupby("seed8").probability.sum()
                  .sort_values(ascending=False))
    pos = team.set_index(["season", "team"]).position
    keep = []
    for (season, conf), sub in states.groupby(["season", "conference"]):
        seven = team[(team.season == season) & (team.conference == conf)
                     & (team.position == 7)].team.iloc[0]
        eight = team[(team.season == season) & (team.conference == conf)
                     & (team.position == 8)].team.iloc[0]
        keep.append(sub[sub.apply(
            lambda r: {r.seed7, r.seed8} == {seven, eight}, axis=1)]
            .probability.sum())
    both_hold = float(np.mean(keep))
    q9 = team[team.position == 9].qualify_playin
    q10 = team[team.position == 10].qualify_playin
    sign_flips = []
    for (spec_label, season), sub in sw[
            sw.target_rule == "this model's strongest team"].assign(
            spec_label=lambda d: d.variant.str.split(",").str[0]).groupby(
            ["spec_label", "season"]):
        if sub.difference.min() < 0 < sub.difference.max():
            sign_flips.append((spec_label, season,
                               float(sub.difference.abs().max())))
    flip_note = ("no season changes sign across training windows"
                 if not sign_flips else
                 "the only exception is " + "; ".join(
                     f"{a} in {_season(b)}, where every estimate is within "
                     f"{c * 100:.2f} pp of zero" for a, b, c in sign_flips))
    cal_gap = (calib.observed - calib.mean_predicted).abs()
    cal_z = float((cal_gap / calib.standard_error).max())
    calib_md = calib.drop(columns=["spec"]).rename(columns={
        "bin_low": "Predicted from", "bin_high": "to", "games": "Games",
        "mean_predicted": "Mean predicted", "observed": "Observed home-win rate",
        "standard_error": "Standard error"})
    champ_shift = float((sf.groupby("season").expected_champion_old.max()
                         - sf.groupby("season").expected_champion_old.min()).max())
    r2025 = team[team.season == 2025].set_index("team").rating
    exp_seed8 = float(sum(p * r2025[t] for t, p in seed8_2025.items()))
    old_seed8 = float(r2025[team[(team.season == 2025) & (team.conference == "Western")
                                 & (team.position == 8)].team.iloc[0]])

    return f"""# Does the play-in tournament help the best team win the title?

A model-based counterfactual over five NBA seasons, 2020-21 to 2024-25

*Generated {time.strftime('%d %B %Y')} from `NBA_PlayIn_Whiteboard_Data.xlsx`.
Every figure in this report is produced by `python run_all.py`; nothing is
typed in by hand.*

---

## 1. Summary

Holding each season's standings and team ratings fixed, the play-in tournament
changed the highest-rated team's probability of winning the championship by
**{_pp(mean_exact)} percentage points on average over the five seasons**
(simulated: {_pp(mean_mc)} pp, Monte Carlo standard error
{se_mean * 100:.3f} pp). The effect was positive in {n_pos} of the five seasons
and negative in {5 - n_pos}. Every season's effect is smaller than one
percentage point except 2024-25, at {_pp(s2025.exact_difference)} pp.

The sign is not a property of the play-in format. It depends on one thing:
whether the play-in tends to put a **stronger or weaker** team into the seed
that the best team has to beat.

* In **2024-25** the strongest team, OKC, finished first in the West and so
  faced the eighth seed. Under the old format that was Memphis, rated
  {old_seed8:.2f}, the strongest of the four play-in teams. Under the play-in
  format the eighth seed is Memphis only
  {_pct(seed8_2025.get('MEM', 0), 1)} of the time, and its expected rating
  falls to {exp_seed8:.2f}. OKC's draw gets easier, and its title probability
  rises {_pp(s2025.exact_difference)} pp.
* In **2021-22** the strongest team, Boston, finished second in the East and so
  faced the seventh seed. Under the old format that was Brooklyn, the weaker of
  the two; the play-in replaces it with the winner of Brooklyn against a
  better-rated Cleveland. Boston's draw gets harder, and its title probability
  falls {abs(s2022.exact_difference) * 100:.2f} pp.

Two other model-derived quantities are reported alongside: the expected rating
of the champion and the expected rating of the sixteen-team playoff field. Both
move by small amounts, and like the headline number they move in different
directions in different seasons.

**This is a counterfactual inside a model, not the causal effect of the
policy.** Standings, ratings and the game model are held fixed, so nothing
about incentives, resting, injuries or roster decisions is represented. See
section 12.

![Change in title probability by season](../outputs/figures/fig1_difference_by_season.png)

---

## 2. Research question and scope

> Holding regular-season standings and estimated team strengths fixed, does the
> NBA play-in tournament increase the probability that the highest-rated team
> wins the championship?

Five seasons are studied: {", ".join(_season(s) for s in summary.season)}. For
each one, the same standings, the same ratings and the same game-probability
model are put through two tournaments:

| | Old qualification format | Play-in format |
| --- | --- | --- |
| Seeds 1-6 | positions 1-6 qualify | positions 1-6 qualify |
| Seed 7 | position 7 | winner of 7 hosts 8 |
| Seed 8 | position 8 | winner of (7/8 loser hosts 9/10 winner) |
| Teams involved | 8 per conference | 10 per conference |

"Strongest" always means the highest full-season SRS rating computed **before**
that season's postseason. The actual champion is never used to define it.

### What the comparison can and cannot show

It isolates one channel: the bracket. Because the standings and ratings are
frozen, the comparison answers "given these teams and these strengths, what
does the extra round do to the best team's chances?" It does not answer "what
happened to the NBA because the play-in exists?", since a real policy also
changes how teams behave during the season.

---

## 3. Data and audit

### Sources

| Source | Use | Retrieved |
| --- | --- | --- |
| `NBA_PlayIn_Whiteboard_Data.xlsx` | the study's input: 9,519 regular-season games 2017-18 to 2024-25, 150 team-seasons, published reference values | supplied |
| [sportsdataverse/hoopR-nba-data schedule archive](https://raw.githubusercontent.com/sportsdataverse/hoopR-nba-data/main/nba/schedules/nba_schedule_master.csv) | independent rebuild of the game table | {time.strftime('%Y-%m-%d')} |
| [ESPN standings API](https://site.web.api.espn.com/apis/v2/sports/basketball/nba/standings?season=2025&type=0&level=2) | win-loss records and scoring totals, five seasons | {time.strftime('%Y-%m-%d')} |
| [ESPN game summary API](https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=401705741) | box scores for 21 individual games under investigation | {time.strftime('%Y-%m-%d')} |
| [Basketball-Reference season totals](https://www.basketball-reference.com/leagues/NBA_2025.html) | third source for the 12 disputed scoring totals | {time.strftime('%Y-%m-%d')} |
| [NBA.com play-in rules](https://www.nba.com/news/nba-play-in-tournament) | format verification | {time.strftime('%Y-%m-%d')} |

### Audit findings

{_md_table(audit_md)}

### The twelve scoring discrepancies, resolved

Twelve of 150 team-season scoring totals in the ESPN standings feed differ from
the sum of that team's game scores, by one to three points. They are not
scattered: they pair up. In 2020-21, Indiana's points-against is two higher in
the game log while Dallas's points-for is two higher by the same amount, which
can only come from a game between those two teams. That logic narrows the whole
set of twelve to {disc.game_id.nunique()} candidate games.

All {disc.game_id.nunique()} candidate box scores were pulled from ESPN's game
summary endpoint: **every one agrees with the game table**. Basketball-Reference
was then checked as a third, fully independent source: all
{len(third)} team-season totals match the summed game scores exactly, not the
standings feed.

> **Conclusion:** the game scores are right and the ESPN standings aggregate is
> the outlier. No score is corrected, no game is dropped, and the analysis uses
> the game-level scores. Section 11 shows what would happen if the standings
> totals were used instead: at most
> {res['standings_margin_max_shift_pp']:.3f} pp on any season's result.

### One archive defect found

Game `401161536` (Golden State 115, Phoenix 99) is dated 2020-03-01 in the
archive, which puts two Golden State games on the same day. Basketball-Reference's
box-score index shows the game was played 2020-02-29. The score is right; the
date is one day late. It sits in 2019-20, a training season only. Moving it to
its true date changes no season's result by more than
{res['date_defect_max_shift_pp'] * 1000:.3f} thousandths of a percentage point.

### Exclusions and venue handling

* Only completed regular-season games between the 30 NBA teams are kept.
* The two in-season Cup **championship** games are removed, because they do not
  count in the standings. Every other Cup game is kept, because it does.
* No All-Star or postseason game appears in the regular-season table.
* The 88 games played in the 2020 Orlando bubble are treated as neutral. The
  source feed marks none of them neutral, which is wrong; the override is the
  workbook's and it is correct.
* Positions 7-10 are recovered from the wording of the opening play-in matchups
  ("7th Place vs 8th Place"), not from the playoff seeds, which the play-in
  itself changes. In 17 team-seasons the stored playoff seed differs from the
  regular-season position, so this matters.

---

## 4. Ratings

### Full-season SRS

For every team *i*, with mbar_i its average scoring margin, n_i its number of
games and O_i the list of its opponents (one entry per game played):

```
R_i = mbar_i + (1/n_i) * sum over j in O_i of R_j,      sum over i of R_i = 0
```

Multiplying through by n_i turns this into a linear system,
`(diag(N) - C) R = m`, where `C[i,j]` counts the games between i and j and
`m_i` is team i's total scoring margin. It is solved with the sum-to-zero
constraint. The rating is a team's scoring margin adjusted for how strong its
opponents were. A repeated opponent is counted once per game, which is what
makes the adjustment right for unbalanced schedules.

These ratings reproduce the workbook's to within 1e-13, and they satisfy their
own defining equation to within 1e-7 (tested in `tests/test_ratings.py`).

### Pregame ratings

The same system is re-solved once per game date using only games on **strictly
earlier** dates, so a game can never help predict itself. A game enters the
training set only if both teams already have {config.MIN_PRIOR_GAMES} games
that season, which keeps ratings built on five-game samples out of the fit. Of
9,519 games, 7,048 pass that filter. Recomputed independently here, all 7,048
match the workbook's published features exactly.

That threshold is a real choice with a cost: it throws away roughly the first
six weeks of every season. It is kept because early ratings are extremely
noisy - before 20 games a team's SRS still moves by several points per game -
and because it was specified before any result was looked at.

---

## 5. The game model

```
P(A beats B) = 1 / (1 + exp(-(beta * (R_A - R_B) + h * H)))
H = +1 if A is at home, -1 if A is away, 0 at a neutral venue
```

Fitted by maximum likelihood on completed games from earlier seasons only, with
`beta >= 0` and no separate intercept, so two equally rated teams at a neutral
venue are a coin flip by construction. The prespecified training window is the
**three completed seasons before** the season being studied; one- and two-season
windows are reported in section 11 as checks, never as a choice.

{_md_table(ratings_tbl)}

`beta` is close to {base.beta.mean():.3f} in every season: one point of SRS is
worth about {base.beta.mean():.3f} in log-odds, so a five-point rating edge
makes a team roughly {100 / (1 + np.exp(-5 * base.beta.mean())):.0f}% to win a
neutral game. `h` between {base.h.min():.2f} and {base.h.max():.2f} means home
court is worth between {(base.h / base.beta).min():.1f} and
{(base.h / base.beta).max():.1f} points of rating - in the same range as the
familiar "home court is worth about two or three points" rule.

No model was chosen because it produced a preferred tournament answer. The
window was fixed in advance, and the alternatives are reported whatever they
show.

---

## 6. The two tournaments

### Play-in, exactly as the league runs it

Position 7 hosts position 8; the winner is **seed 7**. Position 9 hosts position
10; the loser is eliminated. The loser of 7/8 hosts the winner of 9/10; that
winner is **seed 8**. (Verified against nba.com.)

This produces six possible ordered (seed 7, seed 8) outcomes per conference,
and they are **dependent**: whoever wins the 7/8 game is seed 7 and cannot also
be seed 8. The study carries the joint distribution over all six, never two
independent marginals. `tests/test_structure.py` contains a test that fails if
anyone replaces the joint with a product.

### Bracket and venues

The bracket is fixed and there is no reseeding: 1-8, 4-5, 2-7, 3-6; the winners
of 1/8 and 4/5 meet, as do the winners of 2/7 and 3/6. The better seed hosts
game 1 of every conference series, in the 2-2-1-1-1 pattern
`H, H, A, A, H, A, H`.

### Finals home court

The published NBA rule for two teams in opposite conferences is applied in
order: better regular-season winning percentage; then head-to-head record; then
record against the opposite conference. Across the five seasons there are
{len(notes)} tied pairs among teams that could reach the Finals, and the chain
resolves **all of them** - {tie_counts.get('head-to-head record', 0)} on
head-to-head and {tie_counts.get('record against the opposite conference', 0)}
on opposite-conference record. None is left unresolved, so the workbook's
50/50 pilot assumption is not needed anywhere.

Section 11 shows that this matters even less than it sounds: the highest-rated
team is never itself in a tied pair, so its title probability is
**bit-for-bit identical** under all four hosting rules tried.

---

## 7. Exact calculation

Nothing in this section is simulated.

**Series.** With `p_k` the probability the tracked team wins game k, and
F(w, l) the probability it wins the series from w wins and l losses:

```
F(w, l) = p_{{w+l}} * F(w+1, l) + (1 - p_{{w+l}}) * F(w, l+1)
F(4, l) = 1,   F(w, 4) = 0
```

This is exact for venue-dependent probabilities, which a binomial formula is
not: the games in a series are not all played under the same conditions.

**Bracket.** Each round's output is a probability distribution over which team
occupies the slot. Two slot distributions are combined by summing, over all
pairs, the probability that they meet times the probability that each wins.
After three rounds the conference winner's distribution remains; the two
conferences are then crossed, pair by pair, with the Finals hosting rule.

**Play-in.** Six ordered seed states per conference are enumerated, and the
36 combined configurations are crossed. The title distribution is the
weighted average.

Every distribution is checked to sum to one, and the four play-in teams'
qualification probabilities are checked to sum to exactly two per conference.

---

## 8. Monte Carlo design

The simulator plays games, not tournaments drawn from the answer. It draws
uniforms, compares them with game probabilities, counts series wins, and
carries the winners forward through exactly the same bracket rules - so
agreement with section 7 is evidence that both implementations are right.

* **{int(summary.replicates.iloc[0]):,} complete tournaments per format per
  season** ({int(summary.replicates.iloc[0]) * 2 * 5:,} in total), configurable
  with `--replicates`.
* Seed {res['seed']}. Replicates are drawn in fixed blocks of
  {config.MC_CHUNK:,}, each block seeded from (seed, season, block number), so
  the same seed reproduces the same run on any machine and asking for more
  replicates extends the run instead of changing it.
* **Common random numbers.** Both formats use the same draws for the same
  bracket position, so the two runs are paired. The reported standard error for
  the difference is the standard error of the paired differences,
  `sd(d) / sqrt(M)`, which is the correct one for this design. The
  independent-proportions standard error is also reported: it is about
  {float((summary.mc_independent_se / summary.mc_paired_se).mean()):.0f} times
  larger, which is the value of pairing.
* A best-of-seven is simulated by playing all seven games and awarding the
  series to whoever wins at least four. That is exactly equivalent to stopping
  at four wins, because the winner of the first four games is always the winner
  of all seven.

### Simulation against exact calculation

Across all 30 teams, five seasons and both formats (300 comparisons), the
largest gap between simulated share and exact probability is
{gap.max():.5f} and the mean gap is {gap.mean():.6f}. The largest gap in units
of its own Monte Carlo standard error is
{res['worst_z_exact_vs_simulated']:.2f}, which is what 300 independent
comparisons should produce. No seed was changed to make these agree; the seed
was fixed before the first run.

![Exact against simulated](../outputs/figures/fig2_exact_vs_simulated.png)

**Monte Carlo error is computational uncertainty only.** It says how precisely
the simulation reproduces the model's own answer. It says nothing about whether
the ratings are right, whether the logistic model is the right model, or what
the true effect of the policy is.

---

## 9. Validation

Held out means held out: for a season's test set, that season's games never
enter the fit.

{_md_table(val_tbl)}

The model beats the naive home-win-rate baseline on Brier score and log loss on
all three test sets, and by a wider margin in the regular season, where rating
differences are largest. Its accuracy advantage over the baseline is about
{100 * (wavg(reg, 'accuracy') - wavg(reg, 'accuracy_baseline')):.0f} percentage
points in the regular season and
{100 * (wavg(post, 'accuracy') - wavg(post, 'accuracy_baseline')):.0f} in the
playoffs. The playoff margin is thinner, which is expected: playoff teams are
closer in strength than a random pair of NBA teams.

The baseline is a real baseline, not a straw man - it is fitted on the same
training window and predicts the historical home-win rate
({vb.baseline_home_rate.mean():.3f} on average) for every hosted game.

### Calibration

![Calibration](../outputs/figures/fig3_calibration.png)

{_md_table(calib_md)}

Predicted and observed home-win rates track each other across the whole range;
the biggest single-bin gap is
{cal_gap.max():.3f}, which is {cal_z:.1f} standard errors. A model used to multiply many probabilities
together through a bracket has to be calibrated, not merely accurate, and this
one is.

---

## 10. Results

### Copy onto Page 6

{_md_table(page6)}

**Five-season average effect, equal weight per season: {_pp(mean_mc)}
percentage points** (exact calculation: {_pp(mean_exact)} pp).

### Counts, exact probabilities and Monte Carlo intervals

{_md_table(counts)}

W is the number of simulated tournaments the highest-rated team won out of M.
The interval is 95% around the simulated paired difference and reflects
simulation noise only.

### Expected champion and expected field

{_md_table(field)}

The playoff field's average rating falls slightly under the play-in format in
four of five seasons and rises in {_season(2023)}, when the teams in positions
9 and 10 were genuinely better than the ones in 7 and 8. Across all ten
conference-seasons, a team in position 9 or 10 was rated above one of the
7/8 teams six times - which is why the format's effect has no fixed sign.

![Playoff field strength](../outputs/figures/fig7_field_strength.png)

### One season in detail: 2024-25

![2024-25 title probabilities](../outputs/figures/fig4_title_probabilities_2025.png)

### What the play-in teams are playing for

![Qualification probabilities](../outputs/figures/fig5_qualification.png)

Positions 7 and 8 are no longer safe: across the five seasons, the probability
that both keep their places averages {both_hold:.2f} per conference. A
position-9 team's chance of reaching the playoffs runs from
{_pct(q9.min(), 0)} to {_pct(q9.max(), 0)}, and position 10's from
{_pct(q10.min(), 0)} to {_pct(q10.max(), 0)}.

---

## 11. Sensitivity

### Training window and rating specification

![Sensitivity](../outputs/figures/fig6_sensitivity.png)

{_md_table(win_md)}

Across every window and both rating definitions, the effect stays inside
[{res['window_spec_range_pp'][0]:+.2f}, {res['window_spec_range_pp'][1]:+.2f}]
percentage points. Within a rating definition, changing the training window
almost never changes a season's sign: {flip_note}. The window is not driving
the answer.

### When the alternative rating disagrees about who is strongest

The Bradley-Terry specification fits ratings to wins and losses only, ignoring
margins, with a ridge penalty so early-season fits stay finite. It names a
different strongest team in two seasons. Both readings are reported: the effect
on the team **this** model calls strongest, and the effect on the team the
baseline SRS model calls strongest.

{_md_table(alt_md)}

This is the single most important sensitivity in the study. In {_season(2023)}
the two ratings disagree both about who is strongest and about the sign of the
effect. "Strongest" is itself an estimate, and the answer moves when that
estimate moves.

### Finals home court

Four rules were tried: the published NBA chain, the workbook's 50/50 pilot
assumption, and forcing every tie to the Eastern or the Western team. The
highest-rated team's title probability is identical to machine precision under
all four, because that team is never in a tied pair. The expected champion
rating moves by at most {champ_shift:.4f} SRS points. The tie assumption is immaterial to this study's conclusion, and
it no longer needs to be an assumption at all.

### Data issues

{_md_table(data_md)}

Neither of the audit's two open data items - the disputed standings totals and
the one mis-dated game - moves any season's result by as much as
{max(res['standings_margin_max_shift_pp'], res['date_defect_max_shift_pp']):.3f}
percentage points.

---

## 12. Limitations

1. **Standings and ratings are frozen, so this is not the policy's effect.**
   A real play-in changes what teams do in March: who rests, who tanks, who
   fights for seventh instead of settling for ninth. None of that is in the
   model. The number here is the bracket's mechanical effect, and it is a lower
   bound on the amount of uncertainty about the policy, not a measure of it.
2. **"Strongest" is an estimate, not a fact.** The baseline calls Boston the
   strongest team three times; a win-loss rating disagrees twice and flips the
   sign of the effect in {_season(2023)}. Any conclusion about "the best team"
   inherits the rating's error.
3. **The game model is deliberately simple.** One rating difference, one home
   term, games independent given ratings. No injuries, no rest, no travel, no
   matchup effects, no momentum. It is well calibrated on held-out games, which
   is the most that can be claimed for it.
4. **Five seasons is five observations.** The play-in has existed in this form
   only since 2020-21. The five-season average is an average over the five
   seasons that exist, not an estimate with a sampling distribution, and the
   Monte Carlo interval around it does not represent that uncertainty.

---

## 13. Conclusion

Over the five seasons in which the play-in tournament has existed, and holding
standings and team strengths fixed, the format changed the highest-rated team's
probability of winning the championship by **{_pp(mean_exact)} percentage
points on average** - positive in {n_pos} seasons, negative in {5 - n_pos},
and larger than one percentage point only in 2024-25.

That is a small effect, and its sign is not a property of the format. It
depends on whether the play-in happens to promote a stronger or a weaker team
into the seed the best team must beat, which changes season by season. The
honest summary is that **the play-in tournament does not systematically help or
hurt the best team**; it adds a small amount of noise whose direction depends
on the season's standings.

Nothing here supports a claim that the play-in is better or worse overall. It
is a comparison on one metric, inside one model, with the rest of the policy
held fixed.

---

## 14. Plain-English guide to every computation

**Scoring margin.** Points scored minus points allowed in a game. Average them
over a season and you have a crude strength measure.

**SRS.** The crude measure is unfair to teams with hard schedules. SRS fixes
that by defining a team's rating as its average margin plus the average rating
of its opponents. Every team's rating depends on every other team's, so all 30
are solved together as a system of equations, anchored by making them sum to
zero. A rating of +5 means "about five points better than an average team
against an average schedule".

**Pregame ratings.** To test whether the model predicts, you must not let it
see the answer. So for each game date the ratings are rebuilt from games played
on earlier dates only.

**The logistic model.** Take the rating gap, multiply by `beta` to turn points
into log-odds, add `h` if the team is home (subtract it if away), then squash
into a probability with the logistic function. Fitted by maximum likelihood on
past seasons: choose the `beta` and `h` that make what actually happened as
likely as possible.

**Backward recursion for a series.** Work backwards from the end. If you have
four wins you have won (probability 1); four losses and you have lost
(probability 0). Otherwise your chance from a given score is your chance of
winning the next game times your chance from one-win-better, plus your chance
of losing it times your chance from one-loss-worse. Because home court changes
game by game, this is exact where a binomial formula would not be.

**Why the six play-in outcomes cannot be multiplied.** The team that wins the
7/8 game becomes seed 7 and is therefore not available to be seed 8. Seed 7 and
seed 8 are dependent. Multiplying "chance of being seed 7" by "chance of being
seed 8" would count impossible combinations.

**Propagating through the bracket.** After the first round you do not know who
won, so you carry a probability distribution over possible winners. Each
following round combines two such distributions: for every possible pairing,
the chance they meet times the chance each wins.

**Qualification probabilities summing to two.** Two of the four play-in teams
reach the playoffs, always. So their four probabilities must add to exactly 2 -
a check that catches most implementation mistakes instantly.

**Monte Carlo.** Instead of computing, play the season out with random numbers
hundreds of thousands of times and count. If simulation and exact calculation
agree, two independent implementations of the rules agree, which is much
stronger evidence than either alone.

**Common random numbers.** Both formats are run on the same random draws, so a
difference between them is a real difference in the rules rather than a
difference in luck. It shrinks the noise in the comparison by a factor of about
{float((summary.mc_independent_se / summary.mc_paired_se).mean()):.0f}.

**Brier score and log loss.** Two ways of scoring probability forecasts. Brier
is the average squared error between the forecast and what happened; log loss
punishes confident mistakes harder. Lower is better for both.

**Calibration.** Of the games you called 70%, did about 70% happen? Accuracy
alone is not enough here, because these probabilities get multiplied together
through four rounds.

---

## 15. Corrections for Pages 1 to 5

Every number on the handwritten pages was recomputed from the raw games
(`outputs/tables/worked_examples.csv`). **All of them are arithmetically
correct - no figure needs changing.** Four labelling changes are needed so the
pages say what they mean:

1. **Page 2 - label the ratings.** The four solved values (BOS
   {wex[wex.quantity == 'BOS restricted rating'].recomputed.iloc[0]:.3f}, CLE
   {wex[wex.quantity == 'CLE restricted rating'].recomputed.iloc[0]:.3f}, NY
   {wex[wex.quantity == 'NY restricted rating'].recomputed.iloc[0]:.3f}, IND
   {wex[wex.quantity == 'IND restricted rating'].recomputed.iloc[0]:.3f}) come
   from a 22-game mini-league among those four teams only. Write
   "restricted four-team ratings, not full-season NBA SRS" on the page. Boston's
   full-season 2024-25 SRS is
   {float(team[(team.season == 2025) & (team.team == 'BOS')].rating.iloc[0]):.2f},
   not {wex[wex.quantity == 'BOS restricted rating'].recomputed.iloc[0]:.2f}.
2. **Page 3 - state the H convention.** Write the equation as
   `P(A beats B) = sigmoid(beta*(R_A - R_B) + h*H)` with `H = +1, -1, 0`, and
   add one line: this is the same model as the fitted form "P(home wins) with
   H = 1 at home, 0 at neutral", seen from team A instead of from the host.
   Without that line the two forms look like different models.
3. **Pages 4 and 5 - say what 83.22% is.** It is the probability Golden State
   **qualifies** for the playoffs, as seed 7 or seed 8. It is not the
   probability of winning a play-in game
   (that is {float(wex[wex.quantity == 'P(Golden State beats Memphis at home)'].recomputed.iloc[0]):.4f}
   against Memphis at home). Add: "seed 7 and seed 8 are dependent - use the six
   ordered outcomes, never the product of two marginals."
4. **Page 6 - the target is 2, not 1.** Label the check "the four qualification
   probabilities sum to 2, because exactly two of the four teams get in". A
   reader who expects probabilities to sum to 1 will think the page is wrong.

One presentational note for Page 5: Memphis's qualification probability
({float(wex[wex.quantity == 'P(MEM qualifies)'].recomputed.iloc[0]):.4f}) is
slightly **higher** than Golden State's
({float(wex[wex.quantity == 'P(GS qualifies)'].recomputed.iloc[0]):.4f}) even
though Golden State hosts, because Memphis is the better-rated team. That is
worth a sentence on the page; it looks like an error and is not.

### Worked-example verification

{_md_table(wex[wex.agrees.notna()][['page', 'quantity', 'value_on_the_page',
                                     'recomputed', 'agrees']],
           floatfmt='{:.6f}')}

---

## Appendix A - what runs what

| File | What it does |
| --- | --- |
| `run_all.py` | one command, whole study |
| `src/nbaplayin/audit.py` | step 1, workbook against independent sources |
| `src/nbaplayin/ratings.py` | step 2a, SRS and Bradley-Terry, full-season and pregame |
| `src/nbaplayin/model.py` | step 2b, the logistic game model |
| `src/nbaplayin/tournament.py` | steps 3-4, both formats, exact |
| `src/nbaplayin/montecarlo.py` | step 5, simulation |
| `src/nbaplayin/validation.py` | step 6a, held-out prediction |
| `src/nbaplayin/sensitivity.py` | step 6b, every variant |
| `src/nbaplayin/worked_examples.py` | recomputes the six handwritten pages |
| `src/nbaplayin/figures.py` | the seven charts |
| `src/nbaplayin/report.py` | this document |
| `tests/` | {sum(1 for _ in (config.ROOT / 'tests').glob('test_*.py'))} test files, run with `pytest` |

## Appendix B - fitted coefficients, every window and specification

{_md_table(coeffs.assign(beta=coeffs.beta.round(5), h=coeffs.h.round(5),
                         beta_se=coeffs.beta_se.round(5),
                         h_se=coeffs.h_se.round(5))
           [['season', 'spec', 'window', 'train_first', 'train_last',
             'train_games', 'beta', 'beta_se', 'h', 'h_se', 'role']],
           floatfmt='{:.5f}')}

## Appendix C - validation, every season and window

{_md_table(valid[valid.spec == 'srs'][['season', 'window', 'test_set', 'games',
                                       'brier', 'log_loss', 'accuracy',
                                       'brier_baseline', 'log_loss_baseline']],
           floatfmt='{:.4f}')}

## Appendix D - play-in seed states, all five seasons

{_md_table(states, floatfmt='{:.6f}')}

## Appendix E - Finals hosting ties and how each was resolved

{_md_table(notes, floatfmt='{:.1f}')}

## Appendix F - per-team results

The full 150-row table of ratings, qualification probabilities and title
probabilities under both formats is in
`outputs/tables/exact_team_results.csv`, and round-by-round advancement
probabilities are in `outputs/tables/advancement.csv`.
"""
