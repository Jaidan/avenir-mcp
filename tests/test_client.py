# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Tests for client.py — YNAB API wrapper."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from avenir_mcp import client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(payload: Any, status_code: int = 200) -> MagicMock:
    """Build a mock httpx response that returns *payload* as JSON, with no header."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = payload
    mock_resp.headers = {}
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


def _async_client_returning(payload: Any) -> MagicMock:
    """Return a context-manager mock whose .get(), .patch(), .post() and .delete() yield it."""
    mock_resp = _mock_response(payload)
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    mock_http.patch = AsyncMock(return_value=mock_resp)
    mock_http.delete = AsyncMock(return_value=mock_resp)
    mock_http.post = AsyncMock(return_value=mock_resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_http)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


# ---------------------------------------------------------------------------
# milliunit_to_amount
# ---------------------------------------------------------------------------


def test_milliunit_to_amount_positive() -> None:
    """500 000 milliunits should equal 500.0."""
    assert client.milliunit_to_amount(500_000) == 500.0


def test_milliunit_to_amount_negative() -> None:
    """-75 000 milliunits should equal -75.0."""
    assert client.milliunit_to_amount(-75_000) == -75.0


def test_milliunit_to_amount_zero() -> None:
    """0 milliunits should equal 0.0."""
    assert client.milliunit_to_amount(0) == 0.0


# ---------------------------------------------------------------------------
# _api_key
# ---------------------------------------------------------------------------


def test_api_key_raises_when_missing() -> None:
    """Should raise RuntimeError if YNAB_API_KEY is not set."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(RuntimeError, match="YNAB_API_KEY"):
            client._api_key()  # pylint: disable=protected-access


def test_api_key_never_shows_when_printed() -> None:
    """The key read from the environment prints as a mask, in a repr or an f-string."""
    with patch.dict("os.environ", {"YNAB_API_KEY": "tok_abc"}):
        key = client._api_key()  # pylint: disable=protected-access
    assert "tok_abc" not in f"{key!r} {key}"


def test_api_key_returns_env_value() -> None:
    """Should return the value of YNAB_API_KEY."""
    with patch.dict("os.environ", {"YNAB_API_KEY": "tok_abc"}):
        assert client._api_key().get_secret_value() == "tok_abc"  # pylint: disable=protected-access


# ---------------------------------------------------------------------------
# get_plans
# ---------------------------------------------------------------------------


def test_get_budgets_returns_list() -> None:
    """get_plans should return the budgets list from the API payload."""
    payload = {"data": {"plans": [{"id": "b1", "name": "Business"}]}}
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.get_plans())
    assert result == [{"id": "b1", "name": "Business"}]


# ---------------------------------------------------------------------------
# get_categories
# ---------------------------------------------------------------------------


def test_get_categories_flattens_groups() -> None:
    """get_categories should return a flat list of non-hidden categories."""
    payload = {
        "data": {
            "category_groups": [
                {
                    "id": "g1",
                    "categories": [
                        {"id": "c1", "name": "Rent", "hidden": False},
                        {"id": "c2", "name": "Old", "hidden": True},
                    ],
                },
                {
                    "id": "g2",
                    "categories": [
                        {"id": "c3", "name": "AWS", "hidden": False},
                    ],
                },
            ]
        }
    }
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.get_categories("last-used"))
    assert len(result) == 2
    assert result[0]["id"] == "c1"
    assert result[1]["id"] == "c3"


# ---------------------------------------------------------------------------
# get_transactions — filters and delta sync
# ---------------------------------------------------------------------------


def test_get_transactions_uncategorized_passes_type_param() -> None:
    """uncategorized_only=True should add type=uncategorized to query params."""
    payload = {"data": {"transactions": [], "server_knowledge": 5}}
    mock_resp = _mock_response(payload)
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_http)
    ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            asyncio.run(client.get_transactions("b1", uncategorized_only=True))

    call_kwargs = mock_http.get.call_args
    assert call_kwargs.kwargs["params"].get("type") == "uncategorized"


