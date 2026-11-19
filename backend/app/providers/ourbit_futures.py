"""Read-only Ourbit Futures public market-data adapter with host failover."""
from __future__ import annotations

import os
import time
from typing import Any

import httpx


class OurbitFutures:
    def __init__(self) -> None:
        configured = os.getenv(
            "OURBIT_FUTURES_BASE_URL", "https://contract.ourbit.com"
        ).strip().rstrip("/")
        # The contract Postman collection documents contract.ourbit.com.
        # futures.ourbit.com is a secondary candidate; it is not assumed live
        # until a real ping succeeds from this deployment.
        candidates = [configured, "https://futures.ourbit.com"]
        self.base_urls = list(dict.fromkeys(url for url in candidates if url))
        self.base_url = self.base_urls[0] if self.base_urls else ""
        self.timeout = float(os.getenv("OURBIT_HTTP_TIMEOUT", "10"))

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.base_urls:
            raise RuntimeError("No Ourbit API base URL configured")
        errors: list[str] = []
        limits = httpx.Limits(max_connections=4, max_keepalive_connections=2)
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=min(self.timeout, 5.0)),
            follow_redirects=True,
            limits=limits,
        ) as client:
            for host in self.base_urls:
                try:
                    response = await client.get(f"{host}{path}", params=params)
                    response.raise_for_status()
                    payload = response.json()
                    if isinstance(payload, dict):
                        if payload.get("success") is False:
                            raise RuntimeError(f"Ourbit API rejected request: {payload}")
                        if payload.get("code") not in (None, 0, 200, "0", "200"):
                            raise RuntimeError(f"Ourbit API returned code: {payload.get('code')}")
                    self.base_url = host
                    return payload
                except httpx.HTTPStatusError as exc:
                    status = exc.response.status_code
                    errors.append(f"{host}: HTTP {status}")
                    # Do not retry client-side errors on another hostname.
                    if status < 500:
                        raise
                except (httpx.HTTPError, OSError, RuntimeError, ValueError) as exc:
                    errors.append(f"{host}: {str(exc)[:180]}")
        raise RuntimeError("All Ourbit API hosts failed: " + " | ".join(errors))

    async def ping(self) -> Any:
        return await self._get("/api/v1/contract/ping")

    async def contracts(self) -> Any:
        return await self._get("/api/v1/contract/detail")

    async def ticker(self, symbol: str | None = None) -> Any:
        # Omitting symbol requests the exchange-wide ticker list.
        params = {"symbol": symbol} if symbol else None
        return await self._get("/api/v1/contract/ticker", params)

    async def market_universe(self) -> dict[str, Any]:
        """Return every active futures contract matched with available ticker data."""
        contracts_payload, ticker_payload = await __import__("asyncio").gather(
            self.contracts(), self.ticker()
        )

        def records(payload: Any) -> list[dict[str, Any]]:
            node = payload
            for _ in range(4):
                if isinstance(node, list):
                    return [x for x in node if isinstance(x, dict)]
                if not isinstance(node, dict):
                    return []
                next_node = None
                for key in ("data", "result", "list", "rows", "items", "contracts", "tickers"):
                    if key in node:
                        next_node = node[key]
                        break
                if next_node is None:
                    return [node] if node.get("symbol") else []
                node = next_node
            return []

        contract_rows = records(contracts_payload)
        ticker_rows = records(ticker_payload)
        ticker_by_symbol = {
            str(row.get("symbol", "")).upper(): row
            for row in ticker_rows if row.get("symbol")
        }
        active, inactive, unknown = [], [], []
        for contract in contract_rows:
            symbol = str(contract.get("symbol") or contract.get("contractCode") or "").upper()
            if not symbol:
                continue
            state = str(contract.get("state") or contract.get("status") or contract.get("contractStatus") or "").upper()
            row = {
                "symbol": symbol,
                "state": state or "UNKNOWN",
                "ticker": ticker_by_symbol.get(symbol),
                "contract": contract,
            }
            if state in {"ENABLED", "TRADING", "1", "ONLINE", "OPEN"}:
                active.append(row)
            elif state in {"DISABLED", "OFFLINE", "CLOSED", "SUSPENDED", "0"}:
                inactive.append(row)
            else:
                unknown.append(row)
        # Unknown status is exposed separately, never silently treated as tradable.
        return {
            "contracts_total": len(contract_rows),
            "active_count": len(active),
            "inactive_count": len(inactive),
            "unknown_status_count": len(unknown),
            "tickers_received": len(ticker_rows),
            "active_contracts": active,
            "scan_candidates": active + unknown,
            "unknown_status_contracts": unknown,
            "inactive_contracts": inactive,
            "source": "Ourbit Futures public contract/detail + contract/ticker",
            "read_only": True,
        }

    async def candles(
        self,
        symbol: str,
        interval: str = "Min5",
        start_ms: int | None = None,
        end_ms: int | None = None,
    ) -> Any:
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
                "tested_hosts": self.base_urls,
                "private_key_required": False,
                "trading_enabled": False,
            }
        except Exception as exc:
            return {
                "connected": False,
                "latency_ms": None,
                "host": self.base_url,
                "tested_hosts": self.base_urls,
                "error": str(exc)[:600],
                "private_key_required": False,
                "trading_enabled": False,
            }

    def status(self) -> dict[str, Any]:
        return {
            "exchange": "Ourbit Futures",
            "host": self.base_url,
            "fallback_hosts": self.base_urls[1:],
            "connection": "not_tested",
            "private_api_key_required_for_public_data": False,
            "trading_enabled": False,
            "mode": "read_only_paper",
        }
