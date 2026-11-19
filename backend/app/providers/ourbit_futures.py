"""Ourbit Futures public market-data adapter.

The official Ourbit Postman contract collection documents endpoints under
/api/v1/contract. The host/availability and response schemas must be verified
against the live Futures service before enabling this adapter. No private key
is used for public market-data routes.
"""
from __future__ import annotations

import os
from typing import Any
import httpx


class OurbitFutures:
    def __init__(self) -> None:
        self.base_url = os.getenv("OURBIT_FUTURES_BASE_URL", "").strip().rstrip("/")
        self.enabled = os.getenv("OURBIT_PUBLIC_FEED_ENABLED", "false").lower() == "true"

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.enabled or not self.base_url:
            raise RuntimeError("Ourbit Futures feed is not enabled or configured")
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            return response.json()

    async def ping(self) -> Any:
        return await self._get("/api/v1/contract/ping")

    async def contracts(self) -> Any:
        return await self._get("/api/v1/contract/detail")

    async def tickers(self, symbol: str | None = None) -> Any:
        params = {"symbol": symbol} if symbol else None
        return await self._get("/api/v1/contract/ticker", params)

    async def candles(self, symbol: str, interval: str = "Min5",
                      start: int | None = None, end: int | None = None) -> Any:
        params: dict[str, Any] = {"interval": interval}
        if start is not None:
            params["start"] = start
        if end is not None:
            params["end"] = end
        return await self._get(f"/api/v1/contract/kline/{symbol}", params)

    def status(self) -> dict[str, Any]:
        return {
            "exchange": "Ourbit Futures",
            "enabled": self.enabled and bool(self.base_url),
            "base_url_configured": bool(self.base_url),
            "private_api_key_required_for_public_data": False,
            "trading_enabled": False,
        }
