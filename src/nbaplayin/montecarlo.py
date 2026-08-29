"""Step 5: Monte Carlo simulation of both formats.

The simulator plays individual games. It never draws a champion from the exact
championship vector, so it is a genuine independent check on the bracket code
rather than a restatement of it.

The same stream of uniform random numbers drives both formats (common random
numbers): replicate i uses the same draw for "game 3 of the second-round series
in the lower half of the Eastern bracket" whichever teams happen to be playing
it. The two formats' outcomes are therefore positively correlated, and the
paired standard error of the difference is much smaller than the independent
one. Both standard errors are reported.

A best-of-seven is simulated by playing all seven games and awarding the series
to whoever wins at least four. That is exactly equivalent to stopping at four
wins, because the winner of the first four is always the winner of the seven,
and it keeps the whole simulation vectorised.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import config
from .tournament import SeasonModel

# Position of each first-round series in the seed array (0 = top seed).
ROUND1_PAIRS = [(0, 7), (3, 4), (1, 6), (2, 5)]
N_SERIES = 15          # 8 first round, 4 second, 2 conference finals, 1 Finals
N_GAMES = 7
N_PLAYIN = 3           # per conference


@dataclass
class MCResult:
    season: int
    replicates: int
    seed: int
    champion_counts: dict[str, np.ndarray]     # format -> counts by team index
    qualify_counts: dict[str, np.ndarray]
    strongest: int
    wins_old: int
    wins_new: int
    paired_mean: float
    paired_se: float
    independent_se: float
    seed_state_counts: dict                    # (conf, s7, s8) -> count


def _series(model: SeasonModel, a: np.ndarray, b: np.ndarray,
            a_hosts: np.ndarray, u: np.ndarray) -> np.ndarray:
    """Vectorised best-of-seven. Returns True where a wins the series."""
    wins = np.zeros(len(a), dtype=np.int16)
    for k, host_home in enumerate(config.SERIES_HOME_PATTERN):
        # a is at home when a hosts and the pattern says home, or when b hosts
        # and the pattern says away.
        a_home = np.where(a_hosts, host_home, not host_home)
        p = np.where(a_home, model.p_table[0][a, b], model.p_table[1][a, b])
        wins += (u[:, k] < p).astype(np.int16)
    return wins >= 4


def _play_bracket(model: SeasonModel, seeds: np.ndarray, u: np.ndarray,
                  offset: int) -> tuple[np.ndarray, np.ndarray]:
    """Play one conference bracket. ``seeds[:, k]`` is the team at seed k+1."""
    teams = [seeds[:, i] for pair in ROUND1_PAIRS for i in pair]
    ranks = [np.full(len(seeds), i) for pair in ROUND1_PAIRS for i in pair]
    slot = offset
    while len(teams) > 1:
        nxt_t, nxt_r = [], []
        for i in range(0, len(teams), 2):
            a, b = teams[i], teams[i + 1]
            ra, rb = ranks[i], ranks[i + 1]
            a_hosts = ra < rb
            a_wins = _series(model, a, b, a_hosts, u[:, slot])
            slot += 1
            nxt_t.append(np.where(a_wins, a, b))
            nxt_r.append(np.where(a_wins, ra, rb))
        teams, ranks = nxt_t, nxt_r
    return teams[0], slot


def _playin(model: SeasonModel, conf_order: list[int], u: np.ndarray
            ) -> tuple[np.ndarray, np.ndarray]:
    """Simulate the three play-in games. Returns (seed7, seed8) team arrays."""
    seven, eight, nine, ten = conf_order[6:10]
    n = len(u)
    p78 = model.p_game(seven, eight, 1)
    seven_wins = u[:, 0] < p78
    seed7 = np.where(seven_wins, seven, eight)
    loser = np.where(seven_wins, eight, seven)
    p910 = model.p_game(nine, ten, 1)
    nine_wins = u[:, 1] < p910
    survivor = np.where(nine_wins, nine, ten)
    p_final = model.p_table[0][loser, survivor]     # the 7/8 loser hosts
    seed8 = np.where(u[:, 2] < p_final, loser, survivor)
    return seed7, seed8


def _finals(model: SeasonModel, east: np.ndarray, west: np.ndarray,
            u_games: np.ndarray, u_host: np.ndarray) -> np.ndarray:
    """Return the champion of each replicate."""
    east_hosts = u_host < model.host_matrix[east, west]
    east_wins = _series(model, east, west, east_hosts, u_games)
    return np.where(east_wins, east, west)


def simulate_season(model: SeasonModel, replicates: int = config.MC_REPLICATES,
                    seed: int = config.MC_SEED, progress=None) -> MCResult:
    """Simulate both formats.

    Replicates are drawn in fixed blocks of ``config.MC_CHUNK``, each block
    seeded from (seed, season, block number). The block size is therefore part
    of the implementation, not a tuning knob: the same seed gives the same
    draws whatever the machine, and asking for more replicates extends the run
    rather than changing the replicates already drawn.
    """
    n_teams = len(model.codes)
    block_size = config.MC_CHUNK
    champs = {"old": np.zeros(n_teams, dtype=np.int64),
              "play-in": np.zeros(n_teams, dtype=np.int64)}
    quals = {"old": np.zeros(n_teams, dtype=np.int64),
             "play-in": np.zeros(n_teams, dtype=np.int64)}
    states: dict = {}
    strongest = int(np.argmax(model.ratings))
    d_sum = 0.0
    d_sq = 0.0
    done = 0
    base = {c: np.array(model.order[c][:8]) for c in config.CONFERENCES}
    block = 0
    while done < replicates:
        m = min(block_size, replicates - done)
        rng = np.random.default_rng([seed, model.season, block])
        block += 1
        u_series = rng.random((m, N_SERIES, N_GAMES))
        u_host = rng.random(m)
        u_playin = rng.random((m, 2, N_PLAYIN))
        outcome = {}
        for fmt in ("old", "play-in"):
            champ_of_conf = {}
            slot = 0
            for ci, conf in enumerate(config.CONFERENCES):
                order = model.order[conf]
                if fmt == "old":
                    seeds = np.tile(base[conf], (m, 1))
                else:
                    s7, s8 = _playin(model, order, u_playin[:, ci])
                    seeds = np.column_stack([np.tile(np.array(order[:6]), (m, 1)),
                                             s7, s8])
                    for key, count in zip(*np.unique(
                            np.column_stack([s7, s8]), axis=0, return_counts=True)):
                        k = (conf, int(key[0]), int(key[1]))
                        states[k] = states.get(k, 0) + int(count)
                np.add.at(quals[fmt], seeds.ravel(), 1)
                champ, slot = _play_bracket(model, seeds, u_series, slot)
                champ_of_conf[conf] = champ
            winner = _finals(model, champ_of_conf["Eastern"],
                             champ_of_conf["Western"], u_series[:, slot], u_host)
            np.add.at(champs[fmt], winner, 1)
            outcome[fmt] = (winner == strongest).astype(np.int8)
        d = outcome["play-in"].astype(np.float64) - outcome["old"]
        d_sum += d.sum()
        d_sq += (d ** 2).sum()
        done += m
        if progress:
            progress(done, replicates)
    M = replicates
    w_old = int(champs["old"][strongest])
    w_new = int(champs["play-in"][strongest])
    p_old, p_new = w_old / M, w_new / M
    mean_d = d_sum / M
    var_d = max(d_sq / M - mean_d ** 2, 0.0)
    paired_se = float(np.sqrt(var_d / (M - 1)))
    indep_se = float(np.sqrt(p_old * (1 - p_old) / M + p_new * (1 - p_new) / M))
    return MCResult(season=model.season, replicates=M, seed=seed,
                    champion_counts=champs, qualify_counts=quals,
                    strongest=strongest, wins_old=w_old, wins_new=w_new,
                    paired_mean=mean_d, paired_se=paired_se,
                    independent_se=indep_se, seed_state_counts=states)
