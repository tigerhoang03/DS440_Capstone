from newssentinel.enrich.tickers import extract_tickers

def test_extract_tickers():
    s = "Big move for $TSLA and (AAPL) today."
    assert extract_tickers(s) == ["AAPL", "TSLA"]
