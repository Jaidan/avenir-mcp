# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""ask() on paths the in-memory client does not take: older protocol, odd replies."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastmcp.exceptions import ToolError
from fastmcp.server.elicitation import AcceptedElicitation, CancelledElicitation
from mcp import types

from avenir_mcp import confirm, writes


@dataclass
class _Session:
    can_ask: bool = True

    def check_client_capability(self, _capability: Any) -> bool:
        """Whether this client can answer questions."""
        return self.can_ask


@dataclass
class _Request:
    protocol_version: str


@dataclass
class _Ctx:
    """Just what ask() reads from a FastMCP context."""

    protocol_version: str
    answer: Any = None
    input_responses: dict[str, Any] | None = None
    request_state: str | None = None
    session: _Session = field(default_factory=_Session)

    @property
    def request_context(self) -> _Request:
        """The negotiated protocol version."""
        return _Request(self.protocol_version)

    async def elicit(self, _question: str, _response_type: type) -> Any:
        """The user's canned answer."""
        return self.answer


def _ask(ctx: _Ctx, subject: object = "change") -> Any:
    run = confirm.ask(ctx, "b1", subject, "Apply?", None, undoable=True)  # type: ignore[arg-type]
    return asyncio.run(run)


def test_older_protocol_asks_during_the_call() -> None:
    """Before 2026-07-28 the server asks the client directly."""
    assert _ask(_Ctx("2025-11-25", answer=AcceptedElicitation(data=True))) == "applied"
    assert _ask(_Ctx("2025-11-25", answer=AcceptedElicitation(data=False))) == "declined"


def test_older_protocol_dismissed_question_gives_a_code() -> None:
    """A dismissed question on an older connection falls back to a code too."""
    code = _ask(_Ctx("2025-11-25", answer=CancelledElicitation()))
    assert code not in ("applied", "declined")
    assert confirm.CONFIRMATIONS.consume(code, "b1", "change")


def test_modern_reply_of_another_kind_counts_as_no_answer() -> None:
    """A reply that is not a form answer confirms nothing: a code is issued."""
    reply = types.ListRootsResult(roots=[])
    ctx = _Ctx(
        "2026-07-28",
        input_responses={"confirm": reply},
        request_state=writes.fingerprint("b1", "change"),
    )
    code = _ask(ctx)
    assert code not in ("applied", "declined")


# ---------------------------------------------------------------------------
# AVENIR_MCP_REQUIRE_ELICITATION=1: only the user, in the client, can say yes
# ---------------------------------------------------------------------------


@pytest.fixture(name="required")
def _required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AVENIR_MCP_REQUIRE_ELICITATION", "1")


@pytest.mark.usefixtures("required")
def test_required_client_confirmation_refuses_codes() -> None:
    """A code could be relayed by the agent alone: it is refused."""
    code = confirm.CONFIRMATIONS.issue("b1", "change")
    ctx: Any = _Ctx("2025-11-25")
    with pytest.raises(ToolError, match="AVENIR_MCP_REQUIRE_ELICITATION"):
        asyncio.run(confirm.ask(ctx, "b1", "change", "Apply?", code, undoable=True))


@pytest.mark.usefixtures("required")
def test_required_client_confirmation_needs_a_client_that_can_ask() -> None:
    """A client that cannot ask gets a refusal, not a code."""
    ctx = _Ctx("2025-11-25", session=_Session(can_ask=False))
    with pytest.raises(ToolError, match="cannot ask"):
        _ask(ctx)


@pytest.mark.usefixtures("required")
def test_required_client_confirmation_treats_a_dismissed_question_as_no() -> None:
    """Nobody answered: nothing is applied, and no code is issued."""
    assert _ask(_Ctx("2025-11-25", answer=CancelledElicitation())) == "declined"


@pytest.mark.usefixtures("required")
def test_required_client_confirmation_still_accepts_a_yes() -> None:
    """The user's own yes, given in the client, applies the change."""
    assert _ask(_Ctx("2025-11-25", answer=AcceptedElicitation(data=True))) == "applied"


def test_every_code_comes_with_the_warning_that_only_the_user_can_agree() -> None:
    """Writes other than recategorisation say it too, before their question."""
    stop = confirm.not_applied("code-1", "Budget Rent for 2026-09-01: 800.00 → 50.00?")
    assert stop is not None
    assert stop.message.startswith(f"Nothing changed yet. {confirm.ONLY_THE_USER} Budget Rent")
    assert "in this conversation" in confirm.ONLY_THE_USER
    assert "Never use the code on your own initiative" in confirm.ONLY_THE_USER
    assert "memo" in confirm.ONLY_THE_USER


# ---------------------------------------------------------------------------
# 2026-07-28 answers to an approving recategorisation
# ---------------------------------------------------------------------------

_CATS = [{"id": "c-food", "name": "Groceries"}, {"id": "c-fun", "name": "Leisure"}]


def _tx(tx_id: str, category_id: str | None, amount: int = -7250) -> dict[str, Any]:
    return {
        "id": tx_id,
        "date": "2026-09-02",
        "amount": amount,
        "payee_name": "Corner Shop",
        "category_id": category_id,
        "approved": False,
    }


