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

def test_parser_reads_ourbit_v1_string_order_open_close_high_low():
    rows = [
        [1700000000000, "100.0", "102.0", "103.0", "99.0", "12.5"],
        [1700000300000, "102.0", "101.0", "104.0", "100.0", "10.0"],
        [1700000600000, "101.0", "103.0", "105.0", "100.5", "14.0"],
    ]
    candles = parse_candles({"code": 200, "data": rows})
    assert len(candles) == 2
    assert candles[-1]["open"] == 102.0
    assert candles[-1]["high"] == 104.0
    assert candles[-1]["low"] == 100.0
    assert candles[-1]["close"] == 101.0
