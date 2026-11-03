# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""split_transaction through the MCP protocol: validate, preview, confirm, apply."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp.client.elicitation import ElicitResult

from .mcp_helpers import FLAT, FORGED, accept, asking, call, decline, one_line

_ACCOUNTS = [{"id": "acc", "name": "Checking", "on_budget": True}]
_CATS = [{"id": "c-food", "name": "Groceries"}, {"id": "c-home", "name": "Household"}]
_TX = {"id": "t1", "account_id": "acc", "date": "2026-09-12", "amount": -86400}
_TX |= {"payee_name": "Organic Market", "category_id": None}
_LINES = [
    {"amount": -81.15, "category_id": "c-food"},
    {"amount": -5.25, "category_id": "c-home", "memo": "Dish soap"},
]


@pytest.fixture(name="ynab")
def _ynab() -> Iterator[AsyncMock]:
    """A fake YNAB; the mock it yields records the splits it is asked to make."""
    splits = AsyncMock(return_value=None)
    with (
        patch("avenir_mcp.client.get_accounts", AsyncMock(return_value=_ACCOUNTS)),
        patch("avenir_mcp.client.get_categories", AsyncMock(return_value=_CATS)),
        patch("avenir_mcp.client.get_transactions", AsyncMock(return_value=[_TX])),
        patch("avenir_mcp.client.split_transaction", splits),
    ):
        yield splits


def _args(**extra: Any) -> dict[str, Any]:
    return {"plan_id": "b1", "transaction_id": "t1", "lines": _LINES, **extra}


def test_split_is_previewed_then_applied_with_the_code(ynab: AsyncMock) -> None:
    """Without elicitation: a preview and a code first, the split only with the code."""
    preview = call("split_transaction", _args()).structured_content
    assert preview["status"] == "confirmation_required"
    assert preview["payee"] == "Organic Market"
    assert preview["amount"] == -86.40
    assert preview["lines"] == [
        {"amount": -81.15, "category": "Groceries", "memo": None},
        {"amount": -5.25, "category": "Household", "memo": "Dish soap"},
    ]
    ynab.assert_not_called()
    done = call("split_transaction", _args(confirmation=preview["confirmation"]))
    assert done.structured_content["status"] == "applied"
    ynab.assert_called_once_with(
        "b1",
        "t1",
        [
            {"amount": -81.15, "category_id": "c-food", "memo": None},
            {"amount": -5.25, "category_id": "c-home", "memo": "Dish soap"},
        ],
        approved=False,
    )


@pytest.mark.parametrize("approved", [True, False])
def test_split_transaction_keeps_the_transaction_approved(ynab: AsyncMock, approved: bool) -> None:
    """An approved transaction is sent approved, so YNAB does not unapprove it."""
    tx = _TX | {"approved": approved}
    with patch("avenir_mcp.client.get_transactions", AsyncMock(return_value=[tx])):
        call("split_transaction", _args(), accept)
    assert ynab.call_args.kwargs == {"approved": approved}


def test_a_transfer_to_a_tracking_account_goes_through_the_same_steps(ynab: AsyncMock) -> None:
    """The one splittable transfer gets the usual preview, code, call and undo wording."""
    accounts = [*_ACCOUNTS, {"id": "brokerage", "name": "Brokerage", "on_budget": False}]
    tx = _TX | {"transfer_account_id": "brokerage", "payee_name": "Transfer : Brokerage"}
    with (
        patch("avenir_mcp.client.get_accounts", AsyncMock(return_value=accounts)),
        patch("avenir_mcp.client.get_transactions", AsyncMock(return_value=[tx])),
    ):
        preview = call("split_transaction", _args()).structured_content
        assert preview["status"] == "confirmation_required"
        ynab.assert_not_called()
        done = call("split_transaction", _args(confirmation=preview["confirmation"]))
    assert done.structured_content["status"] == "applied"
    assert "in YNAB" in done.structured_content["message"]
    ynab.assert_called_once()


