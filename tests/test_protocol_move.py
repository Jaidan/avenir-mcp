# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""move_money through the MCP protocol: one preview, one confirmation, one undo."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from avenir_mcp import retry

from .fake_month import FakeMonth, serving
from .mcp_helpers import FLAT, FORGED, accept, asking, call, decline, one_line


@pytest.fixture(name="month")
def _month(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeMonth]:
    fake = FakeMonth(
        {"c-food": "Restaurants", "c-fun": "Tennis", "c-car": "Car"},
        {"c-food": 120000, "c-fun": 80000, "c-car": 0},
    )
    fake.spent["c-food"] = -142500
    with serving(fake, tmp_path, monkeypatch):
        yield fake


_ARGS = {
    "plan_id": "b1",
    "month": "2026-09-01",
    "from_category_id": "c-fun",
    "to_category_id": "c-food",
    "amount": 30.0,
}


def test_a_move_is_one_preview_naming_both_categories(month: FakeMonth) -> None:
    """The preview gives both categories, before and after, and what the source keeps."""
    preview = call("move_money", _ARGS).structured_content
    assert preview["status"] == "confirmation_required"
    assert preview["from_category"] == {
        "category_id": "c-fun",
        "name": "Tennis",
        "from_amount": 80.0,
        "to_amount": 50.0,
        "available_after": 50.0,
    }
    assert preview["to_category"] == {
        "category_id": "c-food",
        "name": "Restaurants",
        "from_amount": 120.0,
        "to_amount": 150.0,
        "available_after": 7.5,
    }
    assert not month.sets


def test_one_confirmation_applies_both_amounts(month: FakeMonth) -> None:
    """The code sets the source first, then the destination, and journals one operation."""
    preview = call("move_money", _ARGS).structured_content
    done = call("move_money", {**_ARGS, "confirmation": preview["confirmation"]})
    assert done.structured_content["status"] == "applied"
    assert done.structured_content["operation_id"]
    assert month.sets == [("2026-09-01", "c-fun", 50.0), ("2026-09-01", "c-food", 150.0)]


def test_the_user_is_asked_one_readable_question(month: FakeMonth) -> None:
    """The question says the amount, both categories and the month."""
    asked: list[str] = []

    async def record(message: str, *_: Any) -> Any:
        asked.append(message)
        return await accept()

    call("move_money", _ARGS, record)
    assert len(month.sets) == 2
    assert asked == [
        "Move 30.00 from Tennis to Restaurants for 2026-09-01?\n"
        "- Tennis: 80.00 → 50.00\n"
        "- Restaurants: 120.00 → 150.00"
    ]


def test_one_undo_restores_both_categories(month: FakeMonth) -> None:
    """undo_operation puts both amounts back, in one confirmed step."""
    call("move_money", _ARGS, accept)
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "applied"
    assert month.budgeted == {"c-food": 120000, "c-fun": 80000, "c-car": 0}


def test_undo_leaves_both_alone_when_one_changed_since(month: FakeMonth) -> None:
    """If either amount moved again, undo writes nothing and names the category."""
    call("move_money", _ARGS, accept)
    month.budgeted["c-food"] = 999000
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "nothing_to_do"
    assert undo["conflicts"] == ["c-food"]
    assert len(month.sets) == 2


def test_the_journal_line_holds_ids_and_the_two_budgeted_amounts(
    month: FakeMonth, tmp_path: Path
) -> None:
    """What undo needs, as for a budget change: ids and amounts assigned, nothing else."""
    call("move_money", _ARGS, accept)
    line = json.loads((tmp_path / "journal.jsonl").read_text(encoding="utf-8"))
    assert line["kind"] == "move"
    assert line["details"] == {
        "month": "2026-09-01",
        "changes": [
            {"category_id": "c-fun", "from": 80000, "to": 50000},
            {"category_id": "c-food", "from": 120000, "to": 150000},
        ],
    }
    assert month.sets


def test_a_failed_second_write_puts_the_first_back(month: FakeMonth) -> None:
    """If YNAB refuses the destination, the source gets its amount back and the error says so."""
    month.failing_calls = {2}
    result = call("move_money", _ARGS, accept)
    assert result.is_error
    assert "nothing was moved" in result.content[0].text
    assert month.budgeted["c-fun"] == 80000
    assert month.sets == [("2026-09-01", "c-fun", 50.0), ("2026-09-01", "c-fun", 80.0)]


def test_a_second_write_with_no_answer_also_puts_the_first_back(month: FakeMonth) -> None:
    """A destination write YNAB never answered puts the source back and says to go and look."""
    lost = retry.no_answer("patch", httpx.ReadTimeout("no answer"), 1)
    month.failure = retry.YnabUnavailable(lost)
    month.failing_calls = {2}
    result = call("move_money", _ARGS, accept)
    assert "may or may not be applied" in result.content[0].text
    assert result.is_error
    assert month.sets == [("2026-09-01", "c-fun", 50.0), ("2026-09-01", "c-fun", 80.0)]
    assert month.budgeted["c-fun"] == 80000


def test_a_failed_put_back_says_what_to_fix_in_ynab(month: FakeMonth) -> None:
    """If putting the source back fails too, the error gives the amount to set by hand."""
    month.failing_calls = {2, 3}
    result = call("move_money", _ARGS, accept)
    assert result.is_error
    assert "set Tennis back to 80.00 in YNAB" in result.content[0].text
    assert month.budgeted["c-fun"] == 50000


def test_declined_move_writes_nothing(month: FakeMonth) -> None:
    """If the user says no, both amounts stay."""
    assert call("move_money", _ARGS, decline).structured_content["status"] == "declined"
    assert not month.sets


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"from_category_id": "c-404"}, "c-404"),
        ({"to_category_id": "c-404"}, "c-404"),
        ({"to_category_id": "c-fun"}, "two different categories"),
        ({"amount": 0}, "greater than 0"),
        ({"amount": -5}, "greater than 0"),
        ({"month": "2026-09"}, "YYYY-MM-01"),
    ],
)
def test_invalid_move_is_a_tool_error(
    month: FakeMonth, args: dict[str, Any], expected: str
) -> None:
    """Unknown or identical categories, a non-positive amount or a bad month: refused first."""
    result = call("move_money", {**_ARGS, **args})
    assert result.is_error
    assert expected in result.content[0].text
    assert not month.sets


def test_category_names_cannot_forge_lines_in_the_question(month: FakeMonth) -> None:
    """Both category names stay on one line, in the question and the preview."""
    month.names["c-fun"] = FORGED
    asked: list[str] = []
    data = call("move_money", _ARGS, asking(asked)).structured_content
    assert one_line(asked[0])
    assert data["from_category"]["name"] == FLAT


def test_category_names_cannot_forge_lines_in_the_undo_question(month: FakeMonth) -> None:
    """Undoing a move names both categories on one line."""
    call("move_money", _ARGS, accept)
    month.names["c-food"] = FORGED
    asked: list[str] = []
    call("undo_operation", {"plan_id": "b1"}, asking(asked))
    assert one_line(asked[0])


def test_a_failed_undo_write_says_which_category_is_back(month: FakeMonth) -> None:
    """Undoing a move stops at a failed write, says what is back, and stays undoable."""
    call("move_money", _ARGS, accept)
    month.failing_calls = {4}
    result = call("undo_operation", {"plan_id": "b1"}, accept)
    assert result.is_error
    assert "Restored: Restaurants." in result.content[0].text
    assert "Not restored: Tennis." in result.content[0].text
    assert "undo_operation" in result.content[0].text
