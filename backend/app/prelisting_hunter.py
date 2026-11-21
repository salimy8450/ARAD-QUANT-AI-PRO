"""ARAD Pre-Listing Hunter: read-only official-announcement and DEX discovery.

Important: a ticker match is never treated as proof of token identity. A token is
marked BUYABLE only when an official contract address is present, an exact
address match exists on a DEX pair, and GoPlus returns an explicit clean result.
"""
from __future__ import annotations

import asyncio
import html
import os
import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

EXCHANGES = {
    "KuCoin": {"kind": "api", "url": "https://api.kucoin.com/api/v3/announcements"},
    "MEXC": {"kind": "api", "url": "https://www.mexc.com/api/v3/announcements"},
    "Gate.io": {"kind": "html", "url": "https://www.gate.com/announcements"},
    "Ourbit": {"kind": "html", "url": "https://www.ourbit.com/support/categories/360000254192"},
}
LISTING_WORDS = re.compile(r"\b(list(?:s|ed|ing|ings)?|will list|new listings?|spot trading|trading will start|world premiere|adds? .+ trading pair)\b", re.I)
NON_LISTING_WORDS = re.compile(r"\b(delist(?:ed|ing)?|remove|suspend|maintenance|deposit|withdraw|airdrop|campaign|futures|perpetual)\b", re.I)
SYMBOL_PARENS = re.compile(r"\(([A-Z0-9]{2,15})\)")
CONTRACT_RE = re.compile(r"0x[a-fA-F0-9]{40}")
CHAIN_HINTS = {
    "bsc": 56, "bnb": 56, "binance smart chain": 56,
    "ethereum": 1, "erc20": 1, "eth": 1,
    "base": 8453, "arbitrum": 42161,
}
CACHE_TTL = 45
_cache: dict[str, Any] = {"at": 0.0, "payload": None}
_telegram_seen: set[str] = set()


