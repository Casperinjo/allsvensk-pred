"""Tests for src.features — the feature pipeline.

The highest-value tests here are the **leakage guards**: a match's own result must
never leak into its own features. That's the class of bug that silently inflates
offline scores and can't be caught by eyeballing predictions.
"""

import pandas as pd
import pytest

from src.features import (
    reshape_matches,
    form_eval,
    add_prev_season_ppg,
    add_implied_probs,
    add_elo_ratings,
    get_matchup_features,
)


# ---------------------------------------------------------------------------
# reshape_matches
# ---------------------------------------------------------------------------

def test_reshape_creates_two_perspectives_with_scores():
    raw = pd.DataFrame([
        {"Season": 2024, "Date": pd.Timestamp("2024-04-01"),
         "Home": "A", "Away": "B", "HG": 2, "AG": 1, "Res": 1},
    ])
    out = reshape_matches(raw)

    assert len(out) == 2  # one row per team-perspective

    home = out[out["is_home"]].iloc[0]
    away = out[~out["is_home"]].iloc[0]

    assert home["team"] == "A" and home["opponent"] == "B"
    assert home["goals_for"] == 2 and home["goals_against"] == 1
    assert home["points"] == 3 and home["goal_diff"] == 1
    assert home["Season"] == 2024

    assert away["team"] == "B" and away["opponent"] == "A"
    assert away["goals_for"] == 1 and away["goals_against"] == 2
    assert away["points"] == 0 and away["goal_diff"] == -1
    assert away["Season"] == 2024


def test_reshape_draw_gives_one_point_each():
    raw = pd.DataFrame([
        {"Season": 2024, "Date": pd.Timestamp("2024-04-01"),
         "Home": "A", "Away": "B", "HG": 1, "AG": 1, "Res": 0},
    ])
    out = reshape_matches(raw)
    assert set(out["points"]) == {1}
    assert set(out["goal_diff"]) == {0}


# ---------------------------------------------------------------------------
# form_eval — leakage guard, season reset, cross-season h2h
# ---------------------------------------------------------------------------

def test_form_excludes_current_match_no_leakage():
    # Same team's home matches within one season, in date order.
    tm = pd.DataFrame([
        {"team": "A", "opponent": "W", "is_home": True, "Season": 2024, "points": 3, "goal_diff": 2},
        {"team": "A", "opponent": "X", "is_home": True, "Season": 2024, "points": 0, "goal_diff": -1},
        {"team": "A", "opponent": "Y", "is_home": True, "Season": 2024, "points": 1, "goal_diff": 0},
        {"team": "A", "opponent": "Z", "is_home": True, "Season": 2024, "points": 3, "goal_diff": 1},
    ])
    out = form_eval(tm, window=2)
    ra = list(out["rolling_avg"])

    # Not enough prior matches yet -> NaN.
    assert pd.isna(ra[0]) and pd.isna(ra[1])
    # Uses the two PRIOR matches only.
    assert ra[2] == pytest.approx(1.5)   # mean(3, 0)
    # The key assertion: this match's form is mean(prior two) = mean(0, 1) = 0.5,
    # which EXCLUDES its own 3 points. That's the .shift(1) leak guard working.
    assert ra[3] == pytest.approx(0.5)


def test_form_resets_each_season():
    tm = pd.DataFrame([
        {"team": "A", "opponent": "P", "is_home": True, "Season": 2024, "points": 3, "goal_diff": 1},
        {"team": "A", "opponent": "Q", "is_home": True, "Season": 2024, "points": 3, "goal_diff": 1},
        {"team": "A", "opponent": "R", "is_home": True, "Season": 2025, "points": 0, "goal_diff": -1},
        {"team": "A", "opponent": "S", "is_home": True, "Season": 2025, "points": 0, "goal_diff": -1},
        {"team": "A", "opponent": "T", "is_home": True, "Season": 2025, "points": 0, "goal_diff": -1},
    ])
    out = form_eval(tm, window=2)
    ra = list(out["rolling_avg"])

    # First two matches of the new season have no in-season history -> NaN,
    # proving 2024's strong form does NOT carry across the off-season.
    assert pd.isna(ra[2]) and pd.isna(ra[3])
    # Third 2025 match uses only 2025 priors [0, 0] -> 0.0, untouched by 2024's 3s.
    assert ra[4] == pytest.approx(0.0)


def test_h2h_carries_across_seasons_and_defaults_to_one():
    tm = pd.DataFrame([
        {"team": "A", "opponent": "B", "is_home": True, "Season": 2024, "points": 3, "goal_diff": 1},
        {"team": "A", "opponent": "B", "is_home": True, "Season": 2025, "points": 0, "goal_diff": -1},
        {"team": "A", "opponent": "B", "is_home": True, "Season": 2025, "points": 0, "goal_diff": -1},
    ])
    out = form_eval(tm, window=2)
    h = list(out["h2h_avg"])

    assert h[0] == pytest.approx(1.0)   # no prior meeting -> fillna(1.0)
    assert h[1] == pytest.approx(3.0)   # prior meeting was in 2024 -> carried across
    assert h[2] == pytest.approx(1.5)   # prior meetings [3, 0] -> mean 1.5


# ---------------------------------------------------------------------------
# add_prev_season_ppg — off-season leak guard
# ---------------------------------------------------------------------------

