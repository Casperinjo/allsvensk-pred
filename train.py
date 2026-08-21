from src.features import build_features
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression

matches = build_features()

X = matches[["home_form" , "away_form"]]
y = matches["Res"]

X_train, X_test, y_train, y_test = train_test_split(
    X , y,
    test_size=0.2,
    shuffle=False
)

model = LogisticRegression(max_iter=1000, class_weight="balanced")


model.fit(X_train , y_train)
model.classes_
y_pred = model.predict(X_test)
y_proba = model.predict_proba(X_test)

print(y_pred)
print(y_proba)