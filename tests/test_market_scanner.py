from backend.app.market_scanner import parse_candles, evaluate_symbol


def _sample():
    rows = []
    for i in range(80):
        close = 100 + i * 0.25
        rows.append([i * 300000, close - 0.1, close + 0.2,
                     close - 0.2, close, 100 + (20 if i == 79 else 0)])
    return {"data": rows}


def test_parser_reads_ourbit_ohlcv_arrays_and_drops_open_bar():
    candles = parse_candles(_sample())
    assert len(candles) == 79
    assert candles[-1]["close"] > candles[0]["close"]


def test_analyzer_never_calls_insufficient_data_a_signal():
    result = evaluate_symbol({"data": []}, {"data": []}, {"data": []})
    assert result["status"] == "insufficient_data"
    assert result["signal"] is None
