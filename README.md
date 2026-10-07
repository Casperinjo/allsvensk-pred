# allsvensk-pred

Predicts Allsvenskan (Swedish top-tier football) match outcomes — home win, draw or
away win — from historical match data, then **keeps score of its own predictions** so
the accuracy claim below is checkable rather than asserted.

**Live:** https://allsvensk-pred-irbbc6cqmq-lz.a.run.app

This is a learning project: a first end-to-end machine-learning service, built to go all
the way from a CSV to something deployed, monitored and honest about its own hit rate.

## How well does it work?

Measured with `TimeSeriesSplit` over 5 chronological folds (`python -m src.evaluate`):

| Metric | Value |
|---|---|
| Mean accuracy | **49.3%** (± 1.0) |
| Mean log loss | 1.031 (± 0.015) |
| Baseline — always predict home win | 42.7% |

So roughly **+6.6 percentage points over the naive baseline**. Modest, and that's the
honest result: three-way football outcomes are genuinely hard, draws especially. A
baseline that always picks the home side is a surprisingly strong opponent, which is
exactly why it's reported here instead of quietly omitted.

Every prediction the service makes is stored and later graded against the real result,
so `/track-record` reports live accuracy on matches it had never seen when it predicted
them — the only number that can't be accidentally cheated by data leakage.

## How it works

```
data/raw/SWE.csv ──► src/load.py ──► src/features.py ──► train.py ──► models/*.pkl
                                                                           │
TheSportsDB ──► src/fixtures.py ──┐                                        ▼
                                  └──► api/main.py ◄──── src/predict.py ───┘
                                           │
                                           ├──► frontend/index.html
                                           └──► src/store.py ──► Firestore
```

**The model** is a multinomial logistic regression (`class_weight="balanced"`, with a
`StandardScaler`) over nine features:

- **Form** — rolling average of recent points, tracked separately for home and away
  records, reset each season
- **Goal-difference form** — rolling goal difference, same split
- **Head-to-head** — long-memory, deliberately *not* reset per season
- **Elo ratings** for both sides
- **Previous-season points per game** for the away side

**Two leakage guards matter more than the feature list.** Every rolling feature is
`.shift(1)`'d before `.rolling()`, so a match's own result can never enter its own form
value; and previous-season aggregates are shifted forward one season, so season N never
sees its own table. The train/test split is **chronological, never shuffled** — a random
split on time-ordered matches would let future games predict past ones and produce a
flattering, meaningless score.

**The target encoding is deliberately non-obvious:** `1 = home win, 0 = draw, 2 = away
win`, mirroring `1`/`X`/`2` betting notation with `X` mapped to `0`. Draw is **not** `1`.
Keep that in mind when reading `predict_proba` columns or a confusion matrix.

## API

| Endpoint | Purpose |
|---|---|
| `GET /` | The web frontend |
| `GET /upcoming-round` | Predictions for fixtures in the next 14 days; saves them for later scoring |
| `POST /predict-fixtures` | Predictions for an arbitrary list of team pairs |
| `GET /track-record` | Scores any pending predictions against real results, returns live accuracy |
| `GET /health` | Dependency-free liveness check |
| `GET /docs` | Auto-generated OpenAPI docs |

Fixtures and results come from [TheSportsDB](https://www.thesportsdb.com) (league
`4347`). Predictions are stored write-once in Firestore and graded when results land, so
re-running the scorer can't regrade a finished match or double-count anything.

## Running it locally

Everything runs **from the repo root** — modules import each other as `from src.x import
y` using implicit namespace packages, so invoking scripts from inside `src/` will fail.

```bash
pip install -r requirements-dev.txt

python -m src.evaluate     # cross-validated accuracy vs. the baseline
python train.py            # fit and write models/{model,scaler,feature_columns}.*
python -m pytest           # 25 tests
uvicorn api.main:app --reload --port 8000
```

Then open http://localhost:8000.

`data/raw/SWE.csv` (match data with betting odds, from
[football-data.co.uk](https://www.football-data.co.uk/swedenm.php)) is committed, so
there's nothing to download. `/track-record` additionally needs Firestore credentials —
`gcloud auth application-default login` — but every other endpoint works without them.

## Project layout

```
src/load.py        load the CSV, parse dates, encode the target
src/features.py    match rows -> model-ready features (form, h2h, Elo, prev-season PPG)
src/predict.py     load the saved model once, predict fixtures
src/fixtures.py    TheSportsDB client for upcoming fixtures and recent results
src/store.py       Firestore persistence: save, score and load predictions
src/evaluate.py    chronological cross-validation against a most-frequent baseline
train.py           fit the model and persist it to models/
api/main.py        FastAPI app; serves the frontend from the same origin
frontend/          single-page UI, no build step and no dependencies
tests/             25 tests; the API suite mocks the fetcher, model and Firestore
notebooks/         exploratory analysis
```

## Deployment

Containerised and running on **Google Cloud Run** (`europe-north1`).

- **CI** — GitHub Actions runs the test suite on every push and pull request
- **CD** — a Cloud Build trigger on pushes to `main` runs `test → build → push →
  deploy`. The test step gates everything below it, so a red suite deploys nothing
- Images are tagged with the commit SHA in Artifact Registry, so any revision traces
  back to an exact commit

`main` is protected: no direct pushes, and a pull request needs green CI to merge.

## Contributing / roadmap

Planned work lives in [`ROADMAP.md`](ROADMAP.md) and is tracked as
[GitHub issues](https://github.com/Casperinjo/allsvensk-pred/issues) on a
[project board](https://github.com/users/Casperinjo/projects/3). The near-term path is
structured logging, a move from Firestore to Cloud SQL, user accounts, and then the
feature the rest is for: **letting users pick matches and compete against the model.**

## Data sources

- Historical matches and odds — [football-data.co.uk](https://www.football-data.co.uk/swedenm.php)
- Fixtures and live results — [TheSportsDB](https://www.thesportsdb.com)
