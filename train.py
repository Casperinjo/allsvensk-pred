from src.features import build_features
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import StandardScaler
import pandas as pd


matches = build_features()

X = matches[["home_form" , "away_form" , "home_gd_form" , "away_gd_form" , "home_h2h_form" , "away_h2h_form", "implied_prob_home",  "implied_prob_draw",  "implied_prob_away"]]
y = matches["Res"]

X_train, X_test, y_train, y_test = train_test_split(
    X , y,
    test_size=0.2,
    shuffle=False
)

model = LogisticRegression(max_iter=1000, class_weight="balanced")
scaler = StandardScaler()

X_train_scaled = scaler.fit_transform(X_train)
X_test_scaled = scaler.transform(X_test)

model.fit(X_train_scaled , y_train)
model.classes_
y_pred = model.predict(X_test_scaled)
y_proba = model.predict_proba(X_test_scaled)


print(y_pred)
print("------------------------------------")
print(accuracy_score(y_test , y_pred))
print("------------------------------------")
print(pd.Series(y_pred).value_counts())
print("------------------------------------")
print(pd.DataFrame(model.coef_, columns=X.columns, index=model.classes_))