# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""set_category_budget through the MCP protocol: preview, confirm, journal, undo."""

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
    fake = FakeMonth({"c-food": "Restaurants", "c-fun": "Leisure"}, {"c-food": 200000, "c-fun": 0})
    with serving(fake, tmp_path, monkeypatch):
        yield fake


_ARGS = {"plan_id": "b1", "month": "2026-10-01", "category_id": "c-food", "amount": 150.0}


def test_budget_change_is_previewed_in_currency_then_applied_with_the_code(
    month: FakeMonth,
) -> None:
    """The preview names the category and both amounts; the code applies it."""
    preview = call("set_category_budget", _ARGS).structured_content
    assert preview["status"] == "confirmation_required"
    assert (preview["category"], preview["from_amount"], preview["to_amount"]) == (
        "Restaurants",
        200.0,
        150.0,
    )
    assert not month.sets
    done = call("set_category_budget", {**_ARGS, "confirmation": preview["confirmation"]})
    assert done.structured_content["status"] == "applied"
    assert month.sets == [("2026-10-01", "c-food", 150.0)]


def test_budget_change_is_undone_to_the_previous_amount(month: FakeMonth) -> None:
    """undo_operation puts the category back to what it had."""
    call("set_category_budget", _ARGS, accept)
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "applied"
    assert month.sets[-1] == ("2026-10-01", "c-food", 200.0)


def test_undo_leaves_a_budget_changed_since_alone(month: FakeMonth) -> None:
    """If the amount moved again after the operation, undo does not overwrite it."""
    call("set_category_budget", _ARGS, accept)
    month.budgeted["c-food"] = 999000
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "nothing_to_do"
    assert undo["conflicts"] == ["c-food"]
    assert len(month.sets) == 1


def test_same_amount_changes_nothing(month: FakeMonth) -> None:
    """Setting the current amount again asks and writes nothing."""
    data = call("set_category_budget", {**_ARGS, "amount": 200.0}).structured_content
    assert data["status"] == "nothing_to_do"
    assert not month.sets


def test_declined_budget_change_writes_nothing(month: FakeMonth) -> None:
    """If the user says no, the amount stays."""
    assert call("set_category_budget", _ARGS, decline).structured_content["status"] == "declined"
    assert not month.sets


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"category_id": "c-404"}, "c-404"),
        ({"month": "2026-10"}, "YYYY-MM-01"),
    ],
)
def test_invalid_budget_change_is_a_tool_error(
    month: FakeMonth, args: dict[str, Any], expected: str
) -> None:
    """Unknown category or malformed month is refused before anything is asked."""
    result = call("set_category_budget", {**_ARGS, **args})
    assert result.is_error
    assert expected in result.content[0].text
    assert not month.sets


def test_declined_undo_keeps_the_new_amount(month: FakeMonth) -> None:
    """If the user refuses the undo, the budget keeps its new amount."""
    call("set_category_budget", _ARGS, accept)
    undo = call("undo_operation", {"plan_id": "b1"}, decline).structured_content
    assert undo["status"] == "declined"
    assert month.sets == [("2026-10-01", "c-food", 150.0)]


def test_a_category_name_cannot_forge_lines_in_the_question(month: FakeMonth) -> None:
    """A category name with a line break stays on one line, in the question and the preview."""
    month.names["c-food"] = FORGED
    asked: list[str] = []
    data = call("set_category_budget", _ARGS, asking(asked)).structured_content
    assert one_line(asked[0])
    assert data["category"] == FLAT


def test_a_category_name_cannot_forge_lines_in_the_undo_question(month: FakeMonth) -> None:
    """Undoing a budget change names the category on one line."""
    call("set_category_budget", _ARGS, accept)
    month.names["c-food"] = FORGED
    asked: list[str] = []
    call("undo_operation", {"plan_id": "b1"}, asking(asked))
    assert one_line(asked[0])


# ---------------------------------------------------------------------------
# set_category_budgets: several categories, one confirmation
# ---------------------------------------------------------------------------


@pytest.fixture(name="many")
def _many(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeMonth]:
    fake = FakeMonth(
        {"c-food": "Restaurants", "c-fun": "Leisure", "c-car": "Car", "c-gift": "Gifts"},
        {"c-food": 200000, "c-fun": 0, "c-car": 50000, "c-gift": 10000},
    )
    with serving(fake, tmp_path, monkeypatch):
        yield fake


