"""Transparent, conservative multi-timeframe screening for Ourbit Futures.

This is a research filter, not a profitability claim or execution system.
"""
from __future__ import annotations

from typing import Any
import math


def _rows(payload: Any) -> list[Any]:
    node = payload
    for _ in range(5):
        if isinstance(node, list):
            return node
        if not isinstance(node, dict):
            return []
        nxt = None
        for key in ("data", "result", "list", "rows", "items", "klines"):
            if key in node:
                nxt = node[key]
                break
        if nxt is None:
            return [node]
        node = nxt
    return []


def parse_candles(payload: Any) -> list[dict[str, float]]:
    parsed = []
    for row in _rows(payload):
        try:
            if isinstance(row, (list, tuple)) and len(row) >= 5:
                # Futures V1 commonly returns [time, open, close, high, low, volume].
                # Some feeds return the more common [time, open, high, low, close, volume].
                t = row[0]
                a, b, c, d = (float(x) for x in row[1:5])
                valid = lambda high, low, close: high >= max(a, close) and low <= min(a, close) and high >= low
                if valid(c, d, b):       # O, C, H, L
                    o, close_value, h, l = a, b, c, d
                elif valid(b, c, d):     # O, H, L, C
                    o, h, l, close_value = a, b, c, d
                else:
                    continue
                v = row[5] if len(row) > 5 else 0
            elif isinstance(row, dict):
                t = row.get("time", row.get("timestamp", row.get("t", 0)))
                o = row.get("open", row.get("o"))
                h = row.get("high", row.get("h"))
                l = row.get("low", row.get("l"))
                close_value = row.get("close", row.get("c"))
                v = row.get("volume", row.get("vol", row.get("v", 0)))
            else:
                continue
            candle = {"time": float(t or 0), "open": float(o), "high": float(h),
                      "low": float(l), "close": float(close_value), "volume": float(v or 0)}
            if all(math.isfinite(x) for x in candle.values()) and candle["close"] > 0 and candle["high"] >= candle["low"]:
                parsed.append(candle)
        except (TypeError, ValueError, OverflowError):
            continue
    parsed.sort(key=lambda x: x["time"])
    # The newest bar may still be forming. Exclude it to avoid intrabar repainting.
    return parsed[:-1] if len(parsed) >= 3 else []


def _ema(values: list[float], period: int) -> float:
    alpha = 2.0 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = alpha * value + (1 - alpha) * result
    return result


def _rsi(values: list[float], period: int = 14) -> float:
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    recent = changes[-period:]
    gains = sum(max(x, 0) for x in recent) / period
    losses = sum(max(-x, 0) for x in recent) / period
    if losses == 0:
        return 100.0 if gains else 50.0
    return 100 - 100 / (1 + gains / losses)


def _frame(candles: list[dict[str, float]]) -> dict[str, Any]:
    if len(candles) < 30:
        return {"ready": False, "bars": len(candles)}
    closes = [x["close"] for x in candles]
    last = candles[-1]
    e9, e21 = _ema(closes[-60:], 9), _ema(closes[-60:], 21)
    rsi = _rsi(closes)
    prior = candles[-21:-1]
    high20 = max(x["high"] for x in prior)
    low20 = min(x["low"] for x in prior)
    avg_vol = sum(x["volume"] for x in candles[-21:-1]) / 20
    vol_ratio = last["volume"] / avg_vol if avg_vol > 0 else 0.0
    direction = "LONG" if e9 > e21 and last["close"] > e9 else "SHORT" if e9 < e21 and last["close"] < e9 else "NEUTRAL"
    breakout = last["close"] > high20 if direction == "LONG" else last["close"] < low20 if direction == "SHORT" else False
    body = abs(last["close"] - last["open"]) / last["open"] if last["open"] else 0
    return {"ready": True, "direction": direction, "close": last["close"],
            "ema9": e9, "ema21": e21, "rsi14": rsi, "volume_ratio": vol_ratio,
            "breakout20": breakout, "body_pct": body * 100,
            "swing_high": max(x["high"] for x in candles[-10:]),
            "swing_low": min(x["low"] for x in candles[-10:])}


def evaluate_symbol(c5: Any, c15: Any, c60: Any) -> dict[str, Any]:
    f5, f15, f60 = (_frame(parse_candles(x)) for x in (c5, c15, c60))
    if not f5["ready"]:
        return {"status": "insufficient_data", "label": "داده ۵دقیقه ناکافی", "signal": None}
    if not f15["ready"] or not f60["ready"]:
        return {"status": "insufficient_data", "label": "داده تایم‌فریم کمکی ناکافی", "signal": None}
    direction = f5["direction"]
    if direction == "NEUTRAL":
        return {"status": "no_setup", "label": "فعلاً بدون شرایط ورود", "signal": None,
                "five_min": f5, "fifteen_min": f15, "one_hour": f60}
    aligned15 = f15["direction"] == direction
    # 1h is context only: recorded, not used as a hard veto.
    volume_ok = f5["volume_ratio"] >= 1.15
    momentum_ok = (f5["rsi14"] >= 52 if direction == "LONG" else f5["rsi14"] <= 48)
    breakout_ok = bool(f5["breakout20"])
    score = 0
    score += 35 if aligned15 else 0
    score += 25 if volume_ok else 0
    score += 20 if momentum_ok else 0
    score += 20 if breakout_ok else 0
    if score < 60:
        return {"status": "no_setup", "label": "شرایط ورود کامل نیست", "score": score,
                "signal": None, "five_min": f5, "fifteen_min": f15, "one_hour": f60}
    entry = f5["close"]
    sl = f5["swing_low"] if direction == "LONG" else f5["swing_high"]
    risk = entry - sl if direction == "LONG" else sl - entry
    if risk <= 0 or risk / entry > 0.025:
        return {"status": "risk_rejected", "label": "ریسک ساختاری نامناسب", "score": score,
                "signal": None, "five_min": f5, "fifteen_min": f15, "one_hour": f60}
    sign = 1 if direction == "LONG" else -1
    targets = [entry + sign * risk * r for r in (1, 1.5, 2, 3, 4, 5)]
    return {"status": "candidate", "label": "فرصت احتمالی · آزمایشی", "score": score,
            "signal": {"direction": direction, "entry": entry, "stop_loss": sl,
                       "targets": targets, "risk_reward_tp1": 1.0},
            "context_1h": f60["direction"], "five_min": f5,
            "fifteen_min": f15, "one_hour": f60}
