# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""set_category_target through the MCP protocol: preview, confirmation, undo."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from .mcp_helpers import FORGED, accept, asking, call, decline, one_line

_FREQ = {"monthly": 1, "weekly": 2, "yearly": 13}


class FakeTargets:
    """Categories and their targets, as YNAB holds them, and the changes asked of it."""

    def __init__(self) -> None:
        """Start with a category without a target and one funded monthly in YNAB's app."""
        self.categories: dict[str, dict[str, Any]] = {
            "c-hol": {"id": "c-hol", "name": "Holidays", "goal_type": None, "goal_target": None},
            "c-car": {"id": "c-car", "name": "Car", "goal_type": "MF", "goal_target": 30_000},
            "c-visa": {
                "id": "c-visa",
                "name": "Visa",
                "category_group_name": "Credit Card Payments",
                "goal_type": None,
                "goal_target": None,
            },
        }
        self.sent: list[tuple[str, dict[str, Any]]] = []

    async def get_categories(self, _plan_id: str) -> list[dict[str, Any]]:
        """The categories, as YNAB lists them."""
        return [dict(c) for c in self.categories.values()]

    async def set_category_target(
        self, _plan_id: str, category_id: str, fields: dict[str, Any]
    ) -> dict[str, Any]:
        """Record and apply the change the way YNAB does, and refuse what YNAB refuses."""
        self.sent.append((category_id, fields))
        cat = self.categories[category_id]
        if "goal_frequency" in fields and cat.get("category_group_name") == "Credit Card Payments":
            raise ValueError("YNAB: goal_frequency is not supported for this category")
        if fields.get("goal_target") is None:
            cat.update(goal_type=None, goal_target=None, goal_target_date=None)
        elif "goal_target_date" in fields:
            cat.update(
                goal_type="NEED",
                goal_target=fields["goal_target"],
                goal_target_date=fields["goal_target_date"],
                goal_cadence=0,
            )
        elif "goal_frequency" in fields:
            cat.update(
                goal_type="NEED",
                goal_target=fields["goal_target"],
                goal_cadence=_FREQ[fields["goal_frequency"]],
                goal_target_date=None,
            )
        else:
            cat.update(goal_type=cat["goal_type"] or "NEED", goal_target=fields["goal_target"])
            cat.setdefault("goal_cadence", 1)
        return cat


@pytest.fixture(name="ynab")
def _ynab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeTargets]:
    fake = FakeTargets()
    monkeypatch.setenv("AVENIR_MCP_JOURNAL", str(tmp_path / "journal.jsonl"))
    with (
        patch("avenir_mcp.client.get_categories", fake.get_categories),
        patch("avenir_mcp.client.set_category_target", fake.set_category_target),
    ):
        yield fake


_HOLIDAYS = {"plan_id": "b1", "category_id": "c-hol", "amount": 1200.0, "by_date": "2027-06-01"}


def test_a_target_by_a_date_is_previewed_then_set(ynab: FakeTargets) -> None:
    """Preview before and after, then the code sets it, journaled for undo."""
    preview = call("set_category_target", _HOLIDAYS).structured_content
    assert preview["status"] == "confirmation_required"
    assert (preview["before"], preview["after"]) == ("no target", "1200.00 by 2027-06-01")
    assert preview["undoable"] is True
    assert not ynab.sent
    done = call("set_category_target", {**_HOLIDAYS, "confirmation": preview["confirmation"]})
    assert done.structured_content["operation_id"]
    assert ynab.sent == [("c-hol", {"goal_target": 1_200_000, "goal_target_date": "2027-06-01"})]


def test_the_user_is_asked_one_readable_question(ynab: FakeTargets) -> None:
    """The question names the category and both targets."""
    asked: list[str] = []

    async def record(message: str, *_: Any) -> Any:
        asked.append(message)
        return await accept()

    call("set_category_target", _HOLIDAYS, record)
    assert asked == ["Set the target of Holidays: no target → 1200.00 by 2027-06-01?"]
    assert ynab.sent


def test_undo_removes_a_target_that_was_not_there(ynab: FakeTargets) -> None:
    """undo_operation sends YNAB the removal, and the category has no target again."""
    call("set_category_target", _HOLIDAYS, accept)
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "applied"
    assert ynab.sent[-1] == ("c-hol", {"goal_target": None})
    assert ynab.categories["c-hol"]["goal_target"] is None


def test_undo_leaves_a_target_changed_since_alone(ynab: FakeTargets) -> None:
    """If the user changed the target in YNAB since, undo writes nothing."""
    call("set_category_target", _HOLIDAYS, accept)
    ynab.categories["c-hol"]["goal_target"] = 999_000
    undo = call("undo_operation", {"plan_id": "b1"}, accept).structured_content
    assert undo["status"] == "nothing_to_do"
    assert undo["conflicts"] == ["c-hol"]
    assert len(ynab.sent) == 1


