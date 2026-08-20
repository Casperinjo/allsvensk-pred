# football-predictor

A small, educational ML project predicting Allsvenskan (Swedish top-tier
football league) match outcomes.

## Project structure

```
data/raw/          # downloaded CSVs, gitignored
data/processed/     # cleaned/feature-engineered data
src/
  load.py           # load raw data into DataFrames
  features.py        # turn raw data into model-ready features
  evaluate.py         # evaluate predictions against actual results
notebooks/01-explore.ipynb   # exploratory data analysis
train.py             # entry point: load -> features -> train -> evaluate
```

## Status

Work in progress — scaffolding only, no data or model yet.
