"""The simulator must agree with the exact calculation and be reproducible."""
import numpy as np
import pytest

from nbaplayin import montecarlo


def test_reproducible_with_the_same_seed(solved):
    m, _, _ = solved[2023]
    a = montecarlo.simulate_season(m, replicates=4000, seed=7)
    b = montecarlo.simulate_season(m, replicates=4000, seed=7)
    assert a.wins_old == b.wins_old
    assert a.wins_new == b.wins_new
    assert np.array_equal(a.champion_counts["old"], b.champion_counts["old"])


def test_a_different_seed_gives_a_different_draw(solved):
    m, _, _ = solved[2023]
    a = montecarlo.simulate_season(m, replicates=4000, seed=7)
    b = montecarlo.simulate_season(m, replicates=4000, seed=8)
    assert a.wins_old != b.wins_old or a.wins_new != b.wins_new


def test_more_replicates_extend_the_same_run(solved):
    """Doubling the replicate count keeps the draws already made."""
    from nbaplayin import config
    m, _, _ = solved[2022]
    n = config.MC_CHUNK
    a = montecarlo.simulate_season(m, replicates=n, seed=3)
    b = montecarlo.simulate_season(m, replicates=2 * n, seed=3)
    assert b.champion_counts["old"].sum() == 2 * n
    assert (b.champion_counts["old"] >= a.champion_counts["old"]).all()


def test_every_replicate_produces_exactly_one_champion(solved):
    m, _, _ = solved[2024]
    mc = montecarlo.simulate_season(m, replicates=5000, seed=11)
    for fmt in ("old", "play-in"):
        assert mc.champion_counts[fmt].sum() == mc.replicates
        assert mc.qualify_counts[fmt].sum() == 16 * mc.replicates


def test_simulation_matches_the_exact_probabilities(solved):
    """Every team's simulated share is within four standard errors of exact."""
    for season, (m, res, _) in solved.items():
        mc = montecarlo.simulate_season(m, replicates=40000, seed=101)
        for fmt, exact in (("old", res.title_old), ("play-in", res.title_new)):
            counts = mc.champion_counts[fmt]
            for t in range(len(m.codes)):
                p = exact[t]
                se = np.sqrt(max(p * (1 - p), 1e-12) / mc.replicates)
                assert abs(counts[t] / mc.replicates - p) < 4 * se + 1e-4


def test_simulated_seed_states_match_the_exact_enumeration(solved):
    m, res, _ = solved[2025]
    mc = montecarlo.simulate_season(m, replicates=40000, seed=5)
    for conf, states in res.states.items():
        for (s7, s8), p in states.items():
            share = mc.seed_state_counts.get((conf, s7, s8), 0) / mc.replicates
            se = np.sqrt(max(p * (1 - p), 1e-12) / mc.replicates)
            assert abs(share - p) < 4 * se + 1e-4


def test_old_format_never_changes_the_field(solved):
    m, res, _ = solved[2021]
    mc = montecarlo.simulate_season(m, replicates=2000, seed=2)
    qualified = mc.qualify_counts["old"]
    for t in range(len(m.codes)):
        expected = mc.replicates if m.rank[t] <= 8 else 0
        assert qualified[t] == expected
