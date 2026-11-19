from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from backend.app.providers.ourbit_futures import OurbitFutures

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
        return {"source": "ourbit_futures", "symbol": symbol.upper(),
                "interval": interval, "data": data}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ourbit Futures candles unavailable: {str(exc)[:250]}")

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
