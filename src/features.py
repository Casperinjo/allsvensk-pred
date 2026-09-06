
import pandas as pd
import numpy as np
from src.load import load_matches

def reshape_matches(matches : pd.DataFrame) -> pd.DataFrame:


    home_df = matches[['Date' , 'Home' , 'Away', 'HG' , 'AG', 'Res']].copy().rename(columns={'Home' : 'team' , 'Away' : 'opponent' , 'HG' : 'goals_for' , 'AG' : 'goals_against' , "Res" : "points"}).assign(is_home=True)
    home_df["points"] = np.select(
            condlist=[home_df["goals_for"]  > home_df["goals_against"],
                      home_df["goals_for"]  == home_df["goals_against"]],
            choicelist=[3,1],
            default=0
    
        )
    home_df["goal_diff"] = home_df["goals_for"] - home_df["goals_against"]

    away_df = matches[['Date' , 'Home' , 'Away', 'HG' , 'AG', 'Res']].copy().rename(columns={'Away' : 'team' , 'Home' : 'opponent' , 'AG' : 'goals_for' , 'HG' : 'goals_against', "Res" : "points"}).assign(is_home=False)
    away_df["points"] = np.select(
        condlist=[away_df["goals_for"]  > away_df["goals_against"],
                  away_df["goals_for"]  == away_df["goals_against"]],
        choicelist=[3,1],
        default=0
    )
    away_df["goal_diff"] = away_df["goals_for"] - away_df["goals_against"]
    stacked = pd.concat([home_df , away_df], ignore_index=True)
    stacked = stacked.sort_values(["team" , "Date"])

    return stacked


def form_eval(team_matches : pd.DataFrame , window = 5) -> pd.DataFrame:
    df = team_matches.copy()
    df["rolling_avg"] = (df
                        .groupby(["team", "is_home"])["points"]
                        .transform(lambda s : s.shift(1).rolling(window).mean()))
    df["rolling_gd"] = (df
                        .groupby(["team", "is_home"])["goal_diff"]
                        .transform(lambda s : s.shift(1).rolling(window).mean()))
    df["h2h_avg"] = (df
                      .groupby(["team", "opponent"])["points"]
                      .transform(lambda s: s.shift(1).expanding().mean())).fillna(1.0)
    
    return df

def strip_data(matches : pd.DataFrame, team_matches : pd.DataFrame) -> pd.DataFrame:
    home_df = team_matches[team_matches["is_home"] == True][["Date", "team" , "rolling_avg" , "rolling_gd" , "h2h_avg"]].copy().rename(columns={"team" : "Home", "rolling_avg" : "home_form" , "rolling_gd" : "home_gd_form" , "h2h_avg" : "home_h2h_form"})
    away_df = team_matches[team_matches["is_home"] == False][["Date", "team" , "rolling_avg" , "rolling_gd", "h2h_avg"]].copy().rename(columns={"team" : "Away", "rolling_avg" : "away_form" , "rolling_gd" : "away_gd_form", "h2h_avg" : "away_h2h_form"})

    result = matches.merge(home_df, on=["Date", "Home"], how="left")
    result = result.merge(away_df, on=["Date", "Away"], how="left")
    return result

def add_implied_probs(matches : pd.DataFrame) -> pd.DataFrame:
    df = matches.copy()
    df["p_home"] = 1 / df["AvgCH"]
    df["p_draw"] = 1 / df["AvgCD"]
    df["p_away"] = 1 / df["AvgCA"]

    df["overround"] = df["p_home"] + df["p_draw"] + df["p_away"]

    df["implied_prob_home"] = df["p_home"] / df["overround"]
    df["implied_prob_draw"] = df["p_draw"] / df["overround"]
    df["implied_prob_away"] = df["p_away"] / df["overround"]

    return df



def _run_elo(matches: pd.DataFrame, k: float, home_advantage: float, initial_rating: float):
    """Sequential Elo update loop over matches (must be sorted by Date ascending).

    Returns (home_elo, away_elo, ratings): the pre-match rating recorded for
    each row, and the final ratings dict after every match has been processed
    (i.e. each team's *current* rating, going into a hypothetical next match).
    """
    ratings: dict[str, float] = {}
    home_elo = []
    away_elo = []

    for row in matches.itertuples():
        r_home = ratings.get(row.Home, initial_rating)
        r_away = ratings.get(row.Away, initial_rating)

        # Record pre-match ratings first — the sequential-loop equivalent of
        # shift(1): this match's own result must not leak into its own feature.
        home_elo.append(r_home)
        away_elo.append(r_away)

        expected_home = 1 / (1 + 10 ** ((r_away - (r_home + home_advantage)) / 400))
        expected_away = 1 - expected_home

        if row.HG > row.AG:
            score_home = 1.0
        elif row.HG == row.AG:
            score_home = 0.5
        else:
            score_home = 0.0
        score_away = 1 - score_home

        ratings[row.Home] = r_home + k * (score_home - expected_home)
        ratings[row.Away] = r_away + k * (score_away - expected_away)

    return home_elo, away_elo, ratings