_MANY = {
    "plan_id": "b1",
    "month": "2026-10-01",
    "budgets": [
        {"category_id": "c-food", "amount": 150.0},
        {"category_id": "c-fun", "amount": 40.0},
        {"category_id": "c-car", "amount": 50.0},
        {"category_id": "c-gift", "amount": 25.5},
    ],
}


def test_several_budgets_are_previewed_together_and_asked_once(many: FakeMonth) -> None:
    """Every change is listed from → to; an amount already in place is only counted."""
    preview = call("set_category_budgets", _MANY).structured_content
    assert preview["status"] == "confirmation_required"
    assert preview["month"] == "2026-10-01"
    assert preview["unchanged_count"] == 1
    assert preview["changes"] == [
        {
            "category_id": "c-food",
            "category": "Restaurants",
            "from_amount": 200.0,
            "to_amount": 150.0,
        },
        {"category_id": "c-fun", "category": "Leisure", "from_amount": 0.0, "to_amount": 40.0},
        {"category_id": "c-gift", "category": "Gifts", "from_amount": 10.0, "to_amount": 25.5},
    ]
    assert not many.sets
    asked: list[str] = []
    call("set_category_budgets", _MANY, asking(asked))
    assert asked == [
        "Budget 3 categories for 2026-10-01?\n"
        "- Restaurants: 200.00 → 150.00\n"
        "- Leisure: 0.00 → 40.00\n"
        "- Gifts: 10.00 → 25.50"
    ]


