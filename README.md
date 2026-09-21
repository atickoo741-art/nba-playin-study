# Does the NBA play-in tournament help the best team win the title?

A model-based counterfactual over the five seasons in which the play-in
tournament has existed: 2020-21 through 2024-25.

**Research question.** Holding regular-season standings and estimated team
strengths fixed, does the play-in tournament increase the probability that the
highest-rated team wins the championship?

**Answer, in one line.** Over the five seasons it changed that probability by
**+0.29 percentage points on average** - positive in two seasons, negative in
three, and larger than one percentage point only in 2024-25. The sign depends
on whether the play-in happens to promote a stronger or a weaker team into the
seed the best team has to beat, so the format neither systematically helps nor
systematically hurts the best team.

The full write-up, with equations, audit findings, validation and every
caveat, is in **[`reports/report.md`](reports/report.md)** (also as
`report.html` and `report.pdf`).

---

## Reproducing the study

```bash
./setup.sh                      # once: creates .venv and installs dependencies
.venv/bin/python run_all.py     # the whole study, about 20 seconds
```

Useful flags:

```bash
.venv/bin/python run_all.py --replicates 50000   # a faster, noisier run
.venv/bin/python run_all.py --skip-audit         # skip the network-backed audit
.venv/bin/python run_all.py --no-report          # tables and charts only
.venv/bin/python -m pytest tests -q              # the test suite
```

`run_all.py` writes every table, every chart and the report, and tees its
output to `logs/run_<timestamp>.log`. The audit step downloads from GitHub,
ESPN and Basketball-Reference on first run and caches everything under
`data/external/`, so later runs work offline.

Environment: Python 3.9+, numpy, pandas, scipy, openpyxl, matplotlib, markdown,
lxml, pytest. Minimums are in `requirements.txt`; the exact versions behind the
committed results are in `requirements-lock.txt`. PDF generation uses headless
Google Chrome if it is installed; without it the Markdown and HTML reports are
still produced.

---

## How the pieces fit together

```
NBA_PlayIn_Whiteboard_Data.xlsx
        |
        |  audit.py ........... checked against the hoopR archive, the ESPN
        |                       standings and box-score APIs, and
        |                       Basketball-Reference
        v
   9,519 regular-season games, 150 team-seasons
        |
        |  ratings.py .......... full-season SRS (frozen before the postseason)
        |                        and pregame SRS rebuilt date by date
        v
   7,048 training rows with no future information
        |
        |  model.py ............ P(A beats B) = sigmoid(beta*(R_A-R_B) + h*H)
        |                        fitted on the three prior seasons
        v
   beta ~ 0.113 per SRS point, h ~ 0.24 (home court is worth about two points)
        |
        +--> tournament.py ..... both formats, solved exactly: backward
        |                        recursion for series, enumeration over the six
        |                        play-in seed states per conference and the 36
        |                        combinations
        |
        +--> montecarlo.py ..... 500,000 tournaments per format per season,
        |                        simulated game by game with common random
        |                        numbers, as an independent check
        |
        +--> validation.py ..... held-out Brier score, log loss, calibration,
        |                        against a home-win-rate baseline
        |
        +--> sensitivity.py .... training window, alternative rating, Finals
                                 hosting rule, and both open data issues
```

## Project layout

| Path | What is in it |
| --- | --- |
| `run_all.py` | single-command reproduction |
| `setup.sh` | creates the virtual environment |
| `src/nbaplayin/` | all analysis code, one module per step |
| `tests/` | 43 tests: series edge cases, bracket structure, normalisation, qualification sums, reproducibility, simulation against exact |
| `data/raw/` | the original workbook, unchanged |
| `data/external/` | independently retrieved sources, cached |
| `data/processed/` | cleaned games, ratings, pregame features, team tallies |
| `outputs/tables/` | every result table as CSV, plus `results.json` |
| `outputs/figures/` | seven charts, PNG and SVG |
| `reports/` | the report in Markdown, HTML and PDF |
| `logs/` | one log per run |

## Key result tables

| File | Contents |
| --- | --- |
| `outputs/tables/page6_table.csv` | the five-row table for Page 6 of the handwritten work |
| `outputs/tables/season_summary.csv` | exact and simulated probabilities, counts, standard errors |
| `outputs/tables/exact_team_results.csv` | all 150 team-seasons under both formats |
| `outputs/tables/audit_findings.csv` | 18 audit checks and what each found |
| `outputs/tables/audit_scoring_discrepancies.csv` | the 12 disputed totals traced to individual games |
| `outputs/tables/worked_examples.csv` | every handwritten page recomputed from the raw games |
| `outputs/tables/validation.csv` | held-out predictive performance, every season and window |
| `outputs/tables/sensitivity_*.csv` | one file per sensitivity analysis |

## The handwritten pages

Pages 1-9 of the handwritten work demonstrate the mathematics by hand; the code
does the repetitive versions of the same calculations. `worked_examples.py`
recomputes every published figure on those pages from the raw game scores and
reports whether each agrees. **All of them do.** Section 15 of the report lists
the four labelling changes the pages need - what the numbers are called, not
what they are.

## What this study does not claim

It is a counterfactual inside a model. Standings, ratings and the game model
are held fixed, so changes in incentives, resting, injuries and roster
decisions are not represented, and the result is not the causal effect of the
policy. "Strongest" is itself an estimate: an alternative rating fitted to wins
and losses alone names a different strongest team in two of the five seasons
and reverses the sign of the effect in one of them. Five seasons is five
observations, and the Monte Carlo intervals describe simulation noise only.
