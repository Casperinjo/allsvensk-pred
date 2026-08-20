
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

    away_df = matches[['Date' , 'Home' , 'Away', 'HG' , 'AG', 'Res']].copy().rename(columns={'Away' : 'team' , 'Home' : 'opponent' , 'AG' : 'goals_for' , 'HG' : 'goals_against', "Res" : "points"}).assign(is_home=False)
    away_df["points"] = np.select(
        condlist=[away_df["goals_for"]  > away_df["goals_against"],
                  away_df["goals_for"]  == away_df["goals_against"]],
        choicelist=[3,1],
        default=0
    )

    stacked = pd.concat([home_df , away_df], ignore_index=True)
    stacked = stacked.sort_values(["team" , "Date"])

    return stacked


def form_eval(team_matches : pd.DataFrame , window = 5) -> pd.DataFrame:
    df = team_matches.copy()
    df["rolling_avg"] = (df
                        .groupby("team")["points"]
                        .transform(lambda s : s.shift(1).rolling(window).mean()))
    
    return df

def strip_data(matches : pd.DataFrame, team_matches : pd.DataFrame) -> pd.DataFrame:
    home_df = team_matches[team_matches["is_home"] == True][["Date", "team" , "rolling_avg"]].copy().rename(columns={"team" : "Home", "rolling_avg" : "home_form"})
    away_df = team_matches[team_matches["is_home"] == False][["Date", "team" , "rolling_avg"]].copy().rename(columns={"team" : "Away", "rolling_avg" : "away_form"})

    result = matches.merge(home_df, on=["Date", "Home"], how="left")
    result = result.merge(away_df, on=["Date", "Away"], how="left")
    return result

def build_features():
    raw = load_matches()
    team_matches = form_eval(reshape_matches(raw))
    final = strip_data(raw, team_matches)
    return final[["Date", "Home", "Away", "home_form", "away_form"]].dropna()

if __name__ == "__main__":
    raw = load_matches()
    team_matches = form_eval(reshape_matches(raw))
    final = strip_data(raw, team_matches)
    print(final[["Date", "Home", "Away", "Res" ,"home_form", "away_form"]].dropna().head(10))

