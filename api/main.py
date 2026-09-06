from fastapi import FastAPI
from pydantic import BaseModel

from src.predict import predict_fixtures

app = FastAPI(title="Allsvenskan Predictor API")


class Fixture(BaseModel):
    home_team: str
    away_team: str


class FixturesRequest(BaseModel):
    fixtures: list[Fixture]


class Prediction(BaseModel):
    home_team: str
    away_team: str
    home_win: float
    draw: float
    away_win: float


class PredictionsResponse(BaseModel):
    predictions: list[Prediction]


@app.post("/predict-fixtures", response_model=PredictionsResponse)
def predict_fixtures_endpoint(request: FixturesRequest) -> PredictionsResponse:
    pairs = [(f.home_team, f.away_team) for f in request.fixtures]
    results = predict_fixtures(pairs)
    return PredictionsResponse(predictions=results)
