"""The fitted game model and its published reference values."""
import numpy as np
import pytest

from nbaplayin import config, model


def test_coefficients_match_the_workbook(study):
    wb = study.workbook.model_fit
    for r in wb.itertuples():
        fit = model.fit_window(study.features, int(r._1), int(r._2))
        # The workbook's own optimiser stopped a few nanounits away on one of
        # the fifteen fits, so agreement is asserted to 1e-6, and the gradient
        # check below confirms this fit is the converged one.
        assert fit.beta == pytest.approx(r.beta, abs=1e-6)
        assert fit.h == pytest.approx(r.h, abs=1e-6)
        assert fit.n_train == int(r._5)


def test_fits_are_at_a_stationary_point(study):
    """The likelihood gradient vanishes at every fitted coefficient pair."""
    from scipy.special import expit
    for r in study.workbook.model_fit.itertuples():
        season, window = int(r._1), int(r._2)
        fit = model.fit_window(study.features, season, window)
        train = study.features[study.features.season.between(
            season - window, season - 1)]
        X = np.column_stack([train.srs_difference, train.H]).astype(float)
        y = train.home_win.to_numpy(float)
        grad = X.T @ (expit(X @ np.array([fit.beta, fit.h])) - y)
        assert np.max(np.abs(grad)) < 1e-5 * len(train)


def test_beta_and_home_advantage_have_the_expected_sign(study):
    for season in config.STUDY_SEASONS:
        fit = model.fit_window(study.features, season, config.BASELINE_WINDOW)
        assert fit.beta > 0
        assert fit.h > 0
        assert fit.converged


def test_whiteboard_page3_value(study, solved):
    """Page 3: Golden State hosting Memphis, 2024-25."""
    m, _, _ = solved[2025]
    gs, mem = m.codes.index("GS"), m.codes.index("MEM")
    assert m.p_game(gs, mem, 1) == pytest.approx(0.5207427031776123, abs=1e-9)


def test_whiteboard_page5_value(solved):
    """Pages 5 and 6: Golden State's play-in qualification probability."""
    m, res, _ = solved[2025]
    gs = m.codes.index("GS")
    assert res.qualify_new[gs] == pytest.approx(0.8321779281859525, abs=1e-9)


def test_predictions_beat_the_naive_home_rate(study):
    from nbaplayin import validation
    v = validation.evaluate(study, specs=("srs",),
                            windows=[config.BASELINE_WINDOW])
    reg = v[v.test_set == "Regular season (pregame ratings)"]
    assert (reg.brier < reg.brier_baseline).all()
    assert (reg.log_loss < reg.log_loss_baseline).all()