def test_get_transactions_delta_sync_uses_cached_knowledge() -> None:
    """Second call for same budget should pass last_knowledge_of_server."""
    payload = {"data": {"transactions": [{"id": "t1"}], "server_knowledge": 42}}
    ctx = _async_client_returning(payload)

    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            # First call populates cache
            asyncio.run(client.get_transactions("b1"))

    # Second call should use server_knowledge=42
    mock_resp2 = _mock_response({"data": {"transactions": [], "server_knowledge": 43}})
    mock_http2 = AsyncMock()
    mock_http2.get = AsyncMock(return_value=mock_resp2)
    ctx2 = MagicMock()
    ctx2.__aenter__ = AsyncMock(return_value=mock_http2)
    ctx2.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=ctx2):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            asyncio.run(client.get_transactions("b1"))

    call_kwargs = mock_http2.get.call_args
    assert call_kwargs.kwargs["params"].get("last_knowledge_of_server") == 42


def _get_transactions_twice(
    first: list[dict[str, Any]], delta: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Load a budget's transactions, then reload it when YNAB returns only `delta`."""
    with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
        payload = {"data": {"transactions": first, "server_knowledge": 1}}
        with patch("httpx.AsyncClient", return_value=_async_client_returning(payload)):
            asyncio.run(client.get_transactions("b1"))
        payload = {"data": {"transactions": delta, "server_knowledge": 2}}
        with patch("httpx.AsyncClient", return_value=_async_client_returning(payload)):
            return asyncio.run(client.get_transactions("b1"))


def test_get_transactions_delta_sync_returns_full_list_when_nothing_changed() -> None:
    """An empty delta means nothing changed, not that the budget is empty."""
    first = [{"id": "t1", "deleted": False}, {"id": "t2", "deleted": False}]
    assert _get_transactions_twice(first, []) == first


def test_get_transactions_delta_sync_merges_changes() -> None:
    """A delta updates changed transactions, adds new ones and drops deleted ones."""
    first = [
        {"id": "t1", "memo": "old", "deleted": False},
        {"id": "t2", "deleted": False},
    ]
    delta = [
        {"id": "t1", "memo": "new", "deleted": False},
        {"id": "t2", "deleted": True},
        {"id": "t3", "deleted": False},
    ]
    assert _get_transactions_twice(first, delta) == [
        {"id": "t1", "memo": "new", "deleted": False},
        {"id": "t3", "deleted": False},
    ]


def test_get_month_returns_month_dict() -> None:
    """get_month should return the 'month' key from the API response."""
    payload = {
        "data": {
            "month": {
                "month": "2026-04-01",
                "budgeted": 5_000_000,
                "activity": -3_200_000,
                "balance": 1_800_000,
                "income": 8_000_000,
                "overspend": 0,
                "categories": [],
            }
        }
    }
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.get_month("b1", "2026-04-01"))
    assert result["month"] == "2026-04-01"
    assert result["budgeted"] == 5_000_000


def test_get_month_categories_flattens_nested_groups() -> None:
    """get_month_categories should flatten categories from nested group dicts."""
    month_payload = {
        "data": {
            "month": {
                "month": "2026-04-01",
                "budgeted": 0,
                "activity": 0,
                "balance": 0,
                "income": 0,
                "overspend": 0,
                "categories": [
                    {
                        "id": "g1",
                        "categories": [
                            {"id": "c1", "name": "Rent", "budgeted": 500_000},
                            {"id": "c2", "name": "AWS", "budgeted": 200_000},
                        ],
                    }
                ],
            }
        }
    }
    ctx = _async_client_returning(month_payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.get_month_categories("b1", "2026-04-01"))
    assert len(result) == 2
    assert result[0]["id"] == "c1"


def test_get_month_categories_flat_list() -> None:
    """get_month_categories handles a flat category list (no nested groups)."""
    month_payload = {
        "data": {
            "month": {
                "month": "2026-04-01",
                "budgeted": 0,
                "activity": 0,
                "balance": 0,
                "income": 0,
                "overspend": 0,
                "categories": [
                    {"id": "c1", "name": "Rent", "budgeted": 500_000},
                ],
            }
        }
    }
    ctx = _async_client_returning(month_payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.get_month_categories("b1", "2026-04-01"))
    assert len(result) == 1
    assert result[0]["id"] == "c1"


