# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""find_transactions through the MCP protocol: one bounded read, no write."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from .mcp_helpers import call

_ACCOUNTS = [{"id": "acc", "name": "Checking"}]
_CATS = [{"id": "c-food", "name": "Groceries"}]
_TX = {"id": "t1", "date": "2026-09-12", "amount": -86400, "account_id": "acc"}
_TX |= {"payee_name": "Organic Market", "category_id": "c-food", "cleared": "cleared"}


@pytest.fixture(name="read")
def _read() -> Iterator[AsyncMock]:
    """A fake YNAB; the mock it yields records how transactions were read."""
    transactions = AsyncMock(return_value=[_TX])
    with (
        patch("avenir_mcp.client.get_accounts", AsyncMock(return_value=_ACCOUNTS)),
        patch("avenir_mcp.client.get_categories", AsyncMock(return_value=_CATS)),
        patch("avenir_mcp.client.get_transactions", transactions),
        patch("avenir_mcp.app.today", lambda: date(2026, 9, 26)),
    ):
        yield transactions


def test_find_reads_once_from_the_start_date(read: AsyncMock) -> None:
    """One request, asking YNAB only for what follows since_date."""
    args = {"plan_id": "b1", "since_date": "2026-09-10", "amount": -86.4}
    found = call("find_transactions", args).structured_content
    assert [t["transaction_id"] for t in found["transactions"]] == ["t1"]
    assert found["transactions"][0]["category"] == "Groceries"
    read.assert_awaited_once_with("b1", since_date="2026-09-10")


def test_until_defaults_to_today(read: AsyncMock) -> None:
    """Without until_date, the search ends today."""
    args = {"plan_id": "b1", "since_date": "2026-09-13"}
    found = call("find_transactions", args).structured_content
    assert (found["transactions"], found["until_date"]) == ([], "2026-09-26")
    assert read.await_count == 1


def test_open_ended_search_stops_a_year_after_since(read: AsyncMock) -> None:
    """Without until_date, a start older than a year searches its first year, and says so."""
    args = {"plan_id": "b1", "since_date": "2025-01-01"}
    found = call("find_transactions", args).structured_content
    assert (found["transactions"], found["until_date"]) == ([], "2026-01-02")
    read.assert_awaited_once_with("b1", since_date="2025-01-01")


def test_an_explicit_range_over_a_year_is_still_refused(read: AsyncMock) -> None:
    """Only an open end is clamped: a range the agent gave is its own."""
    args = {"plan_id": "b1", "since_date": "2025-01-01", "until_date": "2026-09-01"}
    result = call("find_transactions", args)
    assert result.is_error
    assert "366 days" in result.content[0].text
    read.assert_not_awaited()


def test_a_bad_window_is_refused_before_any_request(read: AsyncMock) -> None:
    """The dates are checked first."""
    args: dict[str, Any] = {
        "plan_id": "b1",
        "since_date": "2026-09-20",
        "until_date": "2026-09-10",
    }
    result = call("find_transactions", args)
    assert result.is_error
    assert "before" in result.content[0].text
    read.assert_not_awaited()


def test_category_and_payee_narrow_the_search(read: AsyncMock) -> None:
    """Both filters reach the search: a matching pair is found, a wrong payee is not."""
    args: dict[str, Any] = {"plan_id": "b1", "since_date": "2026-09-01", "category_ids": ["c-food"]}
    found = call("find_transactions", {**args, "payee": "organic"}).structured_content
    assert [t["transaction_id"] for t in found["transactions"]] == ["t1"]
    missed = call("find_transactions", {**args, "payee": "bakery"}).structured_content
    assert missed["transactions"] == []
    read.assert_awaited_with("b1", since_date="2026-09-01")


@pytest.mark.usefixtures("read")
def test_an_unknown_category_is_a_tool_error() -> None:
    """The agent learns which id is wrong and where to find a right one."""
    args = {"plan_id": "b1", "since_date": "2026-09-01", "category_ids": ["c-gone"]}
    result = call("find_transactions", args)
    assert result.is_error
    assert "c-gone" in result.content[0].text
    assert "get_category_balances" in result.content[0].text


def test_review_filters_reach_the_search(read: AsyncMock) -> None:
    """cleared, approved and uncategorized narrow a cleared, categorized, unapproved row."""
    args: dict[str, Any] = {"plan_id": "b1", "since_date": "2026-09-01"}
    kept = call("find_transactions", {**args, "cleared": "cleared", "uncategorized": False})
    assert [t["transaction_id"] for t in kept.structured_content["transactions"]] == ["t1"]
    for extra in ({"cleared": "uncleared"}, {"approved": True}, {"uncategorized": True}):
        missed = call("find_transactions", {**args, **extra}).structured_content
        assert missed["transactions"] == []
    read.assert_awaited_with("b1", since_date="2026-09-01")
