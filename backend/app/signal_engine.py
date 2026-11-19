"""Conservative research-only multi-timeframe signal scaffold.

No probability or accuracy claim is made. This module intentionally returns
NO SIGNAL until enough validated candles are supplied and the strategy is
implemented and tested.
"""
from __future__ import annotations
from typing import Any


def analyze_market(candles_5m: list[dict[str, Any]],
                   candles_15m: list[dict[str, Any]],
                   candles_1h: list[dict[str, Any]]) -> dict[str, Any]:
    if min(len(candles_5m), len(candles_15m), len(candles_1h)) < 60:
        return {"status": "insufficient_data", "signal": None,
                "reason": "At least 60 candles are required on each timeframe."}
    return {"status": "not_calibrated", "signal": None,
            "reason": "Strategy validation is not complete; no trade signal is emitted."}