def test_get_transactions_with_since_date_skips_delta_sync() -> None:
    """Passing since_date should add the date param and NOT use delta sync."""
    payload = {"data": {"transactions": [{"id": "t5"}], "server_knowledge": 10}}
    mock_resp = _mock_response(payload)
    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_http)
    ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.get_transactions("b1", since_date="2026-01-01"))

    assert result == [{"id": "t5"}]
    call_kwargs = mock_http.get.call_args
    assert call_kwargs.kwargs["params"].get("since_date") == "2026-01-01"
    assert "last_knowledge_of_server" not in call_kwargs.kwargs["params"]


def test_get_months_returns_list() -> None:
    """get_months should return the months list from the API payload."""
    payload = {"data": {"months": [{"month": "2026-03-01"}, {"month": "2026-04-01"}]}}
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.get_months("b1"))
    assert result == [{"month": "2026-03-01"}, {"month": "2026-04-01"}]


# ---------------------------------------------------------------------------
# get_category_groups / create_category
# ---------------------------------------------------------------------------


def test_get_category_groups_skips_hidden_deleted_and_internal() -> None:
    """get_category_groups returns only user-visible groups, without their categories."""
    payload = {
        "data": {
            "category_groups": [
                {
                    "id": "g0",
                    "name": "Internal Master Category",
                    "hidden": False,
                    "deleted": False,
                    "categories": [],
                },
                {
                    "id": "g1",
                    "name": "Software",
                    "hidden": False,
                    "deleted": False,
                    "categories": [{"id": "c1"}],
                },
                {
                    "id": "g2",
                    "name": "Archived",
                    "hidden": True,
                    "deleted": False,
                    "categories": [],
                },
                {
                    "id": "g4",
                    "name": "Credit Card Payments",
                    "hidden": False,
                    "deleted": False,
                    "categories": [],
                },
                {
                    "id": "g5",
                    "name": "Hidden Categories",
                    "hidden": False,
                    "deleted": False,
                    "categories": [],
                },
                {
                    "id": "g3",
                    "name": "Deleted",
                    "hidden": False,
                    "deleted": True,
                    "categories": [],
                },
            ]
        }
    }
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.get_category_groups("b1"))
    assert result == [{"id": "g1", "name": "Software"}]


def test_create_category_posts_name_and_group() -> None:
    """create_category should POST {category: {name, category_group_id}}."""
    payload = {"data": {"category": {"id": "c42", "name": "Miscellaneous"}, "server_knowledge": 7}}
    mock_resp = _mock_response(payload)
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_http)
    ctx.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.create_category("b1", "g1", "Miscellaneous"))

    assert result == {"id": "c42", "name": "Miscellaneous"}
    assert mock_http.post.call_args.args[0].endswith("/plans/b1/categories")
    sent_json = mock_http.post.call_args.kwargs["json"]
    assert sent_json == {"category": {"name": "Miscellaneous", "category_group_id": "g1"}}


# ---------------------------------------------------------------------------
# set_category_budgeted / get_accounts
# ---------------------------------------------------------------------------


def test_set_category_budgeted_patches_month_category_in_milliunits() -> None:
    """set_category_budgeted should PATCH {category: {budgeted: milliunits}} for that month."""
    payload = {"data": {"category": {"id": "c1", "budgeted": 1890000}}}
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.set_category_budgeted("b1", "2026-09-01", "c1", 1890.0))
    http = ctx.__aenter__.return_value
    assert result == {"id": "c1", "budgeted": 1890000}
    assert http.patch.call_args.args[0].endswith("/plans/b1/months/2026-09-01/categories/c1")
    assert http.patch.call_args.kwargs["json"] == {"category": {"budgeted": 1890000}}


def test_set_category_budgeted_rounds_cents_exactly() -> None:
    """Float amounts like 111.32 must become exactly 111320 milliunits (no 111319)."""
    payload = {"data": {"category": {"id": "c1"}}}
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            asyncio.run(client.set_category_budgeted("b1", "current", "c1", 111.32))
    sent = ctx.__aenter__.return_value.patch.call_args.kwargs["json"]
    assert sent == {"category": {"budgeted": 111320}}


