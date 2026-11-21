# ARAD QUANT AI PRO

Independent Ourbit Futures research terminal. This repository is separate from ARAD CRYPTO PRO.

## Current stage
- Responsive dark dashboard served by FastAPI.
- Root `main.py` entrypoint for Vercel FastAPI detection.
- Read-only Ourbit Futures public adapter (ping, contract list, ticker, candles).
- 5m primary, 15m confirmation, 1h context.
- No private API key, signed account calls, or order placement.
- Signals remain disabled until candle data and strategy are validated.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```
Open http://127.0.0.1:8000

## Deploy to Vercel
1. Sign in at https://vercel.com/new.
2. Import the GitHub repository `salimy8450/ARAD-QUANT-AI-PRO`.
3. Keep the project root at the repository root. Vercel detects the FastAPI app through `main.py` and `pyproject.toml`.
4. Deploy. No API key or environment secret is needed for public market data.
5. After deployment, open `/api/health`, then `/api/market/connection`.
6. Only if the connection endpoint reports connected should you test `/api/market/contracts` and ticker/candle routes.

## Ourbit public Futures API
The public V1 contract collection published by Ourbit documents:
- `GET /api/v1/contract/ping`
- `GET /api/v1/contract/detail`
- `GET /api/v1/contract/ticker`
- `GET /api/v1/contract/kline/{symbol}?interval=Min5`

The configured default host is `https://contract.ourbit.com`, matching the official collection's hard-coded public Futures examples. A configured host is not proof of connectivity: the ping route must succeed from the deployed service before live status is shown.

## API routes
- `GET /api/health`
- `GET /api/status`
- `GET /api/market/connection`
- `GET /api/market/contracts`
- `GET /api/market/ticker?symbol=BTC_USDT`
- `GET /api/market/candles?symbol=BTC_USDT&interval=Min5`
- `GET /api/signals`

## Safety
Research and paper mode only. No trade execution is implemented. No win rate is promised. Validate candle formats, candle closure, fees/slippage, backtests and forward paper trading before considering real funds. Never commit API secrets.


## ARAD PRE-LISTING HUNTER (new, read-only)
- Open the separate dashboard at `/prelisting`; the main dashboard also includes a shortcut.
- `GET /api/prelisting/health` reports module availability.
- `GET /api/prelisting/scan?since_hours=72&force=true` scans official announcement sources and performs bounded DEX token-pair discovery.
- Current sources: KuCoin public announcements API, MEXC public announcements endpoint, Gate.io official announcements page, and Ourbit official Listing Information category.
- DEX Screener results are discovery leads only. A ticker match is not token identity.
- A result is marked `buyable_verified` only when the announcement contains an EVM contract and network, the DEX pair matches the exact contract on the mapped chain, and GoPlus returns an explicit clean preliminary security record.
- Supported EVM security chain mappings in this first pass: BNB Smart Chain, Ethereum, Base, and Arbitrum. Solana and other networks remain unverified in this version.
- Optional Telegram alerts are sent only for `buyable_verified` items when `ARAD_PRELISTING_BOT_TOKEN` and `ARAD_PRELISTING_CHAT_ID` are configured as deployment environment variables. Do not commit these values.
- No wallet connection, private exchange key, or order execution is used. This module does not promise price appreciation or safe returns. Third-party public endpoints may rate-limit or block serverless requests; each source's status is displayed independently.
