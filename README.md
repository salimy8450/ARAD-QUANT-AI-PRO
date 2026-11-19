# ARAD QUANT AI PRO

Independent Ourbit Futures research terminal. This repository is separate from ARAD CRYPTO PRO.

## Phase 1
- Responsive dark quant dashboard.
- FastAPI backend.
- Public-data adapter boundary for Ourbit Futures.
- 5m primary, 15m confirmation, 1h context.
- Paper/research mode only. No order placement and no private API key.
- No fabricated market prices or signals: if the feed is unavailable, the UI reports disconnected.

## Run locally
```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```
Open http://127.0.0.1:8000

## Environment
Copy `.env.example` to `.env`. The Futures host is deliberately not enabled until connectivity and response schemas are verified against Ourbit's current official Futures API. Do not paste API secrets into source code or GitHub.

## Safety
This is research software, not financial advice. Signals require historical validation, fee/slippage modelling and paper trading before any real-money use.