def test_get_accounts_skips_deleted_and_converts_balances() -> None:
    """get_accounts returns open and closed (not deleted) accounts with euro balances."""
    payload = {
        "data": {
            "accounts": [
                {
                    "id": "a1",
                    "name": "Checking",
                    "type": "checking",
                    "on_budget": True,
                    "closed": False,
                    "deleted": False,
                    "balance": 1250000,
                    "cleared_balance": 1250000,
                    "uncleared_balance": 0,
                },
                {
                    "id": "a2",
                    "name": "Old",
                    "type": "savings",
                    "on_budget": True,
                    "closed": False,
                    "deleted": True,
                    "balance": 0,
                    "cleared_balance": 0,
                    "uncleared_balance": 0,
                },
            ]
        }
    }
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.get_accounts("b1"))
    assert result == [
        {
            "id": "a1",
            "name": "Checking",
            "type": "checking",
            "on_budget": True,
            "closed": False,
            "balance": 1250.0,
            "cleared_balance": 1250.0,
            "uncleared_balance": 0.0,
            "bank_link": "none",
            "last_reconciled": None,
        },
    ]


# ---------------------------------------------------------------------------
# create_transactions
# ---------------------------------------------------------------------------


def test_create_transactions_posts_milliunits_and_reports_duplicates() -> None:
    """create_transactions should POST cleared transactions in milliunits and summarise."""
    payload = {
        "data": {
            "transaction_ids": ["t1"],
            "duplicate_import_ids": ["dup-1"],
            "transactions": [{"id": "t1"}],
        }
    }
    mock_resp = _mock_response(payload)
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_http)
    ctx.__aexit__ = AsyncMock(return_value=None)
    items = [
        {
            "date": "2026-07-01",
            "amount": -3500.0,
            "payee_name": "Jane Doe",
            "memo": "Salary",
            "category_id": "c1",
            "import_id": "q-1",
        },
        {"date": "2026-07-01", "amount": 4321.0, "payee_name": "Acme Corp", "import_id": "dup-1"},
    ]

    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.create_transactions("b1", "a1", items))

    assert result == {"created": 1, "transaction_ids": ["t1"], "duplicate_import_ids": ["dup-1"]}
    assert mock_http.post.call_args.args[0].endswith("/plans/b1/transactions")
    sent = mock_http.post.call_args.kwargs["json"]["transactions"]
    assert sent[0] == {
        "account_id": "a1",
        "date": "2026-07-01",
        "amount": -3500000,
        "payee_name": "Jane Doe",
        "memo": "Salary",
        "category_id": "c1",
        "import_id": "q-1",
        "cleared": "cleared",
        "approved": True,
    }
    assert sent[1] == {
        "account_id": "a1",
        "date": "2026-07-01",
        "amount": 4321000,
        "payee_name": "Acme Corp",
        "import_id": "dup-1",
        "cleared": "cleared",
        "approved": True,
    }


# ---------------------------------------------------------------------------
# error reporting
# ---------------------------------------------------------------------------


def test_api_error_includes_ynab_detail() -> None:
    """A 4xx from YNAB must surface YNAB's error detail, not just the status code."""
    error = {"error": {"id": "400", "name": "bad_request", "detail": "payee name is reserved"}}
    mock_resp = _mock_response(error, status_code=400)
    mock_http = AsyncMock()
    mock_http.post = AsyncMock(return_value=mock_resp)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_http)
    ctx.__aexit__ = AsyncMock(return_value=None)
    items = [{"date": "2026-07-01", "amount": 1.0, "payee_name": "X"}]

    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            with pytest.raises(RuntimeError, match="400.*payee name is reserved"):
                asyncio.run(client.create_transactions("b1", "a1", items))


# ---------------------------------------------------------------------------
# YNAB's rate limit: 200 requests per hour and per token, over a rolling window
# ---------------------------------------------------------------------------


def _plans_client(status_code: int = 200) -> tuple[MagicMock, AsyncMock]:
    payload: Any = {"data": {"plans": []}}
    if status_code == 429:
        payload = {
            "error": {"id": "429", "name": "too_many_requests", "detail": "Too many requests"}
        }
    ctx = _async_client_returning(None)
    get = AsyncMock(return_value=_mock_response(payload, status_code))
    ctx.__aenter__.return_value.get = get
    return ctx, get


def _plans(ctx: MagicMock, clock: float) -> Any:
    with (
        patch("httpx.AsyncClient", return_value=ctx),
        patch.dict("os.environ", {"YNAB_API_KEY": "tok"}),
        patch("avenir_mcp.client.time.monotonic", return_value=clock),
    ):
        return asyncio.run(client.get_plans())