def test_changing_only_the_amount_keeps_the_kind_and_undo_restores_it(ynab: FakeTargets) -> None:
    """Monthly funding from YNAB's app, 30 → 45: undo puts 30 back, same kind."""
    args = {"plan_id": "b1", "category_id": "c-car", "amount": 45.0}
    done = call("set_category_target", args, accept).structured_content
    assert (done["before"], done["after"]) == ("30.00 (monthly funding)", "45.00 (monthly funding)")
    call("undo_operation", {"plan_id": "b1"}, accept)
    assert ynab.sent[-1] == ("c-car", {"goal_target": 30_000})
    assert ynab.categories["c-car"]["goal_type"] == "MF"


def test_replacing_a_kind_the_api_cannot_set_is_said_before_and_not_journaled(
    ynab: FakeTargets, tmp_path: Path
) -> None:
    """Monthly funding replaced by a weekly target: the question warns, nothing to undo after."""
    asked: list[str] = []

    async def record(message: str, *_: Any) -> Any:
        asked.append(message)
        return await accept()

    args = {"plan_id": "b1", "category_id": "c-car", "amount": 20.0, "frequency": "weekly"}
    done = call("set_category_target", args, record).structured_content
    assert "cannot bring back the previous target (30.00 (monthly funding))" in asked[0]
    assert done["undoable"] is False
    assert done["operation_id"] is None
    assert not (tmp_path / "journal.jsonl").exists()
    assert ynab.categories["c-car"]["goal_type"] == "NEED"


def test_the_journal_keeps_the_target_to_restore_and_nothing_else(
    ynab: FakeTargets, tmp_path: Path
) -> None:
    """Ids and target amounts only, as for a budget change."""
    call("set_category_target", _HOLIDAYS, accept)
    line = json.loads((tmp_path / "journal.jsonl").read_text(encoding="utf-8"))
    assert line["kind"] == "target"
    assert line["details"] == {
        "category_id": "c-hol",
        "undo": {"goal_target": None},
        "after": "1200.00 by 2027-06-01",
    }
    assert ynab.sent


def test_the_same_target_again_changes_nothing(ynab: FakeTargets) -> None:
    """Asking for the target already set sends nothing."""
    args = {"plan_id": "b1", "category_id": "c-car", "amount": 30.0}
    assert call("set_category_target", args).structured_content["status"] == "nothing_to_do"
    assert not ynab.sent


def test_declined_target_changes_nothing(ynab: FakeTargets) -> None:
    """If the user says no, the target stays."""
    assert (
        call("set_category_target", _HOLIDAYS, decline).structured_content["status"] == "declined"
    )
    assert not ynab.sent


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"category_id": "c-404", "amount": 10.0}, "c-404"),
        (
            {
                "category_id": "c-hol",
                "amount": 10.0,
                "by_date": "2027-01-01",
                "frequency": "monthly",
            },
            "either a date or a frequency",
        ),
        ({"category_id": "c-hol", "amount": -1.0}, "greater than 0"),
        ({"category_id": "c-hol", "frequency": "monthly"}, "no date"),
        ({"category_id": "c-hol", "amount": 10.0, "frequency": "daily"}, "frequency"),
        (
            {"category_id": "c-visa", "amount": 10.0, "frequency": "monthly"},
            "no frequency on a credit card payment category",
        ),
    ],
)
def test_invalid_targets_are_refused_before_asking(
    ynab: FakeTargets, args: dict[str, Any], expected: str
) -> None:
    """Refused first: unknown category, date and frequency, bad amount or rhythm, card rhythm."""
    result = call("set_category_target", {"plan_id": "b1", **args}, accept)
    assert result.is_error
    assert expected in result.content[0].text
    assert not ynab.sent


def test_a_category_name_cannot_forge_lines_in_the_question(ynab: FakeTargets) -> None:
    """A category name with a line break stays on one line."""
    ynab.categories["c-hol"]["name"] = FORGED
    asked: list[str] = []
    call("set_category_target", _HOLIDAYS, asking(asked))
    assert one_line(asked[0])


def test_a_category_name_cannot_forge_lines_in_the_undo_question(ynab: FakeTargets) -> None:
    """Undoing a target names the category on one line."""
    call("set_category_target", _HOLIDAYS, accept)
    ynab.categories["c-hol"]["name"] = FORGED
    asked: list[str] = []
    call("undo_operation", {"plan_id": "b1"}, asking(asked))
    assert one_line(asked[0])


@pytest.mark.usefixtures("ynab")
def test_auto_confirm_applies_a_target_undo_can_restore(monkeypatch: pytest.MonkeyPatch) -> None:
    """AVENIR_MCP_AUTO_CONFIRM=1: set at once, journaled for undo."""
    monkeypatch.setenv("AVENIR_MCP_AUTO_CONFIRM", "1")
    done = call("set_category_target", _HOLIDAYS).structured_content
    assert (done["status"], bool(done["operation_id"])) == ("applied", True)


def test_auto_confirm_still_asks_before_a_target_undo_cannot_restore(
    ynab: FakeTargets, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A target the API cannot set back is not undoable: the user is asked."""
    monkeypatch.setenv("AVENIR_MCP_AUTO_CONFIRM", "1")
    args = {"plan_id": "b1", "category_id": "c-car", "amount": 20.0, "frequency": "weekly"}
    done = call("set_category_target", args).structured_content
    assert done["status"] == "confirmation_required"
    assert not ynab.sent
