from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from backend.app.providers.ourbit_futures import OurbitFutures

app = FastAPI(title="ARAD QUANT AI PRO", version="0.1.0",
              description="Ourbit Futures research dashboard — paper mode only")
exchange = OurbitFutures()
FRONTEND = Path(__file__).resolve().parents[2] / "frontend" / "index.html"

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse(FRONTEND.read_text(encoding="utf-8"))

@app.get("/api/health")
async def health():
    return {"ok": True, "project": "ARAD QUANT AI PRO", "mode": "paper"}

@app.get("/api/status")
async def status():
    return exchange.status()

@app.get("/api/market/tickers")
async def market_tickers(symbol: str | None = Query(default=None)):
    try:
        data = await exchange.tickers(symbol)
        return {"source": "ourbit_futures", "data": data}
    except (RuntimeError, Exception) as exc:
        raise HTTPException(status_code=503, detail=f"Market feed unavailable: {exc}")

@app.get("/api/market/candles")
async def market_candles(symbol: str, interval: str = "Min5"):
    allowed = {"Min1", "Min5", "Min15", "Min30", "Min60", "Hour4", "Hour8", "Day1"}
    if interval not in allowed:
        raise HTTPException(status_code=400, detail="Unsupported interval")
    try:
        data = await exchange.candles(symbol.upper(), interval)
        return {"source": "ourbit_futures", "symbol": symbol.upper(),
                "interval": interval, "data": data}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Market feed unavailable: {exc}")

@app.get("/api/signals")
async def signals():
    return {"status": "paper_only", "signals": [],
            "message": "No validated live feed or calibrated strategy; no signals are emitted."}