def test_a_429_is_not_retried_and_pauses_every_request() -> None:
    """Too many requests: say so, retry nothing, and send nothing more for ten minutes."""
    ctx, get = _plans_client(429)
    with pytest.raises(RuntimeError, match="200 requests per hour.*10 minutes"):
        _plans(ctx, 1000.0)
    assert get.await_count == 1
    ok, sent = _plans_client()
    with pytest.raises(RuntimeError, match="Nothing was sent.*10 minute"):
        _plans(ok, 1000.0 + 1)
    with pytest.raises(RuntimeError, match="1 minute"):
        _plans(ok, 1000.0 + 599)
    assert sent.await_count == 0
    assert _plans(ok, 1000.0 + 600) == []
    assert sent.await_count == 1


def test_requests_stop_short_of_ynabs_limit() -> None:
    """After 180 requests in an hour, the next waits for the oldest to leave the hour."""
    ctx, get = _plans_client()
    for second in range(client.PACE.budget):
        _plans(ctx, float(second))
    with pytest.raises(RuntimeError, match="180 requests.*last hour.*Nothing was sent.*57 minutes"):
        _plans(ctx, 200.0)
    assert get.await_count == client.PACE.budget
    assert _plans(ctx, 3600.0) == []


def test_a_rejected_request_does_not_count() -> None:
    """A bad id never reaches YNAB, so it takes nothing from the hour's requests."""
    with pytest.raises(ValueError):
        asyncio.run(client.get_accounts("x/../user"))
    assert not client.PACE.sent


# ---------------------------------------------------------------------------
# approve_transactions
# ---------------------------------------------------------------------------


def test_approve_transactions_bulk_patches_approved_flag() -> None:
    """approve_transactions should PATCH all ids at once with approved=True."""
    payload = {"data": {"transaction_ids": ["t1", "t2"], "transactions": []}}
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.approve_transactions("b1", ["t1", "t2"]))
    http = ctx.__aenter__.return_value
    assert result == {"approved": 2}
    assert http.patch.call_args.args[0].endswith("/plans/b1/transactions")
    assert http.patch.call_args.kwargs["json"] == {
        "transactions": [{"id": "t1", "approved": True}, {"id": "t2", "approved": True}]
    }


def test_import_transactions_asks_ynab_to_import_from_linked_accounts() -> None:
    """import_transactions POSTs to the import endpoint, with no body, and returns the new ids."""
    payload = {"data": {"transaction_ids": ["t7", "t8"]}}
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(client.import_transactions("b1"))
    http = ctx.__aenter__.return_value
    assert result == ["t7", "t8"]
    assert http.post.call_args.args[0].endswith("/plans/b1/transactions/import")
    assert "json" not in http.post.call_args.kwargs


def test_approve_transactions_empty_list_makes_no_call() -> None:
    """Nothing to approve must not hit the API."""
    with patch("httpx.AsyncClient") as mock_client:
        result = asyncio.run(client.approve_transactions("b1", []))
    mock_client.assert_not_called()
    assert result == {"approved": 0}


def test_set_transaction_categories_bulk_patches_category_ids() -> None:
    """All category changes go in one PATCH; None clears a category."""
    payload = {"data": {"transaction_ids": ["t1", "t2"], "transactions": []}}
    keeps = {"t1": True, "t2": False}
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(
                client.set_transaction_categories("b1", [("t1", "c1"), ("t2", None)], keeps)
            )
    http = ctx.__aenter__.return_value
    assert result == ["t1", "t2"]
    assert http.patch.call_args.args[0].endswith("/plans/b1/transactions")
    assert http.patch.call_args.kwargs["json"] == {
        "transactions": [
            {"id": "t1", "category_id": "c1", "approved": True},
            {"id": "t2", "category_id": None, "approved": False},
        ]
    }


