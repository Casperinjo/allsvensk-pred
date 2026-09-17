# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install prod deps first, in their own layer — this layer is cached and only
# rebuilds when requirements.txt changes, not on every code edit.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code, the frontend, and the match data. The CSV is required at
# RUNTIME (predict.py re-reads it to build current form/elo), not just to train.
COPY src/ src/
COPY api/ api/
COPY frontend/ frontend/
COPY train.py .

# The match data is committed to the repo (see .gitignore) so both local builds and
# GitHub-triggered CD builds have it. It's required at RUNTIME too (predict.py
# re-reads it to build current form/elo), not just to train.
COPY data/raw/SWE.csv data/raw/SWE.csv

# Train the model at build time -> writes models/{model,scaler}.pkl + feature_columns.json.
# Bakes a ready-to-serve model into the image; needs only the prod deps above.
RUN python train.py

# TheSportsDB key is NOT baked in (that would leak into image history). The code
# defaults to the shared demo key "3"; inject a real key at run time with
# `docker run -e THESPORTSDB_KEY=...` or, later, a Kubernetes Secret.

EXPOSE 8000
# 0.0.0.0 (not 127.0.0.1) so the server is reachable from outside the container.
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