def test_prev_season_ppg_uses_prior_season_only():
    # Two teams that swap fortunes between seasons, so the league mean (1.5)
    # differs from every team's own ppg — makes the no-leak assertion sharp.
    tm = pd.DataFrame([
        {"team": "A", "Season": 2024, "points": 3},
        {"team": "A", "Season": 2024, "points": 3},
        {"team": "A", "Season": 2025, "points": 0},
        {"team": "A", "Season": 2025, "points": 0},
        {"team": "B", "Season": 2024, "points": 0},
        {"team": "B", "Season": 2024, "points": 0},
        {"team": "B", "Season": 2025, "points": 3},
        {"team": "B", "Season": 2025, "points": 3},
    ])
    out = add_prev_season_ppg(tm)

    def val(team, season):
        return out[(out["team"] == team) & (out["Season"] == season)]["prev_season_ppg"].iloc[0]

    # Season N sees season N-1's ppg.
    assert val("A", 2025) == pytest.approx(3.0)   # A's 2024 ppg
    assert val("B", 2025) == pytest.approx(0.0)   # B's 2024 ppg

    # Earliest season has no prior -> filled with league mean of known values
    # (A2025 rows = 3, B2025 rows = 0 -> 1.5). Crucially NOT A's own 2024 ppg (3.0),
    # which would be self-leakage.
    assert val("A", 2024) == pytest.approx(1.5)
    assert val("B", 2024) == pytest.approx(1.5)


# ---------------------------------------------------------------------------
# add_implied_probs
# ---------------------------------------------------------------------------

def test_implied_probs_normalized_and_ordered():
    raw = pd.DataFrame([{"AvgCH": 1.9, "AvgCD": 3.5, "AvgCA": 4.0}])
    out = add_implied_probs(raw)

    total = out.loc[0, ["implied_prob_home", "implied_prob_draw", "implied_prob_away"]].sum()
    assert total == pytest.approx(1.0)                 # normalized away the margin
    assert out.loc[0, "overround"] > 1.0               # bookmaker margin present
    assert out.loc[0, "implied_prob_home"] > out.loc[0, "implied_prob_away"]  # shortest odds = likeliest


# ---------------------------------------------------------------------------
# elo — pre-match recording (no leakage)
# ---------------------------------------------------------------------------

def test_elo_records_prematch_ratings():
    raw = pd.DataFrame([
        {"Home": "A", "Away": "B", "HG": 2, "AG": 0},   # A wins
        {"Home": "A", "Away": "B", "HG": 0, "AG": 0},   # draw
    ])
    out = add_elo_ratings(raw, k=20, home_advantage=0, initial_rating=1500)

    home_elo = list(out["home_elo"])
    away_elo = list(out["away_elo"])

    # Match 1's recorded ratings are the pre-match values (initial), NOT the
    # post-result update — the loop's equivalent of shift(1).
    assert home_elo[0] == 1500 and away_elo[0] == 1500
    # By match 2, match 1's result has moved the ratings.
    assert home_elo[1] > 1500   # A won -> up
    assert away_elo[1] < 1500   # B lost -> down


# ---------------------------------------------------------------------------
# get_matchup_features — inference-time feature builder
# ---------------------------------------------------------------------------

def test_get_matchup_features_returns_expected_scalar_keys():
    raw = pd.DataFrame([
        {"Season": 2024, "Date": pd.Timestamp("2024-04-01"),
         "Home": "A", "Away": "B", "HG": 2, "AG": 0, "Res": 1},
        {"Season": 2024, "Date": pd.Timestamp("2024-04-08"),
         "Home": "B", "Away": "A", "HG": 1, "AG": 1, "Res": 0},
        {"Season": 2025, "Date": pd.Timestamp("2025-04-01"),
         "Home": "A", "Away": "B", "HG": 0, "AG": 3, "Res": 2},
    ])
    tm = reshape_matches(raw)
    elo = {"A": 1600.0, "B": 1400.0}

    feats = get_matchup_features("A", "B", team_matches=tm, elo_ratings=elo, window=3)

    assert set(feats) == {
        "home_form", "away_form", "home_gd_form", "away_gd_form",
        "home_h2h_form", "away_h2h_form", "home_elo", "away_elo", "away_prev_ppg",
    }
    assert feats["home_elo"] == 1600.0 and feats["away_elo"] == 1400.0
    # away_prev_ppg must be a single number, not a Series (the bug we fixed).
    assert isinstance(feats["away_prev_ppg"], float)
    # B's most recent prev-season value is its 2024 ppg = mean(0 as away, 1 as home) = 0.5.
    assert feats["away_prev_ppg"] == pytest.approx(0.5)
    # Every feature is a plain scalar so predict.py can build a valid feature row.
    for v in feats.values():
        assert isinstance(v, (int, float)) and not isinstance(v, bool)


def test_get_matchup_features_unknown_team_falls_back():
    raw = pd.DataFrame([
        {"Season": 2024, "Date": pd.Timestamp("2024-04-01"),
         "Home": "A", "Away": "B", "HG": 2, "AG": 0, "Res": 1},
    ])
    tm = reshape_matches(raw)
    elo = {"A": 1600.0}  # deliberately missing the unknown team

    feats = get_matchup_features("A", "ZZZ", team_matches=tm, elo_ratings=elo, window=3)

    # Unknown away team -> neutral form fallbacks and the default elo rating.
    assert feats["away_form"] == pytest.approx(1.0)
    assert feats["away_gd_form"] == pytest.approx(0.0)
    assert feats["away_elo"] == 1500  # initial_rating default
