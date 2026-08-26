"""Steps 3 and 4: the two tournament formats and their exact probabilities.

Everything here is deterministic. Given fixed ratings, fixed regular-season
positions and a fitted game model, the probability of every outcome is computed
by enumeration and backward recursion, with no simulation.

Formats
-------
old      the top eight teams in each conference qualify directly; seeds equal
         regular-season positions 1-8.
play-in  positions 1-6 qualify directly. Position 7 hosts position 8 and the
         winner is seed 7. Position 9 hosts position 10 and the loser is out.
         The 7/8 loser hosts the 9/10 winner and the winner is seed 8.

The joint distribution of (seed 7, seed 8) has six outcomes per conference and
is carried around as a whole, never as two independent marginals.
"""
from __future__ import annotations

import functools
import itertools
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.special import expit

from . import config

HOME, AWAY, NEUTRAL = 1, -1, 0


@dataclass
class SeasonModel:
    """Everything needed to play one season out under either format."""

    season: int
    codes: list[str]                     # team code by index
    ratings: np.ndarray                  # rating by index, frozen pre-postseason
    beta: float
    h: float
    conference: dict[int, str]           # team index -> conference
    rank: dict[int, int]                 # team index -> regular-season position
    wins: dict[int, int]
    games_played: dict[int, int]
    order: dict[str, list[int]] = field(init=False)
    p_table: np.ndarray = field(init=False)      # [venue, a, b]
    series_table: np.ndarray = field(init=False)  # [host_is_a, a, b]
    finals_host: dict[tuple[int, int], float] = field(init=False)
    finals_notes: list[dict] = field(init=False)
    host_matrix: np.ndarray = field(init=False)
    head_to_head: dict = field(default_factory=dict)
    vs_other_conf: dict = field(default_factory=dict)
    # "nba" applies the published opposite-conference tie-break chain;
    # "fifty_fifty" reproduces the workbook's pilot assumption; "east" and
    # "west" force every unresolved tie one way for the sensitivity check.
    finals_tiebreak: str = "nba"

    def __post_init__(self) -> None:
        self.order = {
            c: sorted([t for t in self.rank if self.conference[t] == c],
                      key=lambda t: self.rank[t])
            for c in config.CONFERENCES
        }
        diff = self.ratings[:, None] - self.ratings[None, :]
        self.p_table = np.stack([
            expit(self.beta * diff + self.h * HOME),
            expit(self.beta * diff + self.h * AWAY),
            expit(self.beta * diff + self.h * NEUTRAL),
        ])
        self.series_table = np.stack([self._series_matrix(True),
                                      self._series_matrix(False)])
        self.finals_host, self.finals_notes = self._finals_hosting()
        n = len(self.codes)
        self.host_matrix = np.full((n, n), 0.5)
        for (a, b), w in self.finals_host.items():
            self.host_matrix[a, b] = w

    # -- single games and series ---------------------------------------
    def p_game(self, a: int, b: int, venue: int) -> float:
        """Probability that a beats b. venue is +1 a home, -1 a away, 0 neutral."""
        return float(self.p_table[{HOME: 0, AWAY: 1, NEUTRAL: 2}[venue], a, b])

    def _series_matrix(self, a_hosts: bool) -> np.ndarray:
        """Exact best-of-seven win probability for every ordered pair."""
        pattern = [HOME if at_home else AWAY
                   for at_home in config.SERIES_HOME_PATTERN]
        if not a_hosts:
            pattern = [-v for v in pattern]
        ps = [self.p_table[0 if v == HOME else 1] for v in pattern]
        return series_probability(ps)

    def p_series(self, a: int, b: int, a_hosts: bool) -> float:
        return float(self.series_table[0 if a_hosts else 1, a, b])

    # -- Finals home court ---------------------------------------------
    def _finals_hosting(self) -> tuple[dict, list]:
        """Resolve who hosts game 1 of the Finals for every cross-conference pair.

        NBA rule for two teams in opposite conferences: better regular-season
        winning percentage; if equal, head-to-head record; if still equal,
        record against the opposite conference. A pair the chain cannot resolve
        keeps a 0.5 weight and is reported.
        """
        host: dict[tuple[int, int], float] = {}
        notes: list[dict] = []
        east, west = self.order["Eastern"], self.order["Western"]
        for a in east:
            for b in west:
                pa = self.wins[a] / self.games_played[a]
                pb = self.wins[b] / self.games_played[b]
                if pa != pb:
                    weight = 1.0 if pa > pb else 0.0
                    rule = "regular-season winning percentage"
                else:
                    weight, rule = self._tiebreak(a, b)
                host[(a, b)] = weight
                host[(b, a)] = 1.0 - weight
                # Only pairs that can actually reach the Finals are reported.
                if pa == pb and self.rank[a] <= 10 and self.rank[b] <= 10:
                    notes.append(dict(season=self.season, east=self.codes[a],
                                      west=self.codes[b], rule=rule,
                                      east_hosts=weight))
        return host, notes

    def _tiebreak(self, a: int, b: int) -> tuple[float, str]:
        if self.finals_tiebreak == "fifty_fifty":
            return 0.5, "pilot assumption: hosting averaged 50/50"
        if self.finals_tiebreak == "east":
            return 1.0, "sensitivity: Eastern team always hosts"
        if self.finals_tiebreak == "west":
            return 0.0, "sensitivity: Western team always hosts"
        h2h = self.head_to_head.get((a, b))
        if h2h and h2h[0] != h2h[1]:
            return (1.0 if h2h[0] > h2h[1] else 0.0), "head-to-head record"
        oa = self.vs_other_conf.get(a)
        ob = self.vs_other_conf.get(b)
        if oa is not None and ob is not None and oa != ob:
            return (1.0 if oa > ob else 0.0), "record against the opposite conference"
        return 0.5, "unresolved: hosting averaged 50/50"

    def p_finals(self, a: int, b: int) -> float:
        """Probability a beats b in the Finals, averaging any unresolved hosting."""
        w = self.finals_host[(a, b)]
        if w == 1.0:
            return self.p_series(a, b, True)
        if w == 0.0:
            return self.p_series(a, b, False)
        return w * self.p_series(a, b, True) + (1 - w) * self.p_series(a, b, False)


