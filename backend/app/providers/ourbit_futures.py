"""Ourbit Futures public market-data adapter.

Paths are based on Ourbit's published V1 contract Postman collection.
This adapter is read-only: no account endpoints, signatures, or order routes.
The API host is configurable because endpoint reachability must be checked
from the eventual deployment region before declaring the feed live.
"""
from __future__ import annotations

import os
import time
from typing import Any
import httpx


class OurbitFutures:
    def __init__(self) -> None:
        self.base_url = os.getenv(
            "OURBIT_FUTURES_BASE_URL", "https://contract.ourbit.com"
        ).strip().rstrip("/")
        self.timeout = float(os.getenv("OURBIT_HTTP_TIMEOUT", "8"))

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.base_url:
            raise RuntimeError("OURBIT_FUTURES_BASE_URL is empty")
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("success") is False:
                raise RuntimeError(f"Ourbit API rejected request: {payload}")
            return payload

    async def ping(self) -> Any:
        return await self._get("/api/v1/contract/ping")

    async def contracts(self) -> Any:
        return await self._get("/api/v1/contract/detail")

    async def ticker(self, symbol: str | None = None) -> Any:
        params = {"symbol": symbol} if symbol else None
        return await self._get("/api/v1/contract/ticker", params)

    async def candles(self, symbol: str, interval: str = "Min5",
                      start_ms: int | None = None, end_ms: int | None = None) -> Any:
        params: dict[str, Any] = {"interval": interval}
        if start_ms is not None:
            params["start"] = start_ms
        if end_ms is not None:
            params["end"] = end_ms
        return await self._get(f"/api/v1/contract/kline/{symbol}", params)

    async def check_connection(self) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            data = await self.ping()
            return {
                "connected": True,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "host": self.base_url,
                "ping_response": data,
                "private_key_required": False,
                "trading_enabled": False,
            }
        except Exception as exc:
            return {
                "connected": False,
                "latency_ms": None,
                "host": self.base_url,
                "error": str(exc)[:300],
                "private_key_required": False,
                "trading_enabled": False,
            }

    def status(self) -> dict[str, Any]:
        return {
            "exchange": "Ourbit Futures",
            "host": self.base_url,
            "connection": "not_tested",
            "private_api_key_required_for_public_data": False,
            "trading_enabled": False,
            "mode": "read_only_paper",
        }
