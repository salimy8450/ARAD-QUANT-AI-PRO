# ARAD QUANT AI PRO

Independent Ourbit Futures research terminal. This repository is separate from ARAD CRYPTO PRO.

## Current stage
- Dark responsive dashboard.
- FastAPI backend.
- Read-only Ourbit Futures public adapter (ping, contract list, ticker, candles).
- Timeframe interface supports 5m primary, 15m confirmation, 1h context.
- No private API key, signed account calls, or order placement.
- Signal generation remains disabled until live data and candle schemas are verified.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```
Open http://127.0.0.1:8000

## Public market endpoints used
The adapter follows the published Ourbit V1 contract Postman collection paths:
- `GET /api/v1/contract/ping`
- `GET /api/v1/contract/detail`
- `GET /api/v1/contract/ticker`
- `GET /api/v1/contract/kline/{symbol}?interval=Min5`

The host is configurable via `OURBIT_FUTURES_BASE_URL`. The documented Postman environment did not provide a verified host value, so successful connectivity must be confirmed by calling `/api/market/connection` after deployment. Do not assume a configured URL means the feed is connected.

## API routes
- `GET /api/health`
- `GET /api/status`
- `GET /api/market/connection`
- `GET /api/market/contracts`
- `GET /api/market/ticker?symbol=BTC_USDT`
- `GET /api/market/candles?symbol=BTC_USDT&interval=Min5`
- `GET /api/signals`

## Safety
Research and paper mode only. No trade execution is implemented. No win rate is promised. Before any live use, validate data, candle closure, fees/slippage, backtests and forward paper trading. Never commit API secrets.
