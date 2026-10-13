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

from avenir_mcp import confirm, journal, retry, server

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
        self.approved_ids: list[list[str]] = []
        self.approve_fails: Exception | None = None

    @property
    def approved_sent(self) -> dict[str, bool]:
        """Every approval sent with a category, the latest for each transaction."""
        return {k: v for sent in self.sent_approved for k, v in sent.items()}

    async def approve_transactions(self, _budget_id: str, tx_ids: list[str]) -> dict[str, int]:
        """Record the bulk approval and apply it, or fail as YNAB can."""
        if self.approve_fails is not None:
            raise self.approve_fails
        self.approved_ids.append(tx_ids)
        for tx in self.transactions:
            if tx["id"] in tx_ids:
                tx["approved"] = True
        return {"approved": len(tx_ids)}

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
        patch("avenir_mcp.client.approve_transactions", fake.approve_transactions),
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
    budget.transactions.append(budget.transactions[0] | {"id": "t2", "approved": False})
    budget.transactions[0]["approved"] = True
    assign = [*_ASSIGN, {"transaction_id": "t2", "category_id": "c-food"}]
    call("apply_categories", {"plan_id": "b1", "assignments": assign}, accept)
    call("undo_operation", {"plan_id": "b1"}, accept)
    assert budget.sent_approved[-1] == {"t1": True, "t2": False}


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


# ---------------------------------------------------------------------------
# apply_categories with approve
# ---------------------------------------------------------------------------


def _unapproved_t2(category_id: str = "c-fun") -> dict[str, Any]:
    return {**_txs()[0], "id": "t2", "category_id": category_id, "approved": False}


def test_apply_can_approve_in_the_same_call(budget: _Budget) -> None:
    """approve=true sends approved with the category, and approves what was already right."""
    budget.transactions.append(_unapproved_t2())
    args = {
        "plan_id": "b1",
        "approve": True,
        "assignments": [*_ASSIGN, {"transaction_id": "t2", "category_id": "c-fun"}],
    }
    result = call("apply_categories", args, accept).structured_content
    assert result["status"] == "applied"
    assert budget.approved_sent == {"t1": True}
    assert budget.approved_ids == [["t2"]]
    assert [c["transaction_id"] for c in result["approvals"]] == ["t2"]
    assert result["unchanged_count"] == 0
    assert "restores the categories only" in result["message"]


def test_without_approve_nothing_is_approved(budget: _Budget) -> None:
    """The default keeps each approval and approves nothing else."""
    budget.transactions.append(_unapproved_t2())
    args = {
        "plan_id": "b1",
        "assignments": [*_ASSIGN, {"transaction_id": "t2", "category_id": "c-fun"}],
    }
    result = call("apply_categories", args, accept).structured_content
    assert budget.approved_sent == {"t1": False}
    assert budget.approved_ids == []
    assert result["approvals"] == []
    assert result["unchanged_count"] == 1


def test_the_question_says_and_approve_and_shows_each_row(budget: _Budget) -> None:
    """Rows only approved are listed in the question, after the changes."""
    budget.transactions.append(_unapproved_t2())
    asked: list[str] = []

    async def accept_and_keep(message: str, *_: Any) -> ElicitResult[Any]:
        asked.append(message)
        return ElicitResult(action="accept", content={"value": True})

    assign = [*_ASSIGN, {"transaction_id": "t2", "category_id": "c-fun"}]
    call(
        "apply_categories",
        {"plan_id": "b1", "assignments": assign, "approve": True},
        accept_and_keep,
    )
    assert asked[0].splitlines() == [
        "Recategorise and approve 2 transaction(s)?",
        "- 2026-09-02 Corner Shop -7.25: no category → Groceries",
        "- 2026-09-02 Corner Shop -7.25: Leisure (approve)",
    ]


def test_long_approving_preview_counts_the_rows_beyond_twenty(budget: _Budget) -> None:
    """Changes and rows to approve share the 20-line cap."""
    budget.transactions = [dict(_txs()[0], id=f"t{i}") for i in range(15)]
    budget.transactions += [_unapproved_t2() | {"id": f"a{i}"} for i in range(10)]
    asked: list[str] = []

    async def accept_and_keep(message: str, *_: Any) -> ElicitResult[Any]:
        asked.append(message)
        return ElicitResult(action="accept", content={"value": True})

    assign = [{"transaction_id": f"t{i}", "category_id": "c-food"} for i in range(15)]
    assign += [{"transaction_id": f"a{i}", "category_id": "c-fun"} for i in range(10)]
    call(
        "apply_categories",
        {"plan_id": "b1", "assignments": assign, "approve": True},
        accept_and_keep,
    )
    lines = asked[0].splitlines()
    assert lines[0] == "Recategorise and approve 25 transaction(s)?"
    assert sum("(approve)" in line for line in lines) == 5
    assert lines[-1] == "- … and 5 more"