def test_split_transaction_sends_lines_in_milliunits_and_clears_the_category() -> None:
    """A split is one PATCH: no category on the parent, one subtransaction per line."""
    payload = {"data": {"transaction_ids": ["t1"], "transactions": []}}
    ctx = _async_client_returning(payload)
    lines = [
        {"amount": -81.15, "category_id": "c1", "memo": None},
        {"amount": -5.25, "category_id": "c2", "memo": "Soap"},
    ]
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            asyncio.run(client.split_transaction("b1", "t1", lines, approved=True))
    http = ctx.__aenter__.return_value
    assert http.patch.call_args.args[0].endswith("/plans/b1/transactions")
    assert http.patch.call_args.kwargs["json"] == {
        "transactions": [
            {
                "id": "t1",
                "category_id": None,
                "approved": True,
                "subtransactions": [
                    {"amount": -81150, "category_id": "c1"},
                    {"amount": -5250, "category_id": "c2", "memo": "Soap"},
                ],
            }
        ]
    }


def test_set_transaction_categories_empty_list_makes_no_call() -> None:
    """Nothing to change must not hit the API."""
    with patch("httpx.AsyncClient") as mock_client:
        result = asyncio.run(client.set_transaction_categories("b1", [], {}))
    mock_client.assert_not_called()
    assert result == []


def test_update_category_patches_only_given_fields() -> None:
    """Renaming sends the name; moving sends the group; nothing else."""
    payload = {"data": {"category": {"id": "c1", "name": "Pets", "category_group_id": "g2"}}}
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(
                client.update_category("b1", "c1", name="Pets", category_group_id="g2")
            )
    http = ctx.__aenter__.return_value
    assert result["name"] == "Pets"
    assert http.patch.call_args.args[0].endswith("/plans/b1/categories/c1")
    assert http.patch.call_args.kwargs["json"] == {
        "category": {"name": "Pets", "category_group_id": "g2"}
    }
    with patch("httpx.AsyncClient", return_value=_async_client_returning(payload)) as mocked:
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            asyncio.run(client.update_category("b1", "c1", name="Pets"))
    sent = mocked.return_value.__aenter__.return_value.patch.call_args.kwargs["json"]
    assert sent == {"category": {"name": "Pets"}}


def test_update_category_move_only_sends_the_group() -> None:
    """Moving without renaming leaves the name out of the request."""
    payload = {"data": {"category": {"id": "c1"}}}
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            asyncio.run(client.update_category("b1", "c1", category_group_id="g2"))
    sent = ctx.__aenter__.return_value.patch.call_args.kwargs["json"]
    assert sent == {"category": {"category_group_id": "g2"}}


def test_set_transactions_cleared_bulk_patches_the_status() -> None:
    """Reconciling many transactions is one PATCH."""
    payload = {"data": {"transaction_ids": ["t1", "t2"], "transactions": []}}
    keeps = {"t1": True, "t2": False}
    ctx = _async_client_returning(payload)
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            result = asyncio.run(
                client.set_transactions_cleared("b1", ["t1", "t2"], "reconciled", keeps)
            )
    assert result == ["t1", "t2"]
    assert ctx.__aenter__.return_value.patch.call_args.kwargs["json"] == {
        "transactions": [
            {"id": "t1", "cleared": "reconciled", "approved": True},
            {"id": "t2", "cleared": "reconciled", "approved": False},
        ]
    }


def test_set_transactions_cleared_empty_list_makes_no_call() -> None:
    """Nothing to mark must not hit the API."""
    with patch("httpx.AsyncClient") as mock_client:
        assert asyncio.run(client.set_transactions_cleared("b1", [], "reconciled", {})) == []
    mock_client.assert_not_called()


def test_delete_transaction_sends_delete() -> None:
    """Deleting targets the transaction's own path."""
    ctx = _async_client_returning({"data": {"transaction": {"id": "t1", "deleted": True}}})
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            asyncio.run(client.delete_transaction("b1", "t1"))
    http = ctx.__aenter__.return_value
    assert http.delete.call_args.args[0].endswith("/plans/b1/transactions/t1")


def test_create_transactions_can_leave_them_for_review() -> None:
    """approved=False creates transactions the user still has to approve in YNAB."""
    payload = {"data": {"transaction_ids": ["t1"], "duplicate_import_ids": []}}
    ctx = _async_client_returning(payload)
    ctx.__aenter__.return_value.post = AsyncMock(return_value=_mock_response(payload))
    item = {"date": "2026-07-01", "amount": -1.0, "payee_name": "Shop"}
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            asyncio.run(client.create_transactions("b1", "a1", [item], approved=False))
    sent = ctx.__aenter__.return_value.post.call_args.kwargs["json"]["transactions"][0]
    assert sent["approved"] is False


