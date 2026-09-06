import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, log_loss
from sklearn.dummy import DummyClassifier
from src.features import build_features


def evaluate_model(X: pd.DataFrame, y: pd.Series, n_splits: int = 5) -> None:
    """Chronological cross-validation via TimeSeriesSplit.

    Unlike a single train_test_split, this produces n_splits separate
    (train, test) folds that all preserve time order (every test fold comes
    strictly after its train fold — no shuffling, no future leakage). Report
    accuracy + log_loss PER FOLD, plus their mean/std across folds, so you can
    tell a real improvement apart from noise on one lucky/unlucky split.

    Steps:
      1. tss = TimeSeriesSplit(n_splits=n_splits)
      2. for train_idx, test_idx in tss.split(X):
           - X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]   # positional!
             not .loc — build_features()'s dropna() leaves gaps in the row labels.
           - same slicing for y
           - fit a FRESH StandardScaler + LogisticRegression per fold (don't reuse
             one fitted on a previous fold)
           - accuracy_score(y_test, y_pred)
           - log_loss(y_test, y_proba, labels=model.classes_)
      3. Collect each fold's accuracy/log_loss into lists, print per-fold values
         plus mean/std at the end (np.mean / np.std).

    Note: TimeSeriesSplit's folds grow in both position AND size over time — the
    earliest fold trains on very little data, so don't be surprised if fold 1
    looks worse than your existing single-split baseline.
    """

    baseline_accuracies = []
    accuracies = []
    log_losses = []

    tss = TimeSeriesSplit(n_splits=n_splits)
    for train_idx, test_idx in tss.split(X):
      X_train , X_test = X.iloc[train_idx] , X.iloc[test_idx]    
      Y_train , y_test = y.iloc[train_idx] , y.iloc[test_idx]    

      scaler = StandardScaler()
      X_train_scaled = scaler.fit_transform(X_train)
      X_test_scaled = scaler.transform(X_test)

      model = LogisticRegression(max_iter=1000, class_weight="balanced")
      model.fit(X_train_scaled, Y_train)

      y_pred = model.predict(X_test_scaled)
      y_proba = model.predict_proba(X_test_scaled)

      acc = accuracy_score(y_test , y_pred)
      ll = log_loss(y_test , y_proba , labels=model.classes_)

      accuracies.append(acc)
      log_losses.append(ll)
      print(f"fold {len(accuracies)}: acc={acc:.3f}  log_loss={ll:.3f}")

      dummy = DummyClassifier(strategy="most_frequent")
      dummy.fit(X_train, Y_train)
      baseline_acc = dummy.score(X_test, y_test)   # .score returns accuracy directly
      baseline_accuracies.append(baseline_acc)

    print(f"mean acc: {np.mean(accuracies):.3f} (+/- {np.std(accuracies):.3f})")
    print(f"mean log_loss: {np.mean(log_losses):.3f} (+/- {np.std(log_losses):.3f})")
    print(f"mean baseline acc: {np.mean(baseline_accuracies):.3f}")


   






if __name__ == "__main__":
    matches = build_features()
    X = matches[["home_form", "away_form", "home_gd_form", "away_gd_form",
                 "home_h2h_form", "away_h2h_form", "home_elo", "away_elo", "away_prev_ppg"]]
    y = matches["Res"]
    evaluate_model(X, y)
