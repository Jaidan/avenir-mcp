# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""flag_transactions through the MCP protocol: validate, preview, confirm, apply, undo."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from .mcp_helpers import accept, call, decline


class FakeFlags:
    """Transactions and their flags, as YNAB holds them, and the changes asked of it."""

    def __init__(self) -> None:
        """Start with no flag, a blue flag and an empty one, as YNAB returns them."""
        self.flags: dict[str, str | None] = {"t1": None, "t2": "blue", "t3": ""}
        self.sent: list[list[tuple[str, str | None]]] = []
        self.approved: dict[str, bool] = {"t1": True, "t2": False, "t3": True}

    async def get_transactions(self, _plan_id: str, **_: Any) -> list[dict[str, Any]]:
        """The transactions, as YNAB returns them."""
        payees = {"t1": "CB MARKET FRESH", "t2": "STREAMFLIX", "t3": "RAIL CO"}
        return [
            {
                "id": tx_id,
                "date": "2026-09-1" + tx_id[1],
                "amount": -12340,
                "payee_name": payees[tx_id],
                "flag_color": color,
                "approved": self.approved[tx_id],
                "deleted": False,
            }
            for tx_id, color in self.flags.items()
        ]

    async def set_flags(
        self, _plan_id: str, changes: list[tuple[str, str | None]], approved: dict[str, bool]
    ) -> list[str]:
        """Record and apply the flags and the approval sent with them."""
        self.sent.append(changes)
        self.approved.update({tx_id: approved[tx_id] for tx_id, _ in changes})
        self.flags.update(changes)
        return [tx_id for tx_id, _ in changes]


@pytest.fixture(name="ynab")
def _ynab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeFlags]:
    fake = FakeFlags()
    monkeypatch.setenv("AVENIR_MCP_JOURNAL", str(tmp_path / "journal.jsonl"))
    with (
        patch("avenir_mcp.client.get_transactions", fake.get_transactions),
        patch("avenir_mcp.client.set_flags", fake.set_flags),
    ):
        yield fake


_FLAGS = [
    {"transaction_id": "t1", "color": "red"},
    {"transaction_id": "t2", "color": None},
]


def _args(**extra: Any) -> dict[str, Any]:
    return {"plan_id": "b1", "flags": _FLAGS, **extra}


def test_the_preview_gives_each_flag_before_and_after(ynab: FakeFlags) -> None:
    """Without elicitation: every change with its transaction, and a code; nothing sent."""
    preview = call("flag_transactions", _args()).structured_content
    assert preview["status"] == "confirmation_required"
    assert preview["changes"] == [
        {
            "transaction_id": "t1",
            "date": "2026-09-11",
            "payee": "CB MARKET FRESH",
            "amount": -12.34,
            "from_color": None,
            "to_color": "red",
        },
        {
            "transaction_id": "t2",
            "date": "2026-09-12",
            "payee": "STREAMFLIX",
            "amount": -12.34,
            "from_color": "blue",
            "to_color": None,
        },
    ]
    assert not ynab.sent


def test_the_code_applies_the_flags_in_one_request(ynab: FakeFlags) -> None:
    """With the code, both flags are set together, and the result names the operation."""
    code = call("flag_transactions", _args()).structured_content["confirmation"]
    done = call("flag_transactions", _args(confirmation=code)).structured_content
    assert done["status"] == "applied"
    assert done["operation_id"]
    assert ynab.sent == [[("t1", "red"), ("t2", None)]]


def test_the_user_is_asked_one_readable_question(ynab: FakeFlags) -> None:
    """One line per transaction, bank text on one line, the colours before and after."""
    asked: list[str] = []

    async def record(message: str, *_: Any) -> Any:
        asked.append(message)
        return await accept()

    call("flag_transactions", _args(), record)
    assert asked == [
        "Change the flag of 2 transaction(s)?\n"
        "- 2026-09-11 CB MARKET FRESH -12.34: none → red\n"
        "- 2026-09-12 STREAMFLIX -12.34: blue → none"
    ]
    assert ynab.sent