def test_api_url_can_point_to_another_server() -> None:
    """AVENIR_MCP_YNAB_URL sends requests elsewhere, e.g. to a demo budget server."""
    ctx = _async_client_returning({"data": {"plans": []}})
    env = {"YNAB_API_KEY": "tok", "AVENIR_MCP_YNAB_URL": "http://127.0.0.1:9999/v1"}
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", env):
            asyncio.run(client.get_plans())
    url = ctx.__aenter__.return_value.get.call_args.args[0]
    assert url == "http://127.0.0.1:9999/v1/plans"


def test_api_url_defaults_to_ynab() -> None:
    """Without configuration, requests go to YNAB's API."""
    ctx = _async_client_returning({"data": {"plans": []}})
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}, clear=True):
            asyncio.run(client.get_plans())
    url = ctx.__aenter__.return_value.get.call_args.args[0]
    assert url == "https://api.ynab.com/v1/plans"


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.org/v1",
        "http://127.0.0.1:8765",
        "http://localhost:9000/v1",
        "http://[::1]:80",
    ],
)
def test_api_url_may_be_https_or_this_machine(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A stand-in on this machine may use plain http; anything else must be https."""
    monkeypatch.setenv("AVENIR_MCP_YNAB_URL", url + "/")
    assert client._base_url() == url  # pylint: disable=protected-access


@pytest.mark.parametrize("url", ["http://api.example.org/v1", "ftp://127.0.0.1", "api.ynab.com"])
def test_api_url_never_sends_the_token_in_clear(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The token would travel in clear to another machine: refused before any request."""
    monkeypatch.setenv("AVENIR_MCP_YNAB_URL", url)
    with pytest.raises(RuntimeError, match="https"):
        client._base_url()  # pylint: disable=protected-access


def test_token_can_come_from_a_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """YNAB_API_KEY_FILE keeps the token out of client configurations."""
    secret = tmp_path / "ynab-token"
    secret.write_text("file-token\n", encoding="utf-8")
    secret.chmod(0o600)
    monkeypatch.delenv("YNAB_API_KEY", raising=False)
    monkeypatch.setenv("YNAB_API_KEY_FILE", str(secret))
    assert client._api_key().get_secret_value() == "file-token"  # pylint: disable=protected-access


@pytest.mark.skipif(os.name != "posix", reason="POSIX permissions; Windows uses ACLs")
def test_token_file_readable_by_others_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Like an SSH key, a token file others can read is refused, saying how to fix it."""
    secret = tmp_path / "ynab-token"
    secret.write_text("file-token", encoding="utf-8")
    secret.chmod(0o644)
    monkeypatch.delenv("YNAB_API_KEY", raising=False)
    monkeypatch.setenv("YNAB_API_KEY_FILE", str(secret))
    with pytest.raises(RuntimeError, match="chmod 600"):
        client._api_key()  # pylint: disable=protected-access


def test_missing_token_file_says_which_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A path that does not exist is named in the error."""
    monkeypatch.delenv("YNAB_API_KEY", raising=False)
    monkeypatch.setenv("YNAB_API_KEY_FILE", str(tmp_path / "absent"))
    with pytest.raises(RuntimeError, match="YNAB_API_KEY_FILE"):
        client._api_key()  # pylint: disable=protected-access


def test_token_variable_wins_over_the_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """When both are set, YNAB_API_KEY is used and the file is not read."""
    monkeypatch.setenv("YNAB_API_KEY", "env-token")
    monkeypatch.setenv("YNAB_API_KEY_FILE", "/nonexistent")
    assert client._api_key().get_secret_value() == "env-token"  # pylint: disable=protected-access


def test_no_token_at_all_names_both_ways(monkeypatch: pytest.MonkeyPatch) -> None:
    """Neither set: the error says both ways to give the token."""
    monkeypatch.delenv("YNAB_API_KEY", raising=False)
    monkeypatch.delenv("YNAB_API_KEY_FILE", raising=False)
    with pytest.raises(RuntimeError, match="YNAB_API_KEY_FILE"):
        client._api_key()  # pylint: disable=protected-access


@pytest.mark.parametrize(
    "plan_id",
    ["x/../../user", "b1/transactions/tx-9?", "..", "", "-flag", "b1 b2", "b1%2F..", "b1#frag"],
)
def test_ids_that_would_change_the_request_are_refused(
    plan_id: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An id is one path segment: slashes, dots, queries or escapes never reach YNAB."""
    monkeypatch.setenv("YNAB_API_KEY", "tok")
    request = client.get_accounts(plan_id)
    with patch("httpx.AsyncClient") as http, pytest.raises(ValueError, match="not a YNAB id"):
        asyncio.run(request)
    http.assert_not_called()


@pytest.mark.parametrize(
    "plan_id", ["last-used", "demo-budget", "0f9c2a1e-6b5d-4c3a-9e8f-1a2b3c4d5e6f", "b_1"]
)
def test_real_ids_reach_ynab_unchanged(plan_id: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """UUIDs, last-used and the demo budget's ids pass as they are."""
    monkeypatch.setenv("YNAB_API_KEY", "tok")
    response = MagicMock(status_code=200)
    response.json.return_value = {"data": {"accounts": []}}
    with patch("httpx.AsyncClient") as http:
        http.return_value.__aenter__.return_value.get = AsyncMock(return_value=response)
        asyncio.run(client.get_accounts(plan_id))
        url = http.return_value.__aenter__.return_value.get.call_args.args[0]
    assert url.endswith(f"/plans/{plan_id}/accounts")


def test_last_used_is_never_merged_across_budgets() -> None:
    """'last-used' can name another budget between two calls: each call loads in full.

    Delta sync counts changes per budget; merging one budget's changes into
    another's transactions would mix two households silently.
    """
    budget_a = {"data": {"transactions": [{"id": "a1", "amount": -1000}], "server_knowledge": 100}}
    budget_b = {"data": {"transactions": [{"id": "b1", "amount": -2000}], "server_knowledge": 7}}
    get = AsyncMock(side_effect=[budget_a, budget_b])
    with patch("avenir_mcp.client._get", get):
        asyncio.run(client.get_transactions("last-used"))
        second = asyncio.run(client.get_transactions("last-used"))
    assert second == budget_b["data"]["transactions"]
    assert "last_knowledge_of_server" not in get.call_args.kwargs["params"]


def test_scheduled_transactions_are_read_from_the_plan() -> None:
    """One GET on the plan's scheduled transactions."""
    ctx = _async_client_returning({"data": {"scheduled_transactions": [{"id": "s1"}]}})
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}, clear=True):
            found = asyncio.run(client.get_scheduled_transactions("b1"))
    assert found == [{"id": "s1"}]
    url = ctx.__aenter__.return_value.get.call_args.args[0]
    assert url == "https://api.ynab.com/v1/plans/b1/scheduled_transactions"


