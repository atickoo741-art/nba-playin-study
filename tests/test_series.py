"""Best-of-seven edge cases and the constant-probability closed form."""
import math

import numpy as np
import pytest

from nbaplayin.tournament import series_probability


def constant(p, n=7, need=4):
    """Closed form: sum of binomial terms for winning 4, 5, 6 or 7 games."""
    return sum(math.comb(n, k) * p ** k * (1 - p) ** (n - k)
               for k in range(need, n + 1))


@pytest.mark.parametrize("p", [0.0, 0.25, 0.4651879350133163, 0.5, 0.75, 1.0])
def test_constant_probability_matches_binomial(p):
    assert series_probability([p] * 7) == pytest.approx(constant(p), abs=1e-12)


def test_certain_outcomes():
    assert series_probability([1.0] * 7) == pytest.approx(1.0)
    assert series_probability([0.0] * 7) == pytest.approx(0.0)


def test_even_series_is_a_coin_flip():
    assert series_probability([0.5] * 7) == pytest.approx(0.5, abs=1e-12)


def test_complementary_under_reflection():
    ps = [0.61, 0.58, 0.42, 0.40, 0.63, 0.39, 0.66]
    mirror = [1 - p for p in ps]
    assert series_probability(ps) + series_probability(mirror) == pytest.approx(1.0)


def test_monotone_in_game_probability():
    low = series_probability([0.45] * 7)
    high = series_probability([0.55] * 7)
    assert low < 0.5 < high


def test_matrix_and_scalar_agree():
    ps = [0.6, 0.55, 0.48, 0.47, 0.62, 0.44, 0.65]
    mats = [np.full((2, 2), p) for p in ps]
    assert series_probability(mats)[0, 0] == pytest.approx(series_probability(ps))


def test_whiteboard_page8_value():
    """Page 8: Golden State over Memphis, neutral court, constant p."""
    p = 0.4651879350133163
    assert series_probability([p] * 7) == pytest.approx(0.4242166807737399, abs=1e-12)
