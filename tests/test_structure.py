"""Tournament structure, normalisation and the probability identities."""
import numpy as np
import pytest

from nbaplayin import config, tournament


def test_bracket_is_fixed_and_unreseeded():
    assert config.BRACKET_ORDER == [1, 8, 4, 5, 2, 7, 3, 6]
    pairs = [(config.BRACKET_ORDER[i], config.BRACKET_ORDER[i + 1])
             for i in range(0, 8, 2)]
    assert pairs == [(1, 8), (4, 5), (2, 7), (3, 6)]
    assert all(a + b == 9 for a, b in pairs)


def test_series_home_pattern_is_2_2_1_1_1():
    assert config.SERIES_HOME_PATTERN == [True, True, False, False, True, False, True]
    assert sum(config.SERIES_HOME_PATTERN) == 4


def test_game_probabilities_are_complementary(solved):
    for season, (m, _, _) in solved.items():
        a, b = m.order["Eastern"][0], m.order["Western"][0]
        assert m.p_game(a, b, 1) + m.p_game(b, a, -1) == pytest.approx(1.0)
        assert m.p_game(a, b, 0) + m.p_game(b, a, 0) == pytest.approx(1.0)
        assert m.p_series(a, b, True) + m.p_series(b, a, False) == pytest.approx(1.0)


def test_home_court_helps(solved):
    for season, (m, _, _) in solved.items():
        a, b = m.order["Eastern"][0], m.order["Western"][3]
        assert m.p_game(a, b, 1) > m.p_game(a, b, 0) > m.p_game(a, b, -1)


def test_playin_states_sum_to_one(solved):
    for season, (m, res, _) in solved.items():
        for conf, states in res.states.items():
            assert len(states) == 6
            assert sum(states.values()) == pytest.approx(1.0, abs=1e-12)


def test_playin_states_are_not_independent_marginals(solved):
    """Seed 7 and seed 8 are dependent: the joint is not the product."""
    m, res, _ = solved[2025]
    states = res.states["Western"]
    p7 = {}
    p8 = {}
    for (s7, s8), p in states.items():
        p7[s7] = p7.get(s7, 0) + p
        p8[s8] = p8.get(s8, 0) + p
    worst = max(abs(p - p7[s7] * p8[s8]) for (s7, s8), p in states.items())
    assert worst > 1e-3


def test_championship_distributions_normalise(solved):
    for season, (m, res, _) in solved.items():
        assert sum(res.title_old.values()) == pytest.approx(1.0, abs=1e-10)
        assert sum(res.title_new.values()) == pytest.approx(1.0, abs=1e-10)


def test_qualification_sums(solved):
    for season, (m, res, _) in solved.items():
        assert sum(res.qualify_old.values()) == pytest.approx(16.0)
        assert sum(res.qualify_new.values()) == pytest.approx(16.0)
        for conf in config.CONFERENCES:
            contested = sum(res.qualify_new[t] for t in m.order[conf][6:10])
            assert contested == pytest.approx(2.0, abs=1e-10)
            for t in m.order[conf][:6]:
                assert res.qualify_new[t] == pytest.approx(1.0)
            for t in m.order[conf][10:]:
                assert res.qualify_new[t] == 0.0


def test_top_six_and_non_qualifiers(solved):
    for season, (m, res, _) in solved.items():
        for conf in config.CONFERENCES:
            for t in m.order[conf][8:]:
                assert res.title_old[t] == 0.0
            for t in m.order[conf][10:]:
                assert res.title_new[t] == 0.0


def test_advancement_is_monotone(solved):
    for season, (m, res, _) in solved.items():
        for t in range(len(m.codes)):
            r = res.rounds_new[t]
            assert r[0] >= r[1] >= r[2] >= res.title_new[t] - 1e-12


def test_playin_teams_gain_and_lose_the_right_way(solved):
    """Positions 9 and 10 can only gain; positions 7 and 8 can only lose."""
    for season, (m, res, _) in solved.items():
        for conf in config.CONFERENCES:
            for t in m.order[conf][6:8]:
                assert res.qualify_new[t] < 1.0
            for t in m.order[conf][8:10]:
                assert res.qualify_new[t] > 0.0
