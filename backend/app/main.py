from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import asyncio
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from backend.app.providers.ourbit_futures import OurbitFutures
from backend.app.market_scanner import parse_candles, _frame, evaluate_symbol

app = FastAPI(
    title="ARAD QUANT AI PRO",
    version="0.2.0",
    description="Ourbit Futures read-only market research terminal"
)
exchange = OurbitFutures()
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(FRONTEND.read_text(encoding="utf-8"))

@app.get("/api/health")
async def health():
    return {"ok": True, "project": "ARAD QUANT AI PRO", "mode": "read_only_paper"}

@app.get("/api/status")
async def status():
    return exchange.status()

@app.get("/api/market/connection")
async def market_connection():
    return await exchange.check_connection()

@app.get("/api/market/contracts")
async def market_contracts():
    try:
        return {"source": "ourbit_futures", "data": await exchange.contracts()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ourbit Futures contracts unavailable: {str(exc)[:250]}")

@app.get("/api/market/universe")
async def market_universe():
    """Discover the complete futures contract list; no top-N symbol cap."""
    try:
        return await exchange.market_universe()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ourbit Futures universe unavailable: {str(exc)[:300]}")

@app.get("/api/market/ticker")
async def market_ticker(symbol: str | None = Query(default=None)):
    try:
        return {"source": "ourbit_futures", "data": await exchange.ticker(symbol)}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ourbit Futures ticker unavailable: {str(exc)[:250]}")

@app.get("/api/market/candles")
async def market_candles(
    symbol: str = Query(min_length=3, max_length=40),
    interval: str = Query(default="Min5"),
    start_ms: int | None = Query(default=None, ge=0),
    end_ms: int | None = Query(default=None, ge=0),
):
    allowed = {"Min1", "Min5", "Min15", "Min30", "Min60", "Hour4", "Hour8", "Day1"}
    if interval not in allowed:
        raise HTTPException(status_code=400, detail=f"interval must be one of {sorted(allowed)}")
    if start_ms is not None and end_ms is not None and start_ms >= end_ms:
        raise HTTPException(status_code=400, detail="start_ms must be earlier than end_ms")
    try:
        data = await exchange.candles(symbol.upper(), interval, start_ms, end_ms)
        raw_rows = exchange._kline_count(data)
        parsed_rows = parse_candles(data)
        sample = None
        if isinstance(data, dict):
            node = data
            for _ in range(6):
                if isinstance(node, list):
                    sample = node[0] if node else None
                    break
                if not isinstance(node, dict):
                    break
                child = next((node[k] for k in ("data", "result", "list", "rows", "items", "klines") if k in node), None)
                if child is None:
                    sample = node
                    break
                node = child
        elif isinstance(data, list):
            sample = data[0] if data else None
        return {"source": "ourbit_futures", "symbol": symbol.upper(),
                "interval": interval, "raw_rows": raw_rows,
                "parsed_closed_candles": len(parsed_rows),
                "first_row_sample": sample, "data": data}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ourbit Futures candles unavailable: {str(exc)[:250]}")


@app.get("/api/market/scan")
async def market_scan(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=40),
    symbols: str | None = Query(default=None, max_length=2000),
):
    """Scan a bounded page of the full futures universe to stay within serverless limits."""
    try:
        if symbols:
            contracts = [{"symbol": x.strip().upper()} for x in symbols.split(",") if x.strip()]
            total = len(contracts)
            page = contracts
        else:
            universe = await exchange.market_universe()
            contracts = universe.get("scan_candidates", [])
            total = len(contracts)
            page = contracts[offset:offset + limit]
        semaphore = asyncio.Semaphore(4)
        scanned = 0
        errors = 0

        async def inspect(item):
            nonlocal scanned, errors
            symbol = item.get("symbol")
            if not symbol:
                return {"symbol": "?", "status": "invalid_symbol", "label": "نماد نامعتبر"}
            async with semaphore:
                try:
                    raw5 = await exchange.candles(symbol, "Min5")
                    candles5 = parse_candles(raw5)
                    f5 = _frame(candles5)
                    scanned += 1
                    if not f5.get("ready"):
                        return {"symbol": symbol, "status": "insufficient_data",
                                "label": "داده ۵دقیقه ناکافی", "bars_5m": len(candles5)}
                    direction = f5.get("direction")
                    preliminary = (direction != "NEUTRAL" and
                                   (f5.get("volume_ratio", 0) >= 1.05 or f5.get("breakout20")))
                    if not preliminary:
                        return {"symbol": symbol, "status": "no_setup",
                                "label": "فعلاً بدون شرایط ورود", "five_min": f5}
                    raw15, raw60 = await asyncio.gather(
                        exchange.candles(symbol, "Min15"),
                        exchange.candles(symbol, "Min60"),
                    )
                    result = evaluate_symbol(raw5, raw15, raw60)
                    return {"symbol": symbol, **result}
                except Exception as exc:
                    errors += 1
                    return {"symbol": symbol, "status": "data_error",
                            "label": "خطای دریافت داده", "error": str(exc)[:160]}

        results = await asyncio.gather(*(inspect(x) for x in page))
        results.sort(key=lambda x: (x.get("status") == "candidate",
                                    x.get("score", 0)), reverse=True)
        candidates = [x for x in results if x.get("status") == "candidate"]
        next_offset = offset + len(page)
        return {
            "status": "completed",
            "universe_total": total,
            "offset": offset,
            "limit": limit,
            "next_offset": next_offset if next_offset < len(contracts) else None,
            "done": next_offset >= total,
            "scanned_5m": scanned,
            "candidates": len(candidates),
            "data_errors": errors,
            "results": results,
            "method": "closed 5m primary; 15m confirmation; 1h context only",
            "note": "Research candidates only. Not validated trading signals; paper-test before use."
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Market scan unavailable: {str(exc)[:300]}")

@app.get("/api/signals")
async def signals():
    # Universe discovery is real market coverage, not a trade signal.
    try:
        universe = await exchange.market_universe()
        return {
            "status": "paper_only",
            "signals": [],
            "universe": {
                "contracts_total": universe["contracts_total"],
                "active_count": universe["active_count"],
                "inactive_count": universe["inactive_count"],
                "unknown_status_count": universe["unknown_status_count"],
                "tickers_received": universe["tickers_received"],
            },
            "message": "All active contracts are discovered. Signal generation remains disabled until candle formats, multi-timeframe rules, and paper-test results are validated.",
        }
    except Exception as exc:
        return {
            "status": "market_unavailable",
            "signals": [],
            "universe": None,
            "message": f"Could not load the full futures universe: {str(exc)[:250]}",
        }
