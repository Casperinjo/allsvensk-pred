
import pandas as pd
from src.load import load_matches

def build_features(matches : pd.DataFrame) -> pd.DataFrame:


    home_df = matches[['Date' , 'Home' , 'Away', 'HG' , 'AG', 'Res']].copy().rename(columns={'Home' : 'team' , 'Away' : 'opponent' , 'HG' : 'goals_for' , 'AG' : 'goals_against' , "Res" : "points"}).assign(is_home=True)
    home_df['points'] = home_df['points'].map({"H": 3, "D": 1, "A": 0})

    away_df = matches[['Date' , 'Home' , 'Away', 'HG' , 'AG', 'Res']].copy().rename(columns={'Away' : 'team' , 'Home' : 'opponent' , 'AG' : 'goals_for' , 'HG' : 'goals_against', "Res" : "points"}).assign(is_home=False)
    away_df['points'] = away_df['points'].map({"H": 0, "D": 1, "A": 3})

    stacked = pd.concat([home_df , away_df], ignore_index=True)
    stacked = stacked.sort_values(["team" , "Date"])

    return stacked


team_matches = build_features(load_matches())

print(team_matches)