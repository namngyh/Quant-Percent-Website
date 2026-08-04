from pathlib import Path

from raemf_mc.data.loader import load_price_data


def test_parser_handles_split_thousands(tmp_path: Path):
    p = tmp_path / "d.csv"
    p.write_text("Date,Open,High,Low,Close,Volume,,,,\n1/1/2020,1,2,1,1.5,4,200,,,\n", encoding="utf-8")
    df, meta = load_price_data(p)
    assert df.loc[0, "volume"] == 4200
    assert meta["rows_loaded"] == 1


def test_parser_drops_exact_duplicate_without_doubling_volume(tmp_path: Path):
    p = tmp_path / "duplicates.csv"
    row = "1/1/2020,1,2,1,1.5,4,200,,,\n"
    p.write_text("Date,Open,High,Low,Close,Volume,,,,\n" + row + row, encoding="utf-8")

    df, meta = load_price_data(p)

    assert len(df) == 1
    assert df.loc[0, "volume"] == 4200
    assert meta["duplicate_dates"] == 2
    assert meta["exact_duplicate_records_removed"] == 1
    assert meta["conflicting_duplicate_records_aggregated"] == 0
