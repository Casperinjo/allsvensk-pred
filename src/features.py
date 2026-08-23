
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

    probs_sum_ok = np.allclose(df[["implied_prob_home","implied_prob_draw","implied_prob_away"]].sum(axis=1), 1.0)
    print(f"Sum of implied probs OK: {probs_sum_ok}")

    return df



def build_features():
    raw = load_matches()
    team_matches = form_eval(reshape_matches(raw))
    stripped_data = strip_data(raw, team_matches)
    final = add_implied_probs(stripped_data)
    return final[["Date", "Home", "Away", "Res" , "home_form", "away_form" , "home_gd_form" ,"away_gd_form" , "home_h2h_form" , "away_h2h_form", "implied_prob_home",  "implied_prob_draw",  "implied_prob_away"]].dropna()

if __name__ == "__main__":
    raw = load_matches()
    team_matches = form_eval(reshape_matches(raw))
    stripped_data = strip_data(raw, team_matches)
    final = add_implied_probs(stripped_data)
    print(final[["Date", "Home", "Away", "Res" , "home_form", "away_form" , "home_gd_form" ,"away_gd_form" , "home_h2h_form" , "away_h2h_form", "implied_prob_home",  "implied_prob_draw",  "implied_prob_away"]].dropna())

