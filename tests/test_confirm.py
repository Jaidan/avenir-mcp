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
    return asyncio.run(confirm.ask(ctx, "b1", subject, "Apply?", None))  # type: ignore[arg-type]


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
    ctx = _Ctx("2025-11-25")
    with pytest.raises(ToolError, match="AVENIR_MCP_REQUIRE_ELICITATION"):
        asyncio.run(confirm.ask(ctx, "b1", "change", "Apply?", code))  # type: ignore[arg-type]


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
    run = confirm.write_plan(ctx, "b1", plan, action, None)  # type: ignore[arg-type]
    return asyncio.run(run)[0]


@pytest.fixture(name="ynab")
def _ynab(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> list[Any]:
    """A fake YNAB recording the writes; the journal in a temporary file."""
    monkeypatch.setenv("AVENIR_MCP_JOURNAL", str(tmp_path / "journal.jsonl"))
    calls: list[Any] = []

    async def categorise(_plan: str, moves: Any, approved: Any) -> list[str]:
        calls.append(("categorise", moves, approved))
        return []

    async def approve(_plan: str, tx_ids: list[str]) -> dict[str, int]:
        calls.append(("approve", tx_ids))
        return {"approved": len(tx_ids)}

    monkeypatch.setattr("avenir_mcp.client.set_transaction_categories", categorise)
    monkeypatch.setattr("avenir_mcp.client.approve_transactions", approve)
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
    assert ynab == [("categorise", [("t1", "c-food")], {"t1": True}), ("approve", ["t2"])]


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