def series_probability(ps: list[np.ndarray] | list[float]) -> np.ndarray | float:
    """Exact best-of-seven probability by backward recursion.

    ``ps[k]`` is the probability that the tracked team wins game k (0-based),
    either as a scalar or as a whole matrix of pairs at once. Uses

        F(w, l) = p_{w+l} F(w+1, l) + (1 - p_{w+l}) F(w, l+1),
        F(4, l) = 1,  F(w, 4) = 0.
    """
    scalar = np.isscalar(ps[0])
    shape = () if scalar else np.shape(ps[0])
    table: dict[tuple[int, int], np.ndarray] = {}
    for w in range(4, -1, -1):
        for l in range(4, -1, -1):
            if w == 4 and l == 4:
                continue
            if w == 4:
                table[(w, l)] = np.ones(shape)
            elif l == 4:
                table[(w, l)] = np.zeros(shape)
            else:
                p = ps[w + l]
                table[(w, l)] = p * table[(w + 1, l)] + (1 - p) * table[(w, l + 1)]
    out = table[(0, 0)]
    return float(out) if scalar else out


# --------------------------------------------------------------------------
# Play-in enumeration
# --------------------------------------------------------------------------

def playin_states(model: SeasonModel, conf: str) -> dict[tuple[int, int], float]:
    """The six ordered (seed 7, seed 8) outcomes and their probabilities."""
    seven, eight, nine, ten = model.order[conf][6:10]
    p78 = model.p_game(seven, eight, HOME)     # position 7 hosts position 8
    p910 = model.p_game(nine, ten, HOME)       # position 9 hosts position 10
    states: dict[tuple[int, int], float] = {}
    for s7, loser, p1 in [(seven, eight, p78), (eight, seven, 1 - p78)]:
        for winner, p2 in [(nine, p910), (ten, 1 - p910)]:
            # The 7/8 loser hosts the 9/10 winner for seed 8.
            p3 = model.p_game(loser, winner, HOME)
            for s8, p4 in [(loser, p3), (winner, 1 - p3)]:
                states[(s7, s8)] = states.get((s7, s8), 0.0) + p1 * p2 * p4
    assert len(states) == 6, states
    assert abs(sum(states.values()) - 1.0) < 1e-12
    return states


# --------------------------------------------------------------------------
# Conference bracket
# --------------------------------------------------------------------------

