# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""approve_transactions through the MCP protocol: by ids at once, by dates once confirmed."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any
from unittest.mock import patch

import pytest

from .mcp_helpers import FLAT, FORGED, accept, asking, call, decline, one_line

_ACCOUNTS = [
    {"id": "acc", "name": "Checking", "on_budget": True},
    {"id": "acc-house", "name": "House", "on_budget": False},
]
_CATEGORIES = [
    {"id": "c-food", "name": "Groceries", "category_group_name": "Everyday"},
    {
        "id": "c-internal",
        "name": "Uncategorized",
        "category_group_name": "Internal Master Category",
    },
]


def _tx(tx_id: str, day: str, **extra: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "id": tx_id,
        "date": day,
        "amount": -12_340,
        "payee_name": "Corner Shop",
        "memo": None,
        "account_id": "acc",
        "account_name": "Checking",
        "category_id": "c-food",
        "subtransactions": [],
        "cleared": "cleared",
        "approved": False,
        "deleted": False,
    }
    return tx | extra


def _month() -> list[dict[str, Any]]:
    """Four rows to approve, and one row for each reason to leave a row alone."""
    live = [{"id": "s1", "category_id": "c-food", "deleted": False}]
    return [
        _tx("t-food", "2026-09-04"),
        _tx("t-split", "2026-09-06", category_id=None, subtransactions=live),
        _tx("t-transfer", "2026-09-08", category_id=None, transfer_account_id="acc-house"),
        _tx("t-house", "2026-09-10", category_id=None, account_id="acc-house"),
        _tx("t-uncleared", "2026-09-11", cleared="uncleared"),
        _tx("t-bare", "2026-09-12", category_id=None),
        _tx("t-done", "2026-09-13", approved=True),
        _tx("t-kept", "2026-09-14"),
        _tx("t-october", "2026-10-02"),
    ]


class FakeYnab:
    """A plan's transactions, and the ids YNAB was asked to approve."""

    def __init__(self, transactions: list[dict[str, Any]]) -> None:
        """Start with these transactions and nothing approved."""
        self.transactions = transactions
        self.approved: list[list[str]] = []
        self.reads = 0

    async def get_accounts(self, _plan_id: str) -> list[dict[str, Any]]:
        """The plan's accounts."""
        return _ACCOUNTS

    async def get_categories(self, _plan_id: str) -> list[dict[str, Any]]:
        """The plan's categories."""
        return _CATEGORIES

    async def get_transactions(self, _plan_id: str, **_: Any) -> list[dict[str, Any]]:
        """The plan's transactions."""
        self.reads += 1
        return self.transactions

    async def approve_transactions(self, _plan_id: str, ids: list[str]) -> dict[str, int]:
        """Record the ids approved."""
        self.approved.append(ids)
        return {"approved": len(ids)}


@pytest.fixture(name="ynab")
def _ynab() -> Iterator[FakeYnab]:
    fake = FakeYnab(_month())
    with (
        patch("avenir_mcp.client.get_accounts", fake.get_accounts),
        patch("avenir_mcp.client.get_categories", fake.get_categories),
        patch("avenir_mcp.client.get_transactions", fake.get_transactions),
        patch("avenir_mcp.client.approve_transactions", fake.approve_transactions),
        patch("avenir_mcp.app.today", lambda: date(2026, 10, 5)),
    ):
        yield fake


_EXPECTED = ["t-food", "t-split", "t-transfer", "t-house"]


def _september(**extra: Any) -> dict[str, Any]:
    return {
        "plan_id": "b1",
        "since_date": "2026-09-01",
        "until_date": "2026-09-30",
        "exclude_ids": ["t-kept"],
        **extra,
    }


def test_ids_are_approved_at_once(ynab: FakeYnab) -> None:
    """tx_ids mode asks nothing and reads nothing: the agent checked them already."""
    result = call("approve_transactions", {"plan_id": "b1", "tx_ids": ["t1", "t2"]})
    assert result.structured_content["approved"] == 2
    assert result.structured_content["status"] == "applied"
    assert ynab.approved == [["t1", "t2"]]
    assert ynab.reads == 0


def test_a_period_without_elicitation_returns_a_code_and_approves_nothing(ynab: FakeYnab) -> None:
    """The preview lists the rows and asks the agent to show them to the user."""
    found = call("approve_transactions", _september()).structured_content
    assert found["status"] == "confirmation_required"
    assert found["confirmation"]
    assert found["approved"] == 0
    assert [t["transaction_id"] for t in found["transactions"]] == _EXPECTED
    assert "Approve 4 transaction(s)?" in found["message"]
    assert "- 2026-09-06 Corner Shop -12.34: split" in found["message"]
    assert "- 2026-09-08 Corner Shop -12.34: transfer" in found["message"]
    assert "- 2026-09-10 Corner Shop -12.34: no category" in found["message"]
    assert ynab.approved == []


