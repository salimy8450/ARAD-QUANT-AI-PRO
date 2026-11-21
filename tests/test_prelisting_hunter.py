from backend.app.prelisting_hunter import _items, _looks_like_listing, _normalise, _symbols, _timestamp


def test_nested_kucoin_announcement_payload():
    payload = {"code": "200000", "data": {"items": [{"annTitle": "ABC (ABC) Gets Listed!", "annId": 12}]}}
    assert len(_items(payload)) == 1


def test_listing_detection_and_delisting_rejection():
    assert _looks_like_listing("Ourbit Will List CORA (CORA) in the Innovation Zone")
    assert not _looks_like_listing("Ourbit Will Delist CORA (CORA) from Spot")


def test_symbol_extraction_is_conservative():
    assert _symbols("CORA (CORA) Gets Listed!") == ["CORA"]
    assert _symbols("A token is coming soon") == []


def test_announcement_normalisation_requires_listing_language():
    row = _normalise("Ourbit", {"title": "Ourbit Will List CORA (CORA)", "url": "https://www.ourbit.com/support/articles/1"})
    assert row is not None
    assert row["exchange"] == "Ourbit"
    assert row["symbols"] == ["CORA"]
    assert row["buyability"] == "unverified"
    assert row["contract_address"] is None


def test_timestamp_handles_milliseconds_and_iso():
    assert _timestamp(1760000000000).startswith("2025-")
    assert _timestamp("2026-11-21T12:00:00Z").startswith("2026-11-21")