def conference_outcome(model: SeasonModel, conf: str, seed7: int, seed8: int
                       ) -> tuple[dict[int, float], dict[int, list[float]]]:
    """Play out one conference bracket exactly.

    Returns the distribution of the conference champion and, per team, the
    probability of winning round 1, round 2 and the conference final.
    """
    by_seed = model.order[conf][:6] + [seed7, seed8]
    seed = {t: k for k, t in enumerate(by_seed)}     # 0 = top seed
    slots = [{by_seed[k - 1]: 1.0} for k in config.BRACKET_ORDER]
    advance = {t: [] for t in by_seed}
    for _ in range(3):
        nxt = []
        for left, right in zip(slots[::2], slots[1::2]):
            out: dict[int, float] = {}
            for a, pa in left.items():
                for b, pb in right.items():
                    # The better seed hosts game 1.
                    p = model.p_series(a, b, seed[a] < seed[b])
                    out[a] = out.get(a, 0.0) + pa * pb * p
                    out[b] = out.get(b, 0.0) + pa * pb * (1 - p)
            nxt.append(out)
            for t, pt in out.items():
                advance[t].append(pt)
        slots = nxt
    return slots[0], advance


def championship(model: SeasonModel, east: dict[int, float],
                 west: dict[int, float]) -> dict[int, float]:
    """Combine two conference-champion distributions into a title distribution."""
    result: dict[int, float] = {}
    for a, pa in east.items():
        for b, pb in west.items():
            p = model.p_finals(a, b)
            result[a] = result.get(a, 0.0) + pa * pb * p
            result[b] = result.get(b, 0.0) + pa * pb * (1 - p)
    assert abs(sum(result.values()) - 1.0) < 1e-10
    return result


# --------------------------------------------------------------------------
# Whole-season results
# --------------------------------------------------------------------------

@dataclass
class SeasonResult:
    season: int
    title_old: dict[int, float]
    title_new: dict[int, float]
    qualify_old: dict[int, float]
    qualify_new: dict[int, float]
    rounds_old: dict[int, list[float]]
    rounds_new: dict[int, list[float]]
    states: dict[str, dict[tuple[int, int], float]]
    expected_champion_rating: tuple[float, float]
    expected_field_rating: tuple[float, float]
    strongest: int


def solve_season(model: SeasonModel) -> SeasonResult:
    teams = list(range(len(model.codes)))
    states = {c: playin_states(model, c) for c in config.CONFERENCES}

    # Old format: seeds are simply positions 1-8.
    conf_old, rounds_old_raw = {}, {}
    for c in config.CONFERENCES:
        dist, adv = conference_outcome(model, c, *model.order[c][6:8])
        conf_old[c] = dist
        rounds_old_raw.update(adv)
    title_old = championship(model, conf_old["Eastern"], conf_old["Western"])

    # Play-in format: enumerate the six seed states per conference, then all 36
    # combinations, keeping the dependence between seeds 7 and 8 intact.
    conf_new: dict[str, dict] = {}
    rounds_new = {t: [0.0, 0.0, 0.0] for t in teams}
    for c in config.CONFERENCES:
        conf_new[c] = {}
        for seeds, weight in states[c].items():
            dist, adv = conference_outcome(model, c, *seeds)
            conf_new[c][seeds] = dist
            for t, probs in adv.items():
                for k, v in enumerate(probs):
                    rounds_new[t][k] += weight * v
    title_new = {t: 0.0 for t in teams}
    for es, ep in states["Eastern"].items():
        for ws, wp in states["Western"].items():
            cond = championship(model, conf_new["Eastern"][es],
                                conf_new["Western"][ws])
            for t, v in cond.items():
                title_new[t] += ep * wp * v
    assert abs(sum(title_new.values()) - 1.0) < 1e-10

    qualify_old = {t: float(model.rank[t] <= 8) for t in teams}
    qualify_new = {t: (1.0 if model.rank[t] <= 6 else 0.0) for t in teams}
    for c, st in states.items():
        for seeds, weight in st.items():
            for t in seeds:
                qualify_new[t] += weight
    for c in config.CONFERENCES:
        s = sum(qualify_new[t] for t in model.order[c][6:10])
        assert abs(s - 2.0) < 1e-10, (c, s)

    rounds_old = {t: rounds_old_raw.get(t, [0.0, 0.0, 0.0]) for t in teams}
    r = model.ratings
    title_old = {t: title_old.get(t, 0.0) for t in teams}
    title_new = {t: title_new.get(t, 0.0) for t in teams}
    exp_champ = (sum(r[t] * title_old[t] for t in teams),
                 sum(r[t] * title_new[t] for t in teams))
    exp_field = (sum(r[t] * qualify_old[t] for t in teams),
                 sum(r[t] * qualify_new[t] for t in teams))
    strongest = int(np.argmax(r))
    return SeasonResult(
        season=model.season, title_old=title_old, title_new=title_new,
        qualify_old=qualify_old, qualify_new=qualify_new,
        rounds_old=rounds_old, rounds_new=rounds_new, states=states,
        expected_champion_rating=exp_champ, expected_field_rating=exp_field,
        strongest=strongest)