def test_approving_only_is_something_to_do(budget: _Budget) -> None:
    """Every category already right but unapproved: approved, nothing journaled to undo."""
    budget.transactions = [_unapproved_t2("c-food") | {"id": "t1"}]
    result = call(
        "apply_categories", {"plan_id": "b1", "assignments": _ASSIGN, "approve": True}, accept
    ).structured_content
    assert result["status"] == "applied"
    assert result["operation_id"] is None
    assert "cannot be undone" in result["message"]
    assert budget.approved_ids == [["t1"]]
    assert not budget.patches
    assert call("undo_operation", {"plan_id": "b1"}, accept).is_error


def test_a_code_for_categorising_cannot_approve(budget: _Budget) -> None:
    """The code binds the approve flag too."""
    budget.transactions[0]["approved"] = True
    code = call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN}).structured_content[
        "confirmation"
    ]
    again = call(
        "apply_categories",
        {"plan_id": "b1", "assignments": _ASSIGN, "approve": True, "confirmation": code},
    )
    assert again.is_error
    assert not budget.patches


def test_an_approving_code_works_for_assignments_in_another_order(budget: _Budget) -> None:
    """The code confirms the same assignments, whatever their order."""
    budget.transactions.append(_unapproved_t2())
    assign = [*_ASSIGN, {"transaction_id": "t2", "category_id": "c-fun"}]
    args = {"plan_id": "b1", "approve": True}
    code = call("apply_categories", {**args, "assignments": assign}).structured_content[
        "confirmation"
    ]
    done = call(
        "apply_categories", {**args, "assignments": assign[::-1], "confirmation": code}
    ).structured_content
    assert done["status"] == "applied"
    assert budget.approved_ids == [["t2"]]


def test_a_code_is_stale_once_a_row_to_approve_changes(budget: _Budget) -> None:
    """A row to approve whose amount changed since the preview is not what was confirmed."""
    budget.transactions.append(_unapproved_t2())
    assign = [*_ASSIGN, {"transaction_id": "t2", "category_id": "c-fun"}]
    args = {"plan_id": "b1", "approve": True, "assignments": assign}
    code = call("apply_categories", args).structured_content["confirmation"]
    budget.transactions[1]["amount"] = -99990
    result = call("apply_categories", {**args, "confirmation": code})
    assert result.is_error
    assert not budget.patches
    assert not budget.approved_ids


_REFUSED = RuntimeError("YNAB 400: refused")
_NO_ANSWER = retry.YnabUnavailable("YNAB did not answer")


@pytest.mark.parametrize(
    ("failure", "outcome"),
    [
        (_REFUSED, "nothing was approved"),
        (_NO_ANSWER, "the approval may or may not have applied: check in YNAB"),
    ],
)
def test_a_failed_approval_names_the_operation_to_undo(
    budget: _Budget, tmp_path: Path, failure: Exception, outcome: str
) -> None:
    """Categories are journaled before approving: if approving fails, the error says how to undo."""
    budget.transactions.append(_unapproved_t2())
    budget.approve_fails = failure
    assign = [*_ASSIGN, {"transaction_id": "t2", "category_id": "c-fun"}]
    result = call(
        "apply_categories", {"plan_id": "b1", "assignments": assign, "approve": True}, accept
    )
    assert result.is_error
    text = result.content[0].text
    assert str(failure) in text
    assert outcome in text
    assert budget.patches == [[("t1", "c-food")]]
    entry = journal.Journal(tmp_path / "journal.jsonl").find("b1")
    assert entry is not None
    assert f"undo_operation with operation_id {entry.operation_id} reverts them" in text


def test_a_refused_approval_of_rows_only_says_nothing_changed(budget: _Budget) -> None:
    """YNAB refused and there was no category to change: nothing changed at all."""
    budget.transactions = [_unapproved_t2("c-food") | {"id": "t1"}]
    budget.approve_fails = _REFUSED
    result = call(
        "apply_categories", {"plan_id": "b1", "assignments": _ASSIGN, "approve": True}, accept
    )
    assert result.is_error
    assert result.content[0].text.endswith("nothing was approved and nothing was changed.")
    assert not budget.patches


def test_an_unanswered_approval_of_rows_only_says_to_check(budget: _Budget) -> None:
    """YNAB answered nothing: the approval's outcome is unknown, and nothing claims otherwise."""
    budget.transactions = [_unapproved_t2("c-food") | {"id": "t1"}]
    budget.approve_fails = _NO_ANSWER
    result = call(
        "apply_categories", {"plan_id": "b1", "assignments": _ASSIGN, "approve": True}, accept
    )
    assert result.is_error
    text = result.content[0].text
    assert text.endswith("the approval may or may not have applied: check in YNAB.")
    assert "nothing was changed" not in text


def test_undo_of_an_approving_operation_keeps_the_approval(budget: _Budget) -> None:
    """Undo restores the category and leaves the transaction approved."""
    call("apply_categories", {"plan_id": "b1", "assignments": _ASSIGN, "approve": True}, accept)
    assert budget.transactions[0]["approved"] is True
    call("undo_operation", {"plan_id": "b1"}, accept)
    assert budget.patches[-1] == [("t1", None)]
    assert budget.transactions[0]["approved"] is True