def test_the_question_warns_that_undo_happens_in_ynab(ynab: AsyncMock) -> None:
    """The user is told, before saying yes, that undo_operation cannot revert a split."""
    asked: list[str] = []

    async def remember(message: str, *_: Any) -> ElicitResult[Any]:
        asked.append(message)
        return ElicitResult(action="accept", content={"value": True})

    result = call("split_transaction", _args(), remember).structured_content
    assert "Organic Market" in asked[0]
    assert "Groceries" in asked[0]
    assert "in YNAB" in asked[0]
    assert result["status"] == "applied"
    assert "in YNAB" in result["message"]
    ynab.assert_called_once()


def test_accepted_split_is_applied(ynab: AsyncMock) -> None:
    """A yes in the client applies it at once."""
    assert call("split_transaction", _args(), accept).structured_content["status"] == "applied"
    ynab.assert_called_once()


def test_declined_split_changes_nothing(ynab: AsyncMock) -> None:
    """If the user says no, nothing is split."""
    assert call("split_transaction", _args(), decline).structured_content["status"] == "declined"
    ynab.assert_not_called()


def test_a_code_for_other_lines_is_refused(ynab: AsyncMock) -> None:
    """A code confirms the lines previewed, not different ones."""
    code = call("split_transaction", _args()).structured_content["confirmation"]
    other = [
        {"amount": -80.0, "category_id": "c-food"},
        {"amount": -6.40, "category_id": "c-home"},
    ]
    result = call("split_transaction", _args(lines=other, confirmation=code))
    assert result.is_error
    ynab.assert_not_called()


def test_lines_that_do_not_add_up_are_refused_before_asking(ynab: AsyncMock) -> None:
    """The totals are checked first: the user is never asked about a wrong split."""
    wrong = [{"amount": -81.15, "category_id": "c-food"}, {"amount": -4.0, "category_id": "c-home"}]
    result = call("split_transaction", _args(lines=wrong), accept)
    assert result.is_error
    assert "-85.15" in result.content[0].text
    ynab.assert_not_called()


def test_a_memo_with_a_nul_character_is_refused_before_asking(ynab: AsyncMock) -> None:
    """YNAB answers 400 to a NUL character: the line is refused before the user is asked."""
    lines = [_LINES[0], dict(_LINES[1], memo="Dish\x00soap")]
    result = call("split_transaction", _args(lines=lines), accept)
    assert result.is_error
    assert "U+0000" in result.content[0].text
    ynab.assert_not_called()


def test_category_names_cannot_forge_lines_in_the_question(ynab: AsyncMock) -> None:
    """A category name with a line break stays on one line, in the question and the preview."""
    asked: list[str] = []
    cats = [{"id": "c-food", "name": FORGED}, {"id": "c-home", "name": "Household"}]
    with patch("avenir_mcp.client.get_categories", AsyncMock(return_value=cats)):
        data = call("split_transaction", _args(), asking(asked)).structured_content
    assert one_line(asked[0])
    assert data["lines"][0]["category"] == FLAT
    ynab.assert_called_once()


@pytest.mark.parametrize("approved", [True, False])
def test_split_can_approve_in_the_same_call(ynab: AsyncMock, approved: bool) -> None:
    """approve=true sends the split approved, whatever the transaction had; the user is told."""
    asked: list[str] = []
    tx = _TX | {"approved": approved}
    with patch("avenir_mcp.client.get_transactions", AsyncMock(return_value=[tx])):
        call("split_transaction", _args(approve=True), asking(asked))
    assert ynab.call_args.kwargs == {"approved": True}
    assert asked[0].startswith(
        "Split 2026-09-12 Organic Market -86.40 into 2 lines and approve it?"
    )


def test_a_code_for_splitting_cannot_approve(ynab: AsyncMock) -> None:
    """The code binds the approve flag: a split previewed without approving cannot approve."""
    code = call("split_transaction", _args()).structured_content["confirmation"]
    result = call("split_transaction", _args(approve=True, confirmation=code))
    assert result.is_error
    ynab.assert_not_called()


def test_auto_confirm_still_asks_before_a_split(
    ynab: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AVENIR_MCP_AUTO_CONFIRM=1 skips only undoable writes: undo cannot revert a split."""
    monkeypatch.setenv("AVENIR_MCP_AUTO_CONFIRM", "1")
    preview = call("split_transaction", _args()).structured_content
    assert preview["status"] == "confirmation_required"
    ynab.assert_not_called()