def _items(payload: Any) -> list[dict[str, Any]]:
    node = payload
    for _ in range(5):
        if isinstance(node, list):
            return [x for x in node if isinstance(x, dict)]
        if not isinstance(node, dict):
            return []
        nxt = next((node.get(k) for k in ("data", "result", "list", "items", "details", "announcements") if isinstance(node.get(k), (dict, list))), None)
        if nxt is None:
            return []
        node = nxt
    return []


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000
        if number > 0:
            return datetime.fromtimestamp(number, timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        pass
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except ValueError:
            return None
    return None


def _looks_like_listing(title: str, description: str = "") -> bool:
    text = f"{title} {description}"
    return bool(LISTING_WORDS.search(text)) and not bool(NON_LISTING_WORDS.search(title))


def _symbols(title: str) -> list[str]:
    found = SYMBOL_PARENS.findall(title.upper())
    if found:
        return list(dict.fromkeys(found))[:8]
    # Conservative fallback: only explicit "TOKEN (TICKER)"-like title tokens.
    match = re.search(r"\b([A-Z][A-Z0-9]{1,14})\s+(?:will be listed|gets listed|is listed)\b", title, re.I)
    return [match.group(1).upper()] if match else []


def _chain_id(text: str) -> int | None:
    value = text.lower()
    if re.search(r"\b(?:bsc|bnb|binance smart chain)\b", value):
        return 56
    if re.search(r"\b(?:ethereum|erc20|eth)\b", value):
        return 1
    if re.search(r"\bbase\b", value):
        return 8453
    if re.search(r"\barbitrum\b", value):
        return 42161
    return None


def _normalise(exchange: str, row: dict[str, Any]) -> dict[str, Any] | None:
    title = str(_first(row, "annTitle", "title", "name", "subject", "text") or "").strip()
    description = str(_first(row, "annDesc", "description", "content", "summary") or "").strip()
    if not title or not _looks_like_listing(title, description):
        return None
    raw_url = _first(row, "annUrl", "url", "link", "articleUrl")
    url = str(raw_url or EXCHANGES[exchange]["url"])
    if url.startswith("/"):
        base = "https://www.kucoin.com" if exchange == "KuCoin" else "https://www.mexc.com" if exchange == "MEXC" else EXCHANGES[exchange]["url"]
        url = urljoin(base, url)
    raw_time = _first(row, "cTime", "releaseTime", "postTime", "createdAt", "publishedAt", "time")
    text_blob = f"{title} {description}"
    contract = CONTRACT_RE.search(text_blob)
    chain = _chain_id(text_blob)
    return {
        "id": str(_first(row, "annId", "id", "articleId") or f"{exchange}:{title}"),
        "exchange": exchange, "title": title, "description": description[:700],
        "url": url, "published_at": _timestamp(raw_time),
        "symbols": _symbols(title), "contract_address": contract.group(0) if contract else None,
        "chain_id": chain, "source_type": "official_exchange_announcement",
        "buyability": "unverified", "score": 0,
        "score_reasons": ["اطلاعیه رسمی شناسایی شد؛ هویت قرارداد و امکان خرید هنوز تأیید نشده است"],
    }


async def _fetch_kucoin(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await client.get(EXCHANGES["KuCoin"]["url"], params={
        "currentPage": 1, "pageSize": 50, "annType": "new-listings", "lang": "en_US"
    })
    response.raise_for_status()
    payload = response.json()
    if str(payload.get("code")) not in {"200000", "200"}:
        raise RuntimeError(f"KuCoin API code: {payload.get('code')}")
    return [x for row in _items(payload) if (x := _normalise("KuCoin", row))]


async def _fetch_mexc(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    # MEXC's public announcement endpoint is documented as /api/v3/announcements.
    response = await client.get("https://www.mexc.com/api/v3/announcements", params={
        "language": "en-US", "page": 1, "limit": 50
    })
    response.raise_for_status()
    payload = response.json()
    return [x for row in _items(payload) if (x := _normalise("MEXC", row))]


async def _fetch_html_exchange(client: httpx.AsyncClient, exchange: str) -> list[dict[str, Any]]:
    url = EXCHANGES[exchange]["url"]
    response = await client.get(url, headers={"User-Agent": "ARAD-PreListingResearch/1.0"})
    response.raise_for_status()
    source = response.text[:2_000_000]
    rows: list[dict[str, Any]] = []
    # Extract only visible anchor text + official same-domain links. JS-only pages
    # may return no rows; that is reported as unavailable rather than guessed.
    for match in re.finditer(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', source, re.I | re.S):
        href, raw_title = match.group(1), match.group(2)
        title = html.unescape(re.sub(r"<[^>]+>", " ", raw_title))
        title = re.sub(r"\s+", " ", title).strip()
        if not title or not _looks_like_listing(title):
            continue
        full_url = urljoin(url, html.unescape(href))
        if urlparse(full_url).netloc.lower() != urlparse(url).netloc.lower():
            continue
        context = source[max(0, match.start() - 250):min(len(source), match.end() + 250)]
        date_match = re.search(r"20\d{2}-\d{2}-\d{2}", context)
        row = _normalise(exchange, {"title": title, "url": full_url, "publishedAt": date_match.group(0) if date_match else None})
        if row:
            rows.append(row)
    return rows[:50]


async def _fetch_article_contract(client: httpx.AsyncClient, item: dict[str, Any]) -> None:
    """Read an announcement detail page only on the exchange's own domain."""
    host = (urlparse(str(item.get("url") or "")).hostname or "").lower()
    allowed = {
        "KuCoin": ("kucoin.com",), "MEXC": ("mexc.com",),
        "Gate.io": ("gate.com",), "Ourbit": ("ourbit.com",),
    }.get(str(item.get("exchange")), ())
    if not host or not any(host == domain or host.endswith("." + domain) for domain in allowed):
        return
    try:
        response = await client.get(str(item["url"]), headers={"User-Agent": "ARAD-PreListingResearch/1.0"})
        response.raise_for_status()
        body = html.unescape(re.sub(r"<[^>]+>", " ", response.text[:1_500_000]))
        body = re.sub(r"\s+", " ", body)
        if not item.get("contract_address"):
            labelled = re.search(
                r"(?:token\s+)?contract(?:\s+address)?\s*[:：#-]?\s*(0x[a-fA-F0-9]{40})",
                body, re.I
            )
            if labelled:
                item["contract_address"] = labelled.group(1)
        if not item.get("chain_id"):
            item["chain_id"] = _chain_id(body)
        if not item.get("description"):
            item["description"] = body[:650]
    except Exception:
        return


async def _dex_pairs(client: httpx.AsyncClient, symbol: str) -> list[dict[str, Any]]:
    response = await client.get("https://api.dexscreener.com/latest/dex/search", params={"q": symbol})
    response.raise_for_status()
    payload = response.json()
    pairs = payload.get("pairs") or []
    exact = []
    for pair in pairs:
        base = pair.get("baseToken") or {}
        if str(base.get("symbol", "")).upper() != symbol.upper():
            continue
        exact.append({
            "chain_id": pair.get("chainId"), "dex_id": pair.get("dexId"),
            "pair_address": pair.get("pairAddress"),
            "base_symbol": base.get("symbol"), "base_name": base.get("name"),
            "base_token_address": base.get("address"),
            "price_usd": pair.get("priceUsd"),
            "liquidity_usd": (pair.get("liquidity") or {}).get("usd"),
            "volume_24h_usd": (pair.get("volume") or {}).get("h24"),
            "url": pair.get("url"),
        })
    return exact[:8]


async def _verify_contract(client: httpx.AsyncClient, chain_id: int, address: str) -> dict[str, Any]:
    response = await client.get(
        f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}",
        params={"contract_addresses": address}
    )
    response.raise_for_status()
    payload = response.json()
    record = (payload.get("result") or {}).get(address.lower()) or (payload.get("result") or {}).get(address)
    if not isinstance(record, dict):
        return {"verified": False, "reason": "GoPlus did not return a security record"}
    flags = ("is_honeypot", "cannot_sell_all", "is_mintable", "owner_change_balance")
    bad = [key for key in flags if str(record.get(key, "unknown")).lower() not in {"0", "false"}]
    try:
        sell_tax = float(record.get("sell_tax", 0) or 0)
    except (TypeError, ValueError):
        sell_tax = 100.0
    if sell_tax > 10:
        bad.append("sell_tax")
    return {"verified": not bad, "flags": {key: record.get(key) for key in flags},
            "sell_tax": sell_tax, "holders": record.get("holder_count"),
            "reason": "security flags clear" if not bad else "risk flags: " + ", ".join(bad)}


async def _enrich(client: httpx.AsyncClient, item: dict[str, Any]) -> None:
    await _fetch_article_contract(client, item)
    symbol_list = item.get("symbols") or []
    if not symbol_list:
        item["score_reasons"].append("نماد از عنوان قابل استخراج نبود")
        return
    # Discovery results are only leads until contract address and chain match exactly.
    try:
        pair_results = await asyncio.gather(*(_dex_pairs(client, s) for s in symbol_list[:3]), return_exceptions=True)
        candidates = [p for group in pair_results if isinstance(group, list) for p in group]
        item["dex_candidates"] = candidates[:8]
    except Exception:
        item["dex_candidates"] = []
    address, chain_id = item.get("contract_address"), item.get("chain_id")
    if not address or not chain_id:
        item["buyability"] = "unverified"
        item["score"] = 40
        item["score_reasons"].append("قرارداد رسمی یا شبکه در اطلاعیه پیدا نشد؛ تطبیق نماد DEX به‌تنهایی کافی نیست")
        return
    dex_chain = {56: "bsc", 1: "ethereum", 8453: "base", 42161: "arbitrum"}.get(int(chain_id))
    exact = [p for p in item.get("dex_candidates", []) if p["base_token_address"].lower() == address.lower() and (not dex_chain or str(p.get("chain_id", "")).lower() == dex_chain)]
    if not exact:
        item["buyability"] = "not_found"
        item["score"] = 45
        item["score_reasons"].append("جفت معاملاتی با آدرس قرارداد دقیق در DEX پیدا نشد")
        return
    min_liquidity = float(os.getenv("ARAD_PRELISTING_MIN_LIQUIDITY_USD", "10000"))
    liquid_pairs = []
    for pair in exact:
        try:
            if float(pair.get("liquidity_usd") or 0) >= min_liquidity:
                liquid_pairs.append(pair)
        except (TypeError, ValueError):
            continue
    if not liquid_pairs:
        item["buyability"] = "rejected"
        item["score"] = 0
        item["score_reasons"] = [f"نقدینگی DEX کمتر از حداقل ${min_liquidity:,.0f} یا نامشخص است"]
        return
    exact = liquid_pairs
    try:
        security = await _verify_contract(client, int(chain_id), address)
        item["security"] = security
        if security.get("verified"):
            item["buyability"] = "buyable_verified"
            item["score"] = 85
            item["score_reasons"] = ["اطلاعیه رسمی", "قرارداد با جفت DEX تطبیق دقیق دارد", "بررسی امنیت اولیه GoPlus بدون پرچم خطر"]
            item["matched_pair"] = exact[0]
        else:
            item["buyability"] = "rejected"
            item["score"] = 0
            item["score_reasons"] = [security.get("reason", "ریسک قرارداد")]
    except Exception as exc:
        item["buyability"] = "unverified"
        item["score"] = 45
        item["score_reasons"].append("بررسی امنیت انجام نشد: " + str(exc)[:120])


async def _send_telegram_alerts(client: httpx.AsyncClient, items: list[dict[str, Any]]) -> dict[str, Any]:
    token = os.getenv("ARAD_PRELISTING_BOT_TOKEN", "").strip()
    chat_id = os.getenv("ARAD_PRELISTING_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"configured": False, "sent": 0, "note": "Telegram credentials are not configured"}
    sent = 0
    for item in items:
        if item.get("buyability") != "buyable_verified" or str(item.get("id")) in _telegram_seen:
            continue
        pair = item.get("matched_pair") or {}
        message = (
            "ARAD PRE-LISTING HUNTER\n"
            f"Verified pre-listing market: {item.get('exchange')}\n"
            f"Token: {', '.join(item.get('symbols') or [])}\n"
            f"DEX: {pair.get('chain_id')} / {pair.get('dex_id')}\n"
            f"Liquidity USD: {pair.get('liquidity_usd', 'n/a')}\n"
            f"Announcement: {item.get('url')}\n"
            "Read-only alert; not a buy instruction."
        )
        try:
            response = await client.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                         json={"chat_id": chat_id, "text": message})
            response.raise_for_status()
            if response.json().get("ok"):
                _telegram_seen.add(str(item.get("id")))
                sent += 1
        except Exception:
            continue
    return {"configured": True, "sent": sent}


class PreListingHunter:
    async def scan(self, since_hours: int = 72, force: bool = False) -> dict[str, Any]:
        now = time.time()
        if not force and _cache["payload"] is not None and now - _cache["at"] < CACHE_TTL:
            return _cache["payload"]
        timeout = httpx.Timeout(12.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                                     headers={"Accept": "application/json,text/html,*/*"}) as client:
            tasks = {
                "KuCoin": _fetch_kucoin(client),
                "MEXC": _fetch_mexc(client),
                "Gate.io": _fetch_html_exchange(client, "Gate.io"),
                "Ourbit": _fetch_html_exchange(client, "Ourbit"),
            }
            names = list(tasks)
            results = await asyncio.gather(*tasks.values(), return_exceptions=True)
            source_status = {}
            items: list[dict[str, Any]] = []
            for name, result in zip(names, results):
                if isinstance(result, Exception):
                    source_status[name] = {"ok": False, "error": str(result)[:220], "count": 0}
                else:
                    source_status[name] = {"ok": True, "count": len(result), "method": EXCHANGES[name]["kind"]}
                    items.extend(result)
            cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, min(since_hours, 720)))
            filtered = []
            for item in items:
                published = item.get("published_at")
                if published:
                    try:
                        if datetime.fromisoformat(published) < cutoff:
                            continue
                    except ValueError:
                        pass
                filtered.append(item)
            # Enrich a bounded set to protect public API rate limits.
            await asyncio.gather(*(_enrich(client, item) for item in filtered[:30]), return_exceptions=True)
            filtered.sort(key=lambda x: (x.get("score", 0), x.get("published_at") or ""), reverse=True)
            telegram_status = await _send_telegram_alerts(client, filtered)
            payload = {
                "status": "completed" if any(x.get("ok") for x in source_status.values()) else "sources_unavailable",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "window_hours": since_hours, "sources": source_status, "telegram": telegram_status,
                "total_announcements": len(filtered),
                "buyable_verified": sum(x.get("buyability") == "buyable_verified" for x in filtered),
                "unverified": sum(x.get("buyability") == "unverified" for x in filtered),
                "rejected": sum(x.get("buyability") == "rejected" for x in filtered),
                "items": filtered,
                "safety_note": "نماد یکسان به معنی توکن یکسان نیست. خرید فقط پس از تطبیق آدرس قرارداد و بررسی امنیت قابل بررسی است؛ این ابزار سفارش ثبت نمی‌کند."
            }
            _cache.update({"at": now, "payload": payload})
            return payload


hunter = PreListingHunter()
