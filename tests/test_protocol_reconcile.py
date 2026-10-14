# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""reconcile_account through the MCP protocol: diagnose, confirm, reconcile, undo."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client

from avenir_mcp import client, server

from .mcp_helpers import FLAT, FORGED, accept, asking, call, decline, one_line

# YNAB's own cleared balance, in currency units as client.get_accounts gives it: t1 + t2.
_ACCOUNTS = [{"id": "acc", "name": "Checking", "cleared_balance": 70.0}]
_CATS = [
    {
        "id": "c-inflow",
        "name": "Inflow: Ready to Assign",
        "category_group_name": "Internal Master Category",
    },
    {"id": "c-food", "name": "Groceries", "category_group_name": "Everyday"},
]


class _Bank:
    """A fake budget with one account."""

    def __init__(self) -> None:
        self.transactions: list[dict[str, Any]] = [
            self._tx("t1", 100000, "reconciled"),
            self._tx("t2", -30000, "cleared"),
            self._tx("t3", -5000, "uncleared"),
        ]
        self.created: list[dict[str, Any]] = []
        self.deleted: list[str] = []
        self.sent_approved: list[dict[str, bool]] = []
        self.loads = 0

    @staticmethod
    def _tx(tx_id: str, amount: int, cleared: str) -> dict[str, Any]:
        return {
            "id": tx_id,
            "amount": amount,
            "cleared": cleared,
            "account_id": "acc",
            "payee_name": "Market",
            "date": "2026-09-11",
            "approved": True,
            "deleted": False,
        }

    async def get_transactions(
        self,
        _budget_id: str,
        fresh: bool = False,  # pylint: disable=unused-argument
    ) -> list[dict[str, Any]]:
        """Return copies, as YNAB would, counting the loads."""
        self.loads += 1
        return [dict(tx) for tx in self.transactions]

    async def create_transactions(
        self, _budget_id: str, account_id: str, items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Record the adjustment and add it, cleared, to the account."""
        self.created.extend(items)
        tx = self._tx("adj", round(items[0]["amount"] * 1000), "cleared")
        tx["account_id"] = account_id
        self.transactions.append(tx)
        return {"created": 1, "transaction_ids": ["adj"], "duplicate_import_ids": []}

    async def set_transactions_cleared(
        self, _budget_id: str, tx_ids: list[str], cleared: str, approved: dict[str, bool]
    ) -> list[str]:
        """Apply a cleared status, and the approval sent with it."""
        self.sent_approved.append(approved)
        for tx in self.transactions:
            if tx["id"] in tx_ids:
                tx["cleared"] = cleared
                tx["approved"] = approved[tx["id"]]
        return tx_ids

    async def delete_transaction(self, _budget_id: str, tx_id: str) -> None:
        """Mark a transaction deleted."""
        self.deleted.append(tx_id)
        for tx in self.transactions:
            if tx["id"] == tx_id:
                tx["deleted"] = True

    def status(self, tx_id: str) -> str:
        """Current cleared status of a transaction."""
        return str(next(tx["cleared"] for tx in self.transactions if tx["id"] == tx_id))


@pytest.fixture(name="bank")
def _bank(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Bank]:
    monkeypatch.setenv("AVENIR_MCP_JOURNAL", str(tmp_path / "journal.jsonl"))
    fake = _Bank()
    with (
        patch("avenir_mcp.client.get_transactions", fake.get_transactions),
        patch("avenir_mcp.client.get_accounts", AsyncMock(return_value=_ACCOUNTS)),
        patch("avenir_mcp.client.get_categories", AsyncMock(return_value=_CATS)),
        patch("avenir_mcp.client.create_transactions", fake.create_transactions),
        patch("avenir_mcp.client.set_transactions_cleared", fake.set_transactions_cleared),
        patch("avenir_mcp.client.delete_transaction", fake.delete_transaction),
    ):
        yield fake


def _args(balance: float, **extra: Any) -> dict[str, Any]:
    return {"plan_id": "b1", "account_id": "acc", "bank_balance": balance, **extra}


def test_reconcile_declares_a_write() -> None:
    """It can change the account: clients must know."""

    async def run() -> Any:
        async with Client(server.mcp) as mcp_client:
            return next(t for t in await mcp_client.list_tools() if t.name == "reconcile_account")

    annotations = asyncio.run(run()).annotations
    assert annotations.read_only_hint is False
    assert annotations.destructive_hint is True


def test_difference_is_diagnosed_without_writing(bank: _Bank) -> None:
    """A gap is explained, not silently adjusted: nothing is asked or written."""
    data = call("reconcile_account", _args(65.0), accept).structured_content
    assert data["status"] == "difference_found"
    assert data["analysis"]["difference"] == -5.0
    assert data["analysis"]["explained_by"] == ["t3"]
    assert "adjust" in data["message"]
    assert bank.status("t2") == "cleared" and not bank.created


def test_matching_balance_reconciles_after_confirmation(bank: _Bank) -> None:
    """Balance matches: cleared transactions become reconciled once the code is given."""
    preview = call("reconcile_account", _args(70.0)).structured_content
    assert preview["status"] == "confirmation_required"
    assert bank.status("t2") == "cleared"
    code = preview["confirmation"]
    data = call("reconcile_account", _args(70.0, confirmation=code)).structured_content
    assert data["status"] == "applied"
    assert bank.status("t2") == "reconciled"
    assert bank.status("t3") == "uncleared"


def test_adjustment_is_created_on_request_then_undone(bank: _Bank) -> None:
    """adjust=true records the gap as a Ready to Assign adjustment; undo removes it."""
    data = call("reconcile_account", _args(80.0, adjust=True), accept).structured_content
    assert data["status"] == "applied"
    assert data["adjustment"] == 10.0
    assert bank.created[0]["amount"] == 10.0
    assert bank.created[0]["category_id"] == "c-inflow"
    assert bank.status("adj") == "reconciled"
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "applied"
    assert bank.deleted == ["adj"]
    assert bank.status("t2") == "cleared"


def test_reconcile_account_keeps_the_transaction_approved(bank: _Bank) -> None:
    """Reconciling sends each transaction's approval, and the adjustment's as approved."""
    bank.transactions[1]["approved"] = False
    call("reconcile_account", _args(80.0, adjust=True), accept)
    sent = bank.sent_approved[0]
    assert (sent["t2"], sent["adj"]) == (False, True)
    call("undo_operation", {"plan_id": "b1"}, accept)
    assert bank.sent_approved[-1]["t2"] is False
    approved = {tx["id"]: tx["approved"] for tx in bank.transactions}
    assert approved == {"t1": True, "t2": False, "t3": True, "adj": True}


def test_nothing_to_reconcile(bank: _Bank) -> None:
    """Already reconciled and matching: nothing to do."""
    bank.transactions = [bank.transactions[0]]
    account = [{**_ACCOUNTS[0], "cleared_balance": 100.0}]
    with patch("avenir_mcp.client.get_accounts", AsyncMock(return_value=account)):
        data = call("reconcile_account", _args(100.0)).structured_content
    assert data["status"] == "nothing_to_do"


def test_unknown_account_is_a_tool_error(bank: _Bank) -> None:
    """An account id that is not in the plan is refused, saying where to find one."""
    result = call("reconcile_account", {**_args(1.0), "account_id": "nope"})
    assert result.is_error
    assert "list_accounts" in result.content[0].text
    assert not bank.created


def test_declined_reconciliation_changes_nothing(bank: _Bank) -> None:
    """If the user says no, statuses stay as they are."""
    data = call("reconcile_account", _args(70.0), decline).structured_content
    assert data["status"] == "declined"
    assert bank.status("t2") == "cleared"


def test_undo_reconcile_without_elicitation_needs_the_code(bank: _Bank) -> None:
    """Undoing a reconciliation is previewed and confirmed like any write."""
    call("reconcile_account", _args(70.0), accept)
    preview = call("undo_operation", {"plan_id": "b1"}).structured_content
    assert preview["status"] == "confirmation_required"
    assert bank.status("t2") == "reconciled"
    code = preview["confirmation"]
    data = call("undo_operation", {"plan_id": "b1", "confirmation": code}).structured_content
    assert data["status"] == "applied"
    assert bank.status("t2") == "cleared"


def test_declined_undo_of_a_reconciliation_changes_nothing(bank: _Bank) -> None:
    """If the user refuses the undo, the account stays reconciled."""
    call("reconcile_account", _args(70.0), accept)
    data = call("undo_operation", {"plan_id": "b1"}, decline).structured_content
    assert data["status"] == "declined"
    assert bank.status("t2") == "reconciled"


def test_confirmation_covers_exactly_the_previewed_transactions(bank: _Bank) -> None:
    """Transactions cleared after the preview are not reconciled by its code."""
    code = call("reconcile_account", _args(70.0)).structured_content["confirmation"]
    # pylint: disable-next=protected-access
    later = [bank._tx("t4", 10000, "cleared"), bank._tx("t5", -10000, "cleared")]
    bank.transactions += later
    result = call("reconcile_account", _args(70.0, confirmation=code))
    assert result.is_error
    assert bank.status("t4") == "cleared"
    assert bank.status("t2") == "cleared"


def test_adjustment_goes_to_ready_to_assign_dated_today(bank: _Bank) -> None:
    """A user category named like YNAB's inflow is not mistaken for Ready to Assign."""
    lookalike = {"id": "c-bonus", "name": "Inflow bonus", "category_group_name": "Everyday"}
    with (
        patch("avenir_mcp.client.get_categories", AsyncMock(return_value=[lookalike, *_CATS])),
        patch("avenir_mcp.app.today", return_value=date(2026, 9, 25)),
    ):
        call("reconcile_account", _args(80.0, adjust=True), accept)
    assert bank.created[0]["category_id"] == "c-inflow"
    assert bank.created[0]["date"] == "2026-09-25"


def test_an_account_name_cannot_forge_lines_in_the_question(bank: _Bank) -> None:
    """An account name with a line break stays on one line, in the question and the answer."""
    asked: list[str] = []
    forged = AsyncMock(return_value=[{"id": "acc", "name": FORGED, "cleared_balance": 70.0}])
    with patch("avenir_mcp.client.get_accounts", forged):
        data = call("reconcile_account", _args(70.0), asking(asked)).structured_content
    assert one_line(asked[0])
    assert data["account"] == FLAT
    assert bank.status("t2") == "reconciled"


@pytest.mark.parametrize("adjust", [False, True])
def test_totals_that_still_disagree_stop_before_anything_is_asked(
    bank: _Bank, adjust: bool
) -> None:
    """YNAB counts another cleared total even after a full reload: nothing is asked or written."""
    asked: list[str] = []
    account = [{**_ACCOUNTS[0], "cleared_balance": 99.0}]
    with patch("avenir_mcp.client.get_accounts", AsyncMock(return_value=account)):
        data = call(
            "reconcile_account", _args(80.0, adjust=adjust), asking(asked)
        ).structured_content
    assert data["status"] == "totals_disagree"
    assert (data["analysis"]["cleared_balance"], data["analysis"]["ynab_cleared_balance"]) == (
        70.0,
        99.0,
    )
    assert "70.00" in data["message"] and "99.00" in data["message"]
    assert "Nothing was changed" in data["message"]
    assert data["confirmation"] is None and data["adjustment"] is None
    assert bank.loads == 2
    assert not asked
    assert not bank.created and not bank.sent_approved
    assert bank.status("t2") == "cleared"


def _account(cleared: int) -> dict[str, Any]:
    """An account as YNAB's API returns it, amounts in milliunits."""
    return {
        "id": "acc",
        "name": "Card",
        "type": "creditCard",
        "on_budget": True,
        "closed": False,
        "balance": cleared,
        "cleared_balance": cleared,
        "uncleared_balance": 0,
    }


def _row(tx_id: str, amount: int, cleared: str) -> dict[str, Any]:
    """A transaction as YNAB's API returns it."""
    # pylint: disable-next=protected-access
    return {**_Bank._tx(tx_id, amount, cleared), "payee_name": "Hardware Store"}


def test_an_import_ynab_absorbed_is_dropped_by_a_full_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stale import the delta never deleted no longer counts: the cache is reloaded in full.

    The cache was filled while a bank import and the scheduled placeholder it matches
    were both live. The user then matched them in YNAB: the placeholder came back
    cleared in the next delta, but the import was never reported deleted.
    """
    monkeypatch.setenv("AVENIR_MCP_JOURNAL", str(tmp_path / "journal.jsonl"))
    opening = _row("t1", 100000, "reconciled")
    placeholder = _row("sched", -41317, "uncleared")
    imported = _row("import", -41317, "cleared")
    loads = iter(
        [
            {"transactions": [opening, placeholder, imported], "server_knowledge": 1},
            {"transactions": [{**placeholder, "cleared": "cleared"}], "server_knowledge": 2},
            {
                "transactions": [opening, {**placeholder, "cleared": "cleared"}],
                "server_knowledge": 3,
            },
        ]
    )
    sent: list[dict[str, Any]] = []

    async def fake_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if path.endswith("/accounts"):
            return {"data": {"accounts": [_account(58683)]}}
        sent.append(dict(params or {}))
        return {"data": next(loads)}

    with patch("avenir_mcp.client._get", fake_get):
        asyncio.run(client.get_transactions("b1"))
        data = call("reconcile_account", _args(50.0)).structured_content
    assert data["status"] == "difference_found"
    assert data["analysis"]["cleared_balance"] == 58.683
    assert data["analysis"]["ynab_cleared_balance"] == 58.683
    assert data["analysis"]["possible_duplicates"] == []
    assert [params.get("last_knowledge_of_server") for params in sent] == [None, 1, None]