def test_a_flag_already_set_is_left_out(ynab: FakeFlags) -> None:
    """Asking for the colour a transaction already has changes nothing; an empty flag is none."""
    result = call(
        "flag_transactions",
        _args(flags=[{"transaction_id": "t2", "color": "blue"}, {"transaction_id": "t3"}]),
    ).structured_content
    assert result["status"] == "nothing_to_do"
    assert result["unchanged_count"] == 2
    assert not ynab.sent


def test_declined_flags_change_nothing(ynab: FakeFlags) -> None:
    """If the user says no, no flag changes."""
    assert call("flag_transactions", _args(), decline).structured_content["status"] == "declined"
    assert not ynab.sent


def test_the_journal_keeps_the_colours_and_nothing_else(ynab: FakeFlags, tmp_path: Path) -> None:
    """What undo needs: ids and colours; no payee, memo or amount."""
    call("flag_transactions", _args(), accept)
    line = json.loads((tmp_path / "journal.jsonl").read_text(encoding="utf-8"))
    assert line["kind"] == "flag"
    assert line["details"] == {
        "changes": [
            {"transaction_id": "t1", "from": None, "to": "red"},
            {"transaction_id": "t2", "from": "blue", "to": None},
        ]
    }
    assert ynab.sent


def test_flag_transactions_keeps_the_transaction_approved(ynab: FakeFlags) -> None:
    """Flagging sends each transaction's own approval: approved stays, unapproved stays."""
    call("flag_transactions", _args(), accept)
    assert ynab.approved == {"t1": True, "t2": False, "t3": True}


def test_undo_of_a_flag_keeps_the_transaction_approved(ynab: FakeFlags) -> None:
    """Putting a flag back does not unapprove the transaction."""
    call("flag_transactions", _args(), accept)
    ynab.approved.update({"t1": False, "t2": True})
    call("undo_operation", {"plan_id": "b1"}, accept)
    assert ynab.approved == {"t1": False, "t2": True, "t3": True}


def test_undo_puts_the_flags_back(ynab: FakeFlags) -> None:
    """undo_operation restores every flag, in one confirmed request."""
    call("flag_transactions", _args(), accept)
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "applied"
    assert ynab.flags == {"t1": None, "t2": "blue", "t3": ""}
    assert ynab.sent[-1] == [("t1", None), ("t2", "blue")]


def test_undo_leaves_a_flag_changed_since_alone(ynab: FakeFlags) -> None:
    """A flag the user changed again is not overwritten, and is listed as a conflict."""
    call("flag_transactions", _args(), accept)
    ynab.flags["t1"] = "green"
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "applied"
    assert undo["conflicts"] == ["t1"]
    assert ynab.flags["t1"] == "green"
    assert ynab.flags["t2"] == "blue"


def test_undo_with_every_flag_changed_since_does_nothing(ynab: FakeFlags) -> None:
    """If no flag is still as the operation left it, nothing is asked nor sent."""
    call("flag_transactions", _args(), accept)
    ynab.flags.update({"t1": "green", "t2": "purple"})
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "nothing_to_do"
    assert undo["conflicts"] == ["t1", "t2"]
    assert len(ynab.sent) == 1


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ([{"transaction_id": "t404", "color": "red"}], "t404"),
        ([{"transaction_id": "t1", "color": "pink"}], "flags.0.color"),
        ([{"transaction_id": "t1", "color": "red"}, {"transaction_id": "t1"}], "twice"),
        ([], "at least one"),
    ],
)
def test_invalid_flags_are_refused_before_asking(
    ynab: FakeFlags, flags: list[dict[str, Any]], expected: str
) -> None:
    """An unknown transaction or colour, a transaction named twice, or none: refused first."""
    result = call("flag_transactions", _args(flags=flags), accept)
    assert result.is_error
    assert expected in result.content[0].text
    assert not ynab.sent
