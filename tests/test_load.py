"""Tests for src.load — the CSV reader that encodes results and sorts by date."""

from src.load import load_matches


def test_load_matches_encodes_result_and_sorts_by_date(tmp_path, monkeypatch):
    # A tiny stand-in for data/raw/SWE.csv (which is gitignored and absent in CI).
    # Deliberately out of date order to prove the sort, one of each result letter.
    csv = tmp_path / "SWE.csv"
    csv.write_text(
        "Date,Res\n"
        "05/04/2024,H\n"
        "01/04/2024,D\n"
        "03/04/2024,A\n"
    )
    monkeypatch.setattr("src.load.data_path", csv)

    df = load_matches()

    # Sorted ascending by parsed date (1st, 3rd, 5th).
    assert list(df["Date"].dt.day) == [1, 3, 5]
    # Encoding is the non-obvious part: H->1, D->0, A->2. In sorted order that's
    # the 1st (D), 3rd (A), 5th (H) rows.
    assert list(df["Res"]) == [0, 2, 1]
