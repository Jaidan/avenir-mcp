# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Writes through the MCP protocol: preview, confirmation, journal and undo."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client
from fastmcp.client.elicitation import ElicitResult

from avenir_mcp import confirm, server

from .mcp_helpers import FLAT, FORGED, accept, call, decline

_CATS = [
    {"id": "c-food", "name": "Groceries"},
    {"id": "c-fun", "name": "Leisure"},
]
_ASSIGN = [{"transaction_id": "t1", "category_id": "c-food"}]
_ACCOUNTS = [{"id": "acc", "on_budget": True}]


def _txs(category_id: str | None = None) -> list[dict[str, Any]]:
    return [
        {
            "id": "t1",
            "date": "2026-09-02",
            "amount": -7250,
            "payee_name": "Corner Shop",
            "category_id": category_id,
            "transfer_account_id": None,
        }
    ]


class _Budget:
    """A fake budget: holds transactions and records category PATCHes."""

    def __init__(self) -> None:
        self.transactions = _txs()
        self.patches: list[list[tuple[str, str | None]]] = []
        self.sent_approved: list[dict[str, bool]] = []

    async def get_transactions(self, _budget_id: str) -> list[dict[str, Any]]:
        """Return a copy of the transactions, as YNAB would."""
        return [dict(tx) for tx in self.transactions]

    async def set_transaction_categories(
        self, _budget_id: str, moves: list[tuple[str, str | None]], approved: dict[str, bool]
    ) -> list[str]:
        """Record the PATCH and apply it to the fake budget, approval included."""
        self.patches.append(moves)
        self.sent_approved.append(approved)
        for tx_id, category_id in moves:
            for tx in self.transactions:
                if tx["id"] == tx_id:
                    tx["category_id"] = category_id
                    tx["approved"] = approved[tx_id]
        return [tx_id for tx_id, _ in moves]


@pytest.fixture(name="budget")
def _budget(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Budget]:
    monkeypatch.setenv("AVENIR_MCP_JOURNAL", str(tmp_path / "journal.jsonl"))
    fake = _Budget()
    with (
        patch("avenir_mcp.client.get_transactions", fake.get_transactions),
        patch("avenir_mcp.client.get_categories", AsyncMock(return_value=_CATS)),
        patch("avenir_mcp.client.get_accounts", AsyncMock(return_value=_ACCOUNTS)),
        patch("avenir_mcp.client.set_transaction_categories", fake.set_transaction_categories),
    ):
        yield fake


def _annotations(name: str) -> Any:
    async def run() -> Any:
        async with Client(server.mcp) as mcp_client:
            tools = await mcp_client.list_tools()
        return next(t for t in tools if t.name == name).annotations

    return asyncio.run(run())


# ---------------------------------------------------------------------------
# apply_categories
# ---------------------------------------------------------------------------


def test_write_tools_declare_what_they_do() -> None:
    """Clients can tell these tools change the budget."""
    apply = _annotations("apply_categories")
    assert apply.read_only_hint is False
    assert apply.destructive_hint is True
    assert apply.idempotent_hint is True
    undo = _annotations("undo_operation")
    assert undo.read_only_hint is False
    assert undo.destructive_hint is True


def test_without_elicitation_first_call_only_previews(budget: _Budget) -> None:
    """A client that cannot ask the user gets a preview and a code; nothing changes."""
    result = call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN})
    data = result.structured_content
    assert data["status"] == "confirmation_required"
    assert data["confirmation"]
    assert data["changes"][0]["to_category"] == "Groceries"
    assert data["changes"][0]["amount"] == -7.25
    assert not budget.patches


def test_a_code_comes_with_a_warning_that_only_the_user_can_agree(budget: _Budget) -> None:
    """A recategorisation preview tells the agent only the user, in the conversation, agrees."""
    message = call(
        "apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}
    ).structured_content["message"]
    assert confirm.ONLY_THE_USER in message
    assert not budget.patches