def add_elo_ratings(matches: pd.DataFrame, k: float = 20, home_advantage: float = 100, initial_rating: float = 1500) -> pd.DataFrame:
    """Adds pre-match home_elo/away_elo columns.

    Unlike every other feature so far, this can't be a groupby/transform: each
    match's rating update depends on BOTH teams' current ratings against each
    other, which in turn depend on all prior matches involving EITHER team — so
    it needs a genuine sequential loop over matches in Date order. Ratings carry
    across season boundaries (same choice already made for form_eval); a new
    team defaults to initial_rating.
    """
    df = matches.copy()
    home_elo, away_elo, _ = _run_elo(df, k, home_advantage, initial_rating)
    df["home_elo"] = home_elo
    df["away_elo"] = away_elo
    return df


def get_current_elo_ratings(matches: pd.DataFrame, k: float = 20, home_advantage: float = 100, initial_rating: float = 1500) -> dict:
    """Each team's Elo rating after their most recent played match — used by
    get_matchup_features to feed a hypothetical next match."""
    _, _, ratings = _run_elo(matches, k, home_advantage, initial_rating)
    return ratings


def get_matchup_features(home_team: str, away_team: str, team_matches: pd.DataFrame | None = None, elo_ratings: dict | None = None, window: int = 5, initial_rating: float = 1500) -> dict:
    """Current feature snapshot for a hypothetical, not-yet-played matchup.

    Unlike form_eval's rolling_avg/rolling_gd/h2h_avg (which are deliberately
    shift(1)'d so a *training* row never sees its own match's outcome), here
    there's no "own outcome" to avoid — home_team/away_team's most recent real
    match should be INCLUDED in the window, not excluded from it. So this uses
    its own (unshifted) mean over the tail of each team's history, evaluated at
    "now" instead of at a specific historical row.

    team_matches: pass in a pre-built reshape_matches(load_matches()) frame to
    avoid reloading/reshaping the whole dataset on every call (predict.py builds
    it once and reuses it across a batch of fixtures); builds it itself if omitted.
    elo_ratings: pass in a pre-built get_current_elo_ratings(...) dict, same
    reasoning — computing it is its own sequential pass over all matches.
    """
    if team_matches is None:
        team_matches = reshape_matches(load_matches())
    if elo_ratings is None:
        elo_ratings = get_current_elo_ratings(load_matches())

    home_recent = team_matches[(team_matches["team"] == home_team) & (team_matches["is_home"] == True)].tail(window)
    away_recent = team_matches[(team_matches["team"] == away_team) & (team_matches["is_home"] == False)].tail(window)

    # Neutral-prior fallbacks for a team/pairing with no history yet: 1.0 for
    # points (~ a draw, same convention form_eval's h2h_avg.fillna(1.0) uses),
    # 0.0 for goal_diff (no expected dominance either way).
    home_form = home_recent["points"].mean() if not home_recent.empty else 1.0
    away_form = away_recent["points"].mean() if not away_recent.empty else 1.0
    home_gd_form = home_recent["goal_diff"].mean() if not home_recent.empty else 0.0
    away_gd_form = away_recent["goal_diff"].mean() if not away_recent.empty else 0.0

    home_h2h = team_matches[(team_matches["team"] == home_team) & (team_matches["opponent"] == away_team)]
    away_h2h = team_matches[(team_matches["team"] == away_team) & (team_matches["opponent"] == home_team)]

    home_h2h_form = home_h2h["points"].mean() if not home_h2h.empty else 1.0
    away_h2h_form = away_h2h["points"].mean() if not away_h2h.empty else 1.0

    home_elo = elo_ratings.get(home_team, initial_rating)
    away_elo = elo_ratings.get(away_team, initial_rating)

    return {
        "home_form": home_form,
        "away_form": away_form,
        "home_gd_form": home_gd_form,
        "away_gd_form": away_gd_form,
        "home_h2h_form": home_h2h_form,
        "away_h2h_form": away_h2h_form,
        "home_elo": home_elo,
        "away_elo": away_elo,
    }


FEATURE_COLUMNS = ["Date", "Home", "Away", "Res", "home_form", "away_form", "home_gd_form", "away_gd_form",
                    "home_h2h_form", "away_h2h_form", "home_elo", "away_elo",
                    "implied_prob_home", "implied_prob_draw", "implied_prob_away"]


def build_features():
    raw = load_matches()
    team_matches = form_eval(reshape_matches(raw))
    stripped_data = strip_data(raw, team_matches)
    with_probs = add_implied_probs(stripped_data)
    final = add_elo_ratings(with_probs)
    return final[FEATURE_COLUMNS].dropna()

if __name__ == "__main__":
    raw = load_matches()
    team_matches = form_eval(reshape_matches(raw))
    stripped_data = strip_data(raw, team_matches)
    with_probs = add_implied_probs(stripped_data)
    final = add_elo_ratings(with_probs)
    print(final[FEATURE_COLUMNS].dropna())

