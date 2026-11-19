from backend.app.signal_engine import analyze_market


def test_engine_does_not_emit_signal_without_enough_candles():
    result = analyze_market([], [], [])
    assert result["signal"] is None
    assert result["status"] == "insufficient_data"


def test_engine_stays_disabled_until_strategy_is_calibrated():
    candles = [{"close": 100 + i} for i in range(60)]
    result = analyze_market(candles, candles, candles)
    assert result["signal"] is None
    assert result["status"] == "not_calibrated"