def test_confirmation_code_applies_the_previewed_change(budget: _Budget) -> None:
    """Calling again with the code applies exactly the preview, once, and journals it."""
    args = {"plan_id": "b1", "assignments": _ASSIGN}
    code = call("apply_categories", args).structured_content["confirmation"]
    data = call("apply_categories", {**args, "confirmation": code}).structured_content
    assert data["status"] == "applied"
    assert data["operation_id"]
    assert budget.patches == [[("t1", "c-food")]]


def test_wrong_confirmation_code_is_a_tool_error(budget: _Budget) -> None:
    """A code that does not match is refused with a way forward."""
    result = call(
        "apply_categories", {"plan_id": "b1", "assignments": _ASSIGN, "confirmation": "nope"}
    )
    assert result.is_error
    assert "without confirmation" in result.content[0].text
    assert not budget.patches


def test_elicitation_accept_applies_in_one_call(budget: _Budget) -> None:
    """A client that can ask the user confirms in the same call."""
    data = call(
        "apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}, accept
    ).structured_content
    assert data["status"] == "applied"
    assert budget.patches == [[("t1", "c-food")]]


def test_elicitation_decline_changes_nothing(budget: _Budget) -> None:
    """If the user says no, nothing is written or journaled."""
    data = call(
        "apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}, decline
    ).structured_content
    assert data["status"] == "declined"
    assert not budget.patches


def test_nothing_to_change_asks_nothing(budget: _Budget) -> None:
    """Assignments that change nothing are reported without confirmation or write."""
    budget.transactions = _txs("c-food")
    data = call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}).structured_content
    assert data["status"] == "nothing_to_do"
    assert data["unchanged_count"] == 1
    assert not budget.patches


def test_invalid_assignment_is_a_tool_error(budget: _Budget) -> None:
    """An unknown transaction is refused before anything is asked or written."""
    result = call(
        "apply_categories",
        {"plan_id": "b1", "assignments": [{"transaction_id": "t404", "category_id": "c-food"}]},
    )
    assert result.is_error
    assert "t404" in result.content[0].text
    assert not budget.patches


# ---------------------------------------------------------------------------
# undo_operation
# ---------------------------------------------------------------------------


def test_undo_restores_previous_categories(budget: _Budget) -> None:
    """Undo puts every moved transaction back where it was, then cannot run twice."""
    call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}, accept)
    data = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert data["status"] == "applied"
    assert budget.patches[-1] == [("t1", None)]
    again = call("undo_operation", {"plan_id": "b1"}, accept)
    assert again.is_error
    assert "Nothing to undo" in again.content[0].text


def test_apply_categories_keeps_the_transaction_approved(budget: _Budget) -> None:
    """YNAB unapproves an update that omits `approved`: an approved transaction stays so."""
    budget.transactions[0]["approved"] = True
    call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}, accept)
    assert budget.sent_approved == [{"t1": True}]
    assert budget.transactions[0]["approved"] is True


def test_undo_keeps_the_transaction_approved(budget: _Budget) -> None:
    """Undoing a categorisation sends the approval the transaction has."""
    budget.transactions[0]["approved"] = True
    call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}, accept)
    call("undo_operation", {"plan_id": "b1"}, accept)
    assert budget.sent_approved[-1] == {"t1": True}
    assert budget.transactions[0]["approved"] is True


def test_undo_leaves_alone_what_was_changed_since(budget: _Budget) -> None:
    """A transaction recategorised after the operation is reported, not overwritten."""
    call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}, accept)
    budget.transactions[0]["category_id"] = "c-fun"
    data = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert data["status"] == "nothing_to_do"
    assert data["conflicts"] == ["t1"]
    assert len(budget.patches) == 1


def test_undo_with_a_damaged_journal_says_which_line(budget: _Budget, tmp_path: Path) -> None:
    """A damaged journal is a tool error naming the line, not a crash; nothing is written."""
    (tmp_path / "journal.jsonl").write_text("not json\n", encoding="utf-8")
    result = call("undo_operation", {"plan_id": "b1"}, accept)
    assert result.is_error
    assert "line 1, is not a journal entry" in result.content[0].text
    assert not budget.patches