def test_one_confirmation_applies_every_budget_in_order_and_journals_once(
    many: FakeMonth, tmp_path: Path
) -> None:
    """The code writes each changed category in input order, as one undoable operation."""
    preview = call("set_category_budgets", _MANY).structured_content
    done = call("set_category_budgets", {**_MANY, "confirmation": preview["confirmation"]})
    data = done.structured_content
    assert data["status"] == "applied"
    assert data["operation_id"] in data["message"]
    assert many.sets == [
        ("2026-10-01", "c-food", 150.0),
        ("2026-10-01", "c-fun", 40.0),
        ("2026-10-01", "c-gift", 25.5),
    ]
    lines = (tmp_path / "journal.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    line = json.loads(lines[0])
    assert (line["kind"], line["operation_id"]) == ("budgets", data["operation_id"])
    assert line["details"] == {
        "month": "2026-10-01",
        "changes": [
            {"category_id": "c-food", "from": 200000, "to": 150000},
            {"category_id": "c-fun", "from": 0, "to": 40000},
            {"category_id": "c-gift", "from": 10000, "to": 25500},
        ],
    }


def test_budgets_already_in_place_change_nothing(many: FakeMonth) -> None:
    """When every amount is already set, nothing is asked or written."""
    budgets = [{"category_id": "c-car", "amount": 50.0}, {"category_id": "c-fun", "amount": 0}]
    data = call("set_category_budgets", {**_MANY, "budgets": budgets}).structured_content
    assert (data["status"], data["unchanged_count"], data["changes"]) == ("nothing_to_do", 2, [])
    assert not many.sets


def test_declined_budgets_write_nothing(many: FakeMonth) -> None:
    """If the user says no, every amount stays."""
    assert call("set_category_budgets", _MANY, decline).structured_content["status"] == "declined"
    assert not many.sets


def test_a_code_confirms_only_the_budgets_previewed(many: FakeMonth) -> None:
    """A code from one preview does not apply different amounts."""
    preview = call("set_category_budgets", _MANY).structured_content
    other = [{"category_id": "c-food", "amount": 1.0}]
    result = call(
        "set_category_budgets",
        {**_MANY, "budgets": other, "confirmation": preview["confirmation"]},
    )
    assert result.is_error or result.structured_content["status"] != "applied"
    assert not many.sets


@pytest.mark.parametrize(
    ("budgets", "expected"),
    [
        ([{"category_id": "c-404", "amount": 1.0}], "c-404"),
        (
            [{"category_id": "c-food", "amount": 1.0}, {"category_id": "c-food", "amount": 2.0}],
            "c-food more than once",
        ),
        ([], "at least 1"),
        ([{"category_id": f"c-{n}", "amount": 1.0} for n in range(101)], "at most 100"),
    ],
)
def test_invalid_budgets_are_a_tool_error(
    many: FakeMonth, budgets: list[dict[str, Any]], expected: str
) -> None:
    """Unknown or repeated categories, and an empty or too long list, are refused first."""
    result = call("set_category_budgets", {**_MANY, "budgets": budgets})
    assert result.is_error
    assert expected in result.content[0].text
    assert not many.sets


def test_a_malformed_month_is_refused_for_several_budgets(many: FakeMonth) -> None:
    """The month is checked as for one category."""
    result = call("set_category_budgets", {**_MANY, "month": "2026-10"})
    assert result.is_error
    assert "YYYY-MM-01" in result.content[0].text
    assert not many.sets


def test_a_failed_write_stops_and_journals_what_was_applied(
    many: FakeMonth, tmp_path: Path
) -> None:
    """YNAB refusing the third write leaves the first two applied, undoable, and named."""
    many.failing_calls = {3}
    result = call("set_category_budgets", _MANY, accept)
    assert result.is_error
    text = result.content[0].text
    line = json.loads((tmp_path / "journal.jsonl").read_text(encoding="utf-8"))
    assert line["kind"] == "budgets"
    assert [c["category_id"] for c in line["details"]["changes"]] == ["c-food", "c-fun"]
    assert line["operation_id"] in text
    assert "Applied: Restaurants, Leisure" in text
    assert "Not applied: Gifts" in text
    assert many.sets == [("2026-10-01", "c-food", 150.0), ("2026-10-01", "c-fun", 40.0)]
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "applied"
    assert many.budgeted == {"c-food": 200000, "c-fun": 0, "c-car": 50000, "c-gift": 10000}


def test_a_failed_first_write_changes_and_journals_nothing(many: FakeMonth, tmp_path: Path) -> None:
    """When the first write fails, the error says nothing was changed."""
    many.failing_calls = {1}
    result = call("set_category_budgets", _MANY, accept)
    assert result.is_error
    assert "Nothing was changed" in result.content[0].text
    assert not (tmp_path / "journal.jsonl").exists()
    assert not many.sets


def test_one_undo_restores_every_budget(many: FakeMonth) -> None:
    """undo_operation puts every category back, in one confirmed step."""
    asked: list[str] = []
    call("set_category_budgets", _MANY, accept)
    undo = call("undo_operation", {"plan_id": "b1"}, asking(asked)).structured_content
    assert undo["status"] == "applied"
    assert undo["conflicts"] == []
    assert many.budgeted == {"c-food": 200000, "c-fun": 0, "c-car": 50000, "c-gift": 10000}
    assert len(asked) == 1


def test_undo_restores_the_others_when_one_budget_changed_since(many: FakeMonth) -> None:
    """A category changed again is left alone and named; the rest go back."""
    call("set_category_budgets", _MANY, accept)
    many.budgeted["c-fun"] = 999000
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "applied"
    assert undo["conflicts"] == ["c-fun"]
    assert many.budgeted == {"c-food": 200000, "c-fun": 999000, "c-car": 50000, "c-gift": 10000}


def test_undo_leaves_everything_alone_when_every_budget_changed_since(many: FakeMonth) -> None:
    """If no category still has the amount set, undo writes nothing."""
    budgets = [{"category_id": "c-food", "amount": 1.0}]
    call("set_category_budgets", {**_MANY, "budgets": budgets}, accept)
    many.budgeted["c-food"] = 5000
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert (undo["status"], undo["conflicts"]) == ("nothing_to_do", ["c-food"])
    assert len(many.sets) == 1


def test_declined_undo_keeps_the_new_budgets(many: FakeMonth) -> None:
    """If the user refuses the undo, every category keeps its new amount."""
    call("set_category_budgets", _MANY, accept)
    undo = call("undo_operation", {"plan_id": "b1"}, decline).structured_content
    assert undo["status"] == "declined"
    assert len(many.sets) == 3


def test_category_names_cannot_forge_lines_in_the_budgets_questions(many: FakeMonth) -> None:
    """Each name stays on its own line, in the question, the preview and the undo."""
    many.names["c-food"] = FORGED
    asked: list[str] = []
    data = call("set_category_budgets", _MANY, asking(asked)).structured_content
    assert one_line(asked[0])
    assert asked[0].count("\n") == 3
    assert data["changes"][0]["category"] == FLAT
    call("set_category_budgets", _MANY, accept)
    call("undo_operation", {"plan_id": "b1"}, asking(asked))
    assert one_line(asked[-1])


def _lost() -> retry.YnabUnavailable:
    """A write YNAB read and never answered."""
    return retry.YnabUnavailable(retry.no_answer("patch", httpx.ReadTimeout("no answer"), 1))


def test_an_unanswered_write_may_have_landed_and_stops_the_rest(
    many: FakeMonth, tmp_path: Path
) -> None:
    """With no answer, the category may be set: the error says to check it, not that it failed."""
    many.failure = _lost()
    many.failing_calls = {2}
    result = call("set_category_budgets", _MANY, accept)
    assert result.is_error
    text = result.content[0].text
    assert "Leisure may have been applied: check it in YNAB" in text
    assert "refused" not in text
    assert "Applied: Restaurants." in text
    assert "Not applied: Gifts." in text
    line = json.loads((tmp_path / "journal.jsonl").read_text(encoding="utf-8"))
    assert line["operation_id"] in text


def test_an_unanswered_last_write_leaves_nothing_unapplied(many: FakeMonth) -> None:
    """When the last category gets no answer, every other one is applied."""
    many.failure = _lost()
    many.failing_calls = {3}
    text = call("set_category_budgets", _MANY, accept).content[0].text
    assert "Gifts may have been applied: check it in YNAB" in text
    assert "Not applied" not in text
    assert "Applied: Restaurants, Leisure." in text


def test_an_unanswered_first_write_changes_nothing_else(many: FakeMonth, tmp_path: Path) -> None:
    """No answer on the first category: nothing else written, nothing journaled."""
    many.failure = _lost()
    many.failing_calls = {1}
    text = call("set_category_budgets", _MANY, accept).content[0].text
    assert "Restaurants may have been applied: check it in YNAB" in text
    assert "Nothing else was changed" in text
    assert not (tmp_path / "journal.jsonl").exists()


def test_a_failed_undo_write_says_what_was_restored_and_can_be_retried(many: FakeMonth) -> None:
    """The undo stops, names what is back and what is not, and stays undoable for the rest."""
    call("set_category_budgets", _MANY, accept)
    many.failing_calls = {5}
    result = call("undo_operation", {"plan_id": "b1"}, accept)
    assert result.is_error
    text = result.content[0].text
    assert "Restored: Restaurants." in text
    assert "Not restored: Leisure, Gifts." in text
    many.failing_calls = set()
    retried = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert (retried["status"], retried["conflicts"]) == ("applied", ["c-food"])
    assert many.budgeted == {"c-food": 200000, "c-fun": 0, "c-car": 50000, "c-gift": 10000}


def test_a_first_failed_undo_write_restores_nothing(many: FakeMonth) -> None:
    """When the first restore fails, the error says nothing is back yet."""
    call("set_category_budgets", _MANY, accept)
    many.failing_calls = {4}
    text = call("undo_operation", {"plan_id": "b1"}, accept).content[0].text
    assert "Restored: none." in text
    assert "Not restored: Restaurants, Leisure, Gifts." in text


def test_auto_confirm_applies_a_budget_change_at_once(
    month: FakeMonth, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AVENIR_MCP_AUTO_CONFIRM=1: an undoable write applies in the first call."""
    monkeypatch.setenv("AVENIR_MCP_AUTO_CONFIRM", "1")
    assert call("set_category_budget", _ARGS).structured_content["status"] == "applied"
    assert month.sets == [("2026-10-01", "c-food", 150.0)]


def test_auto_confirm_still_asks_before_an_undo(
    month: FakeMonth, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An undo cannot itself be undone: AVENIR_MCP_AUTO_CONFIRM=1 still asks."""
    call("set_category_budget", _ARGS, accept)
    monkeypatch.setenv("AVENIR_MCP_AUTO_CONFIRM", "1")
    undo = call("undo_operation", {"plan_id": "b1"}).structured_content
    assert undo["status"] == "confirmation_required"
    assert month.sets == [("2026-10-01", "c-food", 150.0)]
