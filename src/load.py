

import pandas as pd
from pathlib import Path

# src/load.py -> parents[0] = src/, parents[1] = repo root
data_path = Path(__file__).resolve().parents[1] / "data" / "raw" / "SWE.csv"

def load_matches() -> pd.DataFrame:

    fb_data = pd.read_csv(data_path, parse_dates=["Date"], date_format="%d/%m/%Y")
    fb_data["Res"] = fb_data["Res"].map({"H" : 1 , "D" : 0 , "A" : 2})
    
    fb_data = fb_data.sort_values("Date")

    return fb_data