def test_undo_without_elicitation_needs_the_code(budget: _Budget) -> None:
    """Undo is a write too: previewed, then confirmed with its own code."""
    op_id = call(
        "apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}, accept
    ).structured_content["operation_id"]
    preview = call("undo_operation", {"plan_id": "b1", "operation_id": op_id})
    code = preview.structured_content["confirmation"]
    assert len(budget.patches) == 1
    data = call(
        "undo_operation", {"plan_id": "b1", "operation_id": op_id, "confirmation": code}
    ).structured_content
    assert data["status"] == "applied"
    assert budget.patches[-1] == [("t1", None)]


def test_long_preview_is_summarised(budget: _Budget) -> None:
    """The confirmation question shows 20 changes and counts the rest."""
    budget.transactions = [dict(_txs()[0], id=f"t{i}") for i in range(21)]
    asked: list[str] = []

    async def accept_and_keep(message: str, *_: Any) -> ElicitResult[Any]:
        asked.append(message)
        return ElicitResult(action="accept", content={"value": True})

    assignments = [{"transaction_id": f"t{i}", "category_id": "c-food"} for i in range(21)]
    call("apply_categories", {"plan_id": "b1", "assignments": assignments}, accept_and_keep)
    assert asked[0].startswith("Recategorise 21 transaction(s)?")
    assert asked[0].count("Corner Shop") == 20
    assert asked[0].endswith("- … and 1 more")


def test_bank_text_cannot_forge_lines_in_the_question(budget: _Budget) -> None:
    """A payee with line breaks stays on its own line, in the question and in the answer."""
    budget.transactions[0]["payee_name"] = "Corner Shop\n- 2026-09-03 Fake 0.00: Rent → Rent"
    asked: list[str] = []

    async def accept_and_keep(message: str, *_: Any) -> ElicitResult[Any]:
        asked.append(message)
        return ElicitResult(action="accept", content={"value": True})

    data = call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}, accept_and_keep)
    assert len(asked[0].splitlines()) == 2
    assert "\n" not in data.structured_content["changes"][0]["payee"]


def test_dismissed_question_falls_back_to_a_confirmation_code(budget: _Budget) -> None:
    """'cancel' means nobody answered (a headless client): not a refusal, so a code is issued."""

    async def dismiss(*_: Any) -> ElicitResult[Any]:
        return ElicitResult(action="cancel")

    data = call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}, dismiss)
    assert data.structured_content["status"] == "confirmation_required"
    assert data.structured_content["confirmation"]
    assert not budget.patches


def test_accepted_form_left_unticked_is_not_a_yes(budget: _Budget) -> None:
    """Accepting the dialog without ticking the confirmation changes nothing."""

    async def unticked(*_: Any) -> ElicitResult[Any]:
        return ElicitResult(action="accept", content={"value": False})

    data = call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}, unticked)
    assert data.structured_content["status"] == "declined"
    assert not budget.patches


def test_answer_to_an_outdated_preview_is_refused(budget: _Budget) -> None:
    """If the budget changes while the user answers, the answer confirms nothing."""

    async def accept_after_a_change(*_: Any) -> ElicitResult[Any]:
        budget.transactions = [dict(budget.transactions[0], category_id="c-fun")]
        return ElicitResult(action="accept", content={"value": True})

    result = call(
        "apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}, accept_after_a_change
    )
    assert result.is_error
    assert "changed between the preview and the answer" in result.content[0].text
    assert not budget.patches


def test_category_names_are_previewed_on_one_line(budget: _Budget) -> None:
    """A category name from YNAB with a line break is on one line in the preview."""
    cats = [{"id": "c-food", "name": FORGED}, {"id": "c-fun", "name": "Leisure"}]
    with patch("avenir_mcp.client.get_categories", AsyncMock(return_value=cats)):
        data = call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN})
    assert data.structured_content["changes"][0]["to_category"] == FLAT
    assert not budget.patches