def test_an_accepted_period_approves_exactly_the_reviewed_rows(ynab: FakeYnab) -> None:
    """Uncleared, uncategorized, approved, excluded and later rows are left alone."""
    result = call("approve_transactions", _september(), accept).structured_content
    assert (result["status"], result["approved"]) == ("applied", 4)
    assert ynab.approved == [_EXPECTED]


def test_the_code_approves_the_rows_previewed(ynab: FakeYnab) -> None:
    """The same arguments and the code apply what the user saw."""
    code = call("approve_transactions", _september()).structured_content["confirmation"]
    result = call("approve_transactions", _september(confirmation=code)).structured_content
    assert (result["status"], result["approved"]) == ("applied", 4)
    assert ynab.approved == [_EXPECTED]


def test_a_code_from_one_window_cannot_approve_another(ynab: FakeYnab) -> None:
    """Two windows that pick the same rows still need their own agreement."""
    code = call("approve_transactions", _september()).structured_content["confirmation"]
    other = _september(since_date="2026-09-02", confirmation=code)
    result = call("approve_transactions", other)
    assert result.is_error
    assert "confirmation code" in result.content[0].text
    assert ynab.approved == []


def test_a_code_cannot_approve_a_row_changed_since(ynab: FakeYnab) -> None:
    """A row whose amount changed after the preview is not what the user agreed to."""
    code = call("approve_transactions", _september()).structured_content["confirmation"]
    ynab.transactions[0]["amount"] = -99_990
    result = call("approve_transactions", _september(confirmation=code))
    assert result.is_error
    assert ynab.approved == []


def test_a_declined_period_approves_nothing(ynab: FakeYnab) -> None:
    """No is no."""
    result = call("approve_transactions", _september(), decline).structured_content
    assert (result["status"], result["approved"]) == ("declined", 0)
    assert ynab.approved == []


def test_a_period_with_nothing_to_approve_asks_nothing(ynab: FakeYnab) -> None:
    """No row, no question."""
    asked: list[str] = []
    args = _september(since_date="2026-09-15")
    result = call("approve_transactions", args, asking(asked)).structured_content
    assert (result["status"], result["approved"]) == ("nothing_to_do", 0)
    assert not asked
    assert ynab.approved == []


def test_an_open_window_ends_today(ynab: FakeYnab) -> None:
    """Without until_date, rows up to today are approved, the excluded one apart."""
    args = {"plan_id": "b1", "since_date": "2026-09-14"}
    result = call("approve_transactions", args, accept).structured_content
    assert (result["status"], result["approved"]) == ("applied", 2)
    assert ynab.approved == [["t-kept", "t-october"]]


def test_the_question_shows_twenty_rows_and_how_many_more(ynab: FakeYnab) -> None:
    """A long period is summed up, not listed in full; bank text stays on its line."""
    ynab.transactions = [_tx(f"t{i:02}", f"2026-09-{i:02}") for i in range(1, 26)]
    ynab.transactions[0]["payee_name"] = FORGED
    asked: list[str] = []
    result = call("approve_transactions", _september(), asking(asked)).structured_content
    assert result["approved"] == 25
    assert len(asked) == 1
    question = asked[0]
    assert question.startswith("Approve 25 transaction(s)?")
    assert question.count("\n- 2026-09-") == 20
    assert question.endswith("\n- … and 5 more")
    assert "Groceries" in question
    assert FLAT in question
    assert one_line(question)


@pytest.mark.parametrize(
    "args",
    [
        {"plan_id": "b1"},
        {"plan_id": "b1", "tx_ids": ["t1"], "since_date": "2026-09-01"},
        {"plan_id": "b1", "tx_ids": ["t1"], "exclude_ids": ["t2"]},
        {"plan_id": "b1", "until_date": "2026-09-30"},
        {"plan_id": "b1", "exclude_ids": ["t2"]},
    ],
    ids=["neither", "both", "ids and an exclusion", "no since_date", "only an exclusion"],
)
def test_one_mode_at_a_time(ynab: FakeYnab, args: dict[str, Any]) -> None:
    """tx_ids, or a period from since_date: never both, never neither."""
    result = call("approve_transactions", args)
    assert result.is_error
    assert "tx_ids" in result.content[0].text
    assert ynab.approved == []
    assert ynab.reads == 0


def test_a_window_over_a_year_is_refused_before_any_read(ynab: FakeYnab) -> None:
    """The dates are checked first, as find_transactions does."""
    args = {"plan_id": "b1", "since_date": "2025-01-01", "until_date": "2026-09-30"}
    result = call("approve_transactions", args)
    assert result.is_error
    assert "366 days" in result.content[0].text
    assert ynab.reads == 0