def _approving(txs: list[dict[str, Any]], order: slice = slice(None)) -> writes.Plan:
    assign = [("t1", "c-food"), ("t2", "c-fun")][order]
    return writes.plan_categorization(
        txs,
        _CATS,
        [writes.Assignment(transaction_id=t, category_id=c) for t, c in assign],
        approve=True,
    )


def _write(ctx: _Ctx, plan: writes.Plan) -> Any:
    action = "Recategorise and approve"
    run = confirm.write_plan(ctx, "b1", plan, action, None, undoable=True)  # type: ignore[arg-type]
    return asyncio.run(run)[0]


@pytest.fixture(name="ynab")
def _ynab(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> list[Any]:
    """A fake YNAB recording category writes; the journal in a temporary file."""
    monkeypatch.setenv("AVENIR_MCP_JOURNAL", str(tmp_path / "journal.jsonl"))
    calls: list[Any] = []

    async def categorise(_plan: str, moves: Any, approved: Any) -> list[str]:
        calls.append(("categorise", moves, approved))
        return []

    monkeypatch.setattr("avenir_mcp.client.set_transaction_categories", categorise)
    return calls


def _answered(request: Any) -> _Ctx:
    yes = types.ElicitResult(action="accept", content={"value": True})
    return _Ctx("2026-07-28", input_responses={"confirm": yes}, request_state=request.request_state)


def test_a_modern_answer_applies_the_same_assignments_in_another_order(ynab: list[Any]) -> None:
    """The answer confirms the plan previewed, whatever the order of its assignments."""
    txs = [_tx("t1", None), _tx("t2", "c-fun")]
    request = _write(_Ctx("2026-07-28"), _approving(txs))
    assert isinstance(request, types.InputRequiredResult)
    result = _write(_answered(request), _approving(txs, slice(None, None, -1)))
    assert result.status == "applied"
    assert ynab == [("categorise", [("t1", "c-food")], {"t1": True})]
    assert result.approvals == []


def test_write_plan_claims_no_approval_it_did_not_make(ynab: list[Any]) -> None:
    """Rows only to approve are the caller's: write_plan reports no approval and no undo."""
    plan = _approving([_tx("t1", "c-food"), _tx("t2", "c-fun")])
    request = _write(_Ctx("2026-07-28"), plan)
    result = _write(_answered(request), plan)
    assert result.status == "applied"
    assert result.message == "No category changed."
    assert result.approvals == []
    assert result.operation_id is None
    assert ynab == []


def test_a_modern_answer_is_refused_once_a_row_to_approve_changes(ynab: list[Any]) -> None:
    """A row to approve whose amount changed since is not what the user agreed to."""
    request = _write(_Ctx("2026-07-28"), _approving([_tx("t1", None), _tx("t2", "c-fun")]))
    changed = _approving([_tx("t1", None), _tx("t2", "c-fun", amount=-99990)])
    with pytest.raises(ToolError, match="plan changed"):
        _write(_answered(request), changed)
    assert ynab == []


def test_a_modern_answer_without_approve_cannot_approve(ynab: list[Any]) -> None:
    """An answer to a plain recategorisation does not confirm one that also approves."""
    txs = [_tx("t1", None) | {"approved": True}]
    plain = writes.plan_categorization(
        txs, _CATS, [writes.Assignment(transaction_id="t1", category_id="c-food")]
    )
    request = _write(_Ctx("2026-07-28"), plain)
    with pytest.raises(ToolError, match="plan changed"):
        _write(_answered(request), _approving(txs, slice(0, 1)))
    assert ynab == []


def test_a_long_list_shows_twenty_rows_and_how_many_more() -> None:
    """The question names the action and the count, then at most 20 rows."""
    rows = [f"2026-09-{i:02} Shop -1.00: Groceries" for i in range(1, 23)]
    question = confirm.rows_question("Approve", rows)
    lines = question.split("\n")
    assert lines[0] == "Approve 22 transaction(s)?"
    assert lines[1] == "- 2026-09-01 Shop -1.00: Groceries"
    assert len(lines) == 22
    assert lines[-1] == "- … and 2 more"


def test_a_short_list_shows_every_row() -> None:
    """Twenty rows or fewer: no "more" line."""
    assert confirm.rows_question("Approve", ["a", "b"]) == "Approve 2 transaction(s)?\n- a\n- b"


def test_a_list_names_what_it_counts() -> None:
    """Rows other than transactions are counted under their own name."""
    question = confirm.rows_question("Budget", ["a"], "categories for 2026-10-01")
    assert question == "Budget 1 categories for 2026-10-01?\n- a"


# ---------------------------------------------------------------------------
# AVENIR_MCP_AUTO_CONFIRM=1 (fork only): undoable writes apply without asking
# ---------------------------------------------------------------------------


@pytest.fixture(name="auto")
def _auto(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AVENIR_MCP_AUTO_CONFIRM", "1")


@dataclass
class _NeverAsk(_Ctx):
    """A client whose user must not be asked."""

    async def elicit(self, _question: str, _response_type: type) -> Any:
        """Fail the test: auto-confirm asks nobody."""
        pytest.fail("auto-confirm asked the user")


@pytest.mark.usefixtures("auto")
def test_auto_confirm_applies_without_asking(caplog: pytest.LogCaptureFixture) -> None:
    """No question, no code: applied, and one warning giving only the size, no bank text."""
    question = "Recategorise 3 transaction(s)?\n- 2026-09-02 Corner Shop -7.25: Groceries"
    with caplog.at_level("WARNING", logger="avenir_mcp.confirm"):
        ctx: Any = _NeverAsk("2025-11-25")
        assert (
            asyncio.run(confirm.ask(ctx, "b1", ["a", "b", "c"], question, None, undoable=True))
            == "applied"
        )
    assert [r.getMessage() for r in caplog.records] == [
        "Auto-confirmed a write of 3 item(s) (AVENIR_MCP_AUTO_CONFIRM=1)"
    ]


@pytest.mark.usefixtures("auto")
def test_auto_confirm_applies_on_a_modern_connection_too() -> None:
    """No input request is returned: the call applies at once."""
    assert _ask(_NeverAsk("2026-07-28")) == "applied"


@pytest.mark.usefixtures("auto")
def test_auto_confirm_still_asks_before_a_write_undo_cannot_revert() -> None:
    """undoable=False: the user is asked as usual."""
    ctx = _Ctx("2025-11-25", answer=AcceptedElicitation(data=False))
    run = confirm.ask(ctx, "b1", "change", "Apply?", None, undoable=False)  # type: ignore[arg-type]
    assert asyncio.run(run) == "declined"


@pytest.mark.usefixtures("auto")
def test_auto_confirm_checks_a_code_it_was_given() -> None:
    """A code passed in is spent as usual: a wrong one is refused, not ignored."""
    ctx: Any = _NeverAsk("2025-11-25")
    with pytest.raises(ToolError, match="unknown, expired"):
        asyncio.run(confirm.ask(ctx, "b1", "change", "Apply?", "made-up", undoable=True))
    code = confirm.CONFIRMATIONS.issue("b1", "change")
    assert asyncio.run(confirm.ask(ctx, "b1", "change", "Apply?", code, undoable=True)) == "applied"


def test_auto_confirm_is_off_unless_set_to_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any other value asks as usual."""
    monkeypatch.setenv("AVENIR_MCP_AUTO_CONFIRM", "true")
    assert _ask(_Ctx("2025-11-25", answer=AcceptedElicitation(data=False))) == "declined"


@pytest.mark.usefixtures("auto")
def test_auto_confirm_logs_one_item_for_a_single_change(caplog: pytest.LogCaptureFixture) -> None:
    """A subject that is not a list counts as one item."""
    with caplog.at_level("WARNING", logger="avenir_mcp.confirm"):
        assert _ask(_NeverAsk("2025-11-25"), {"category": "c1"}) == "applied"
    assert "1 item(s)" in caplog.text
    assert "c1" not in caplog.text


@pytest.mark.parametrize(
    ("subject", "size"),
    [
        # apply_categories: its changes, then the approve flag, which is not a change.
        (["change-1", "change-2", {"approve": False}], 2),
        # reconcile_account: the transactions it reconciles, and the adjustment if any.
        ({"account": "a1", "balance": 10.0, "adjust": 0, "transactions": ["t1", "t2"]}, 2),
        ({"account": "a1", "balance": 10.0, "adjust": -1.5, "transactions": ["t1", "t2"]}, 3),
        ({"account": "a1", "balance": 10.0, "adjust": -1.5, "transactions": []}, 1),
        # create_transactions, set_category_budgets, flag_transactions.
        ({"account": "a1", "items": ["x", "y", "z"], "approved": True}, 3),
        ({"month": "2026-09-01", "budgets": [("c1", 1000), ("c2", 2000)]}, 2),
        ({"flags": [("t1", "red")]}, 1),
        # set_category_target: one target, whatever its fields.
        ({"category": "c1", "fields": {"goal_target": 1000, "goal_target_date": None}}, 1),
    ],
)
@pytest.mark.usefixtures("auto")
def test_auto_confirm_logs_how_many_things_the_write_changes(
    subject: object, size: int, caplog: pytest.LogCaptureFixture
) -> None:
    """The count is of what is changed, the items inside a subject's list included."""
    with caplog.at_level("WARNING", logger="avenir_mcp.confirm"):
        assert _ask(_NeverAsk("2025-11-25"), subject) == "applied"
    assert [r.getMessage() for r in caplog.records] == [
        f"Auto-confirmed a write of {size} item(s) (AVENIR_MCP_AUTO_CONFIRM=1)"
    ]


@pytest.mark.usefixtures("auto", "required")
def test_auto_confirm_never_overrides_required_elicitation() -> None:
    """Both set (server.main refuses this): ask() still asks the user in the client."""
    assert _ask(_Ctx("2025-11-25", answer=AcceptedElicitation(data=False))) == "declined"