def test_set_flags_sends_one_bulk_patch_and_null_removes_a_flag() -> None:
    """Flags go in one request; None becomes null, which YNAB reads as no flag."""
    ctx = _async_client_returning({"data": {"transaction_ids": ["t1", "t2"]}})
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            ids = asyncio.run(
                client.set_flags("b1", [("t1", "red"), ("t2", None)], {"t1": True, "t2": False})
            )
            nothing = asyncio.run(client.set_flags("b1", [], {}))
    sent = ctx.__aenter__.return_value.patch.call_args.kwargs["json"]
    assert sent == {
        "transactions": [
            {"id": "t1", "flag_color": "red", "approved": True},
            {"id": "t2", "flag_color": None, "approved": False},
        ]
    }
    assert ids == ["t1", "t2"]
    assert nothing == []


def test_set_category_target_patches_the_category_with_the_goal_fields() -> None:
    """The target goes in one PATCH of the category; None removes it."""
    ctx = _async_client_returning({"data": {"category": {"id": "c1", "goal_target": None}}})
    with patch("httpx.AsyncClient", return_value=ctx):
        with patch.dict("os.environ", {"YNAB_API_KEY": "tok"}):
            done = asyncio.run(client.set_category_target("b1", "c1", {"goal_target": None}))
    sent = ctx.__aenter__.return_value.patch.call_args
    assert sent.args[0].endswith("/plans/b1/categories/c1")
    assert sent.kwargs["json"] == {"category": {"goal_target": None}}
    assert done == {"id": "c1", "goal_target": None}
