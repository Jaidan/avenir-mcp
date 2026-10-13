# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Tests for writes.py — planning a change and confirming it before it happens."""

from __future__ import annotations

import string
from typing import Any

import pytest

from avenir_mcp import writes
from avenir_mcp.journal import Move

_CATEGORIES: list[dict[str, Any]] = [
    {"id": "c-food", "name": "Groceries"},
    {"id": "c-fun", "name": "Leisure"},
    {"id": "c-visa", "name": "Visa", "category_group_name": "Credit Card Payments"},
]


def _tx(tx_id: str, category_id: str | None = None, **extra: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "id": tx_id,
        "date": "2026-09-01",
        "amount": -12340,
        "payee_name": "Corner Shop",
        "category_id": category_id,
        "transfer_account_id": None,
    }
    tx.update(extra)
    return tx


# ---------------------------------------------------------------------------
# plan_categorization
# ---------------------------------------------------------------------------


def test_plan_lists_each_change_with_before_and_after() -> None:
    """The preview says what moves from where to where, amounts in currency units."""
    plan = writes.plan_categorization(
        [_tx("t1"), _tx("t2", "c-fun")],
        _CATEGORIES,
        [
            writes.Assignment(transaction_id="t1", category_id="c-food"),
            writes.Assignment(transaction_id="t2", category_id="c-food"),
        ],
    )
    assert [c.model_dump() for c in plan.changes] == [
        {
            "transaction_id": "t1",
            "date": "2026-09-01",
            "amount": -12.34,
            "payee": "Corner Shop",
            "from_category_id": None,
            "from_category": None,
            "to_category_id": "c-food",
            "to_category": "Groceries",
            "approved": False,
        },
        {
            "transaction_id": "t2",
            "date": "2026-09-01",
            "amount": -12.34,
            "payee": "Corner Shop",
            "from_category_id": "c-fun",
            "from_category": "Leisure",
            "to_category_id": "c-food",
            "to_category": "Groceries",
            "approved": False,
        },
    ]
    assert plan.unchanged_count == 0


def test_plan_carries_each_transactions_approval() -> None:
    """The change records whether the transaction is approved, so the write keeps it."""
    plan = writes.plan_categorization(
        [_tx("t1", approved=True), _tx("t2", approved=False)],
        _CATEGORIES,
        [
            writes.Assignment(transaction_id="t1", category_id="c-food"),
            writes.Assignment(transaction_id="t2", category_id="c-food"),
        ],
    )
    assert [c.approved for c in plan.changes] == [True, False]


def test_undo_carries_each_transactions_approval() -> None:
    """Undoing keeps the approval the transaction has now."""
    plan = writes.plan_undo(
        [_tx("t1", "c-food", approved=True)], _CATEGORIES, [_move("t1", "c-fun", "c-food")]
    )
    assert [c.approved for c in plan.changes] == [True]


def test_plan_skips_assignments_that_change_nothing() -> None:
    """Assigning a transaction to its current category is not a change."""
    plan = writes.plan_categorization(
        [_tx("t1", "c-food")],
        _CATEGORIES,
        [writes.Assignment(transaction_id="t1", category_id="c-food")],
    )
    assert not plan.changes
    assert plan.unchanged_count == 1


def test_plan_rejects_an_unknown_transaction() -> None:
    """An id that is not in the plan is refused, naming it."""
    with pytest.raises(ValueError) as refusal:
        writes.plan_categorization(
            [], _CATEGORIES, [writes.Assignment(transaction_id="t404", category_id="c-food")]
        )
    assert str(refusal.value) == (
        "Transaction t404 is not in this plan: "
        "use the transaction_id values returned by suggest_categories."
    )


def test_plan_rejects_an_unknown_category() -> None:
    """A category id that is not in the plan is refused, naming it."""
    with pytest.raises(ValueError) as refusal:
        writes.plan_categorization(
            [_tx("t1")], _CATEGORIES, [writes.Assignment(transaction_id="t1", category_id="c-404")]
        )
    assert str(refusal.value) == (
        "Category c-404 is not in this plan: "
        "use a category_id from the categories returned by suggest_categories."
    )


def test_plan_rejects_a_transfer() -> None:
    """Transfers between accounts take no category in YNAB."""
    with pytest.raises(ValueError, match="transfer"):
        writes.plan_categorization(
            [_tx("t1", transfer_account_id="acc-2")],
            _CATEGORIES,
            [writes.Assignment(transaction_id="t1", category_id="c-food")],
        )


def test_plan_rejects_a_credit_card_payment_category() -> None:
    """YNAB ignores it on a transaction: refused, rather than reported applied."""
    with pytest.raises(ValueError, match="c-visa pays a credit card"):
        writes.plan_categorization(
            [_tx("t1")],
            _CATEGORIES,
            [writes.Assignment(transaction_id="t1", category_id="c-visa")],
        )


def test_plan_rejects_the_same_transaction_twice() -> None:
    """Two assignments for one transaction are ambiguous."""
    with pytest.raises(ValueError, match="t1.*twice"):
        writes.plan_categorization(
            [_tx("t1")],
            _CATEGORIES,
            [
                writes.Assignment(transaction_id="t1", category_id="c-food"),
                writes.Assignment(transaction_id="t1", category_id="c-fun"),
            ],
        )


# ---------------------------------------------------------------------------
# Confirmations — single-use codes bound to one exact plan
# ---------------------------------------------------------------------------


def _changes(to: str = "c-food") -> list[writes.Change]:
    return writes.plan_categorization(
        [_tx("t1")], _CATEGORIES, [writes.Assignment(transaction_id="t1", category_id=to)]
    ).changes


def test_confirmation_code_accepts_the_plan_it_was_issued_for_once() -> None:
    """A code confirms its own plan, and only once."""
    confirmations = writes.Confirmations()
    code = confirmations.issue("b1", _changes())
    assert confirmations.consume(code, "b1", _changes()) is True
    assert confirmations.consume(code, "b1", _changes()) is False


def test_confirmation_code_refuses_a_different_plan() -> None:
    """A code issued for one change cannot confirm another."""
    confirmations = writes.Confirmations()
    code = confirmations.issue("b1", _changes("c-food"))
    assert confirmations.consume(code, "b1", _changes("c-fun")) is False
    assert confirmations.consume(code, "b2", _changes("c-food")) is False


def test_confirmation_code_expires() -> None:
    """A code older than its lifetime is refused."""
    now = [1000.0]
    confirmations = writes.Confirmations(ttl_seconds=600, clock=lambda: now[0])
    code = confirmations.issue("b1", _changes())
    now[0] += 601
    assert confirmations.consume(code, "b1", _changes()) is False


def test_unknown_confirmation_code_is_refused() -> None:
    """A code the server never issued confirms nothing."""
    assert writes.Confirmations().consume("made-up", "b1", _changes()) is False


def test_confirmation_code_can_bind_any_json_subject() -> None:
    """A code can confirm a change other than a list of transactions."""
    confirmations = writes.Confirmations()
    rename = {"category_id": "c1", "name": "Pharmacy"}
    code = confirmations.issue("b1", rename)
    assert confirmations.consume(code, "b1", {"category_id": "c1", "name": "Other"}) is False
    code = confirmations.issue("b1", rename)
    assert confirmations.consume(code, "b1", dict(rename)) is True


def test_plan_rejects_a_split_transaction() -> None:
    """Assigning one category to a split would erase its lines."""
    with pytest.raises(ValueError, match="split"):
        writes.plan_categorization(
            [_tx("t1", subtransactions=[{"category_id": "c-food"}])],
            _CATEGORIES,
            [writes.Assignment(transaction_id="t1", category_id="c-fun")],
        )


def test_expired_codes_are_forgotten() -> None:
    """Previews never confirmed do not pile up in memory: expired codes are dropped."""
    now = [0.0]
    codes = writes.Confirmations(ttl_seconds=600, clock=lambda: now[0])
    for i in range(3):
        codes.issue("b1", i)
    now[0] = 601.0
    fresh = codes.issue("b1", "fresh")
    assert list(codes._issued) == [fresh]  # pylint: disable=protected-access


def test_plan_rejects_a_transaction_of_an_off_budget_account() -> None:
    """A tracking account's transaction takes no category."""
    with pytest.raises(ValueError, match="off-budget"):
        writes.plan_categorization(
            [_tx("t1", account_id="acc-loan")],
            _CATEGORIES,
            [writes.Assignment(transaction_id="t1", category_id="c-food")],
            off_budget={"acc-loan"},
        )


def test_plan_rejects_ynab_internal_uncategorized() -> None:
    """Assigning YNAB's internal Uncategorized category changes nothing useful."""
    internal = {
        "id": "c-uncat",
        "name": "Uncategorized",
        "category_group_name": "Internal Master Category",
    }
    with pytest.raises(ValueError, match="Uncategorized"):
        writes.plan_categorization(
            [_tx("t1")],
            [*_CATEGORIES, internal],
            [writes.Assignment(transaction_id="t1", category_id="c-uncat")],
        )


# ---------------------------------------------------------------------------
# Cases found by mutation testing
# ---------------------------------------------------------------------------


def test_every_assignment_is_planned_after_ones_that_change_nothing() -> None:
    """Assignments that change nothing are counted, and the ones after them still planned."""
    plan = writes.plan_categorization(
        [_tx("t1", "c-food"), _tx("t2", "c-food"), _tx("t3")],
        _CATEGORIES,
        [
            writes.Assignment(transaction_id="t1", category_id="c-food"),
            writes.Assignment(transaction_id="t2", category_id="c-food"),
            writes.Assignment(transaction_id="t3", category_id="c-fun"),
        ],
    )
    assert plan.unchanged_count == 2
    assert [c.transaction_id for c in plan.changes] == ["t3"]


def test_the_fingerprint_ignores_the_order_of_keys() -> None:
    """The same change written with its keys in another order is the same change."""
    assert writes.fingerprint("b1", {"a": 1, "b": 2}) == writes.fingerprint("b1", {"b": 2, "a": 1})
    assert writes.fingerprint("b1", [{"a": 1, "b": 2}]) == writes.fingerprint(
        "b1", [{"b": 2, "a": 1}]
    )


def test_codes_are_distinct_strings_and_a_fresh_one_survives_the_next_issue() -> None:
    """Issuing a code drops only expired ones; each code is a new non-empty string."""
    now = [100.0]
    confirmations = writes.Confirmations(ttl_seconds=600, clock=lambda: now[0])
    first = confirmations.issue("b1", {"x": 1})
    now[0] = 700.0
    second = confirmations.issue("b1", {"x": 2})
    assert isinstance(first, str) and first and first != second
    assert confirmations.consume(first, "b1", {"x": 1}) is True


def test_a_code_carries_eight_bytes_of_randomness() -> None:
    """A code the agent cannot guess: 8 random bytes, written URL-safe on 11 characters."""
    code = writes.Confirmations().issue("b1", {"x": 1})
    assert len(code) == 11
    assert set(code) <= set(string.ascii_letters + string.digits + "-_")


def test_a_code_is_still_valid_at_the_exact_end_of_its_lifetime() -> None:
    """Ten minutes means up to and including the tenth minute."""
    now = [0.0]
    confirmations = writes.Confirmations(ttl_seconds=600, clock=lambda: now[0])
    code = confirmations.issue("b1", {"x": 1})
    now[0] = 600.0
    assert confirmations.consume(code, "b1", {"x": 1}) is True


# ---------------------------------------------------------------------------
# plan_undo
# ---------------------------------------------------------------------------


def _move(tx_id: str, before: str | None, after: str | None) -> Move:
    return Move(transaction_id=tx_id, from_category_id=before, to_category_id=after)


def test_undo_lists_each_change_the_other_way_round() -> None:
    """Undoing swaps from and to: the category the operation gave becomes the one left."""
    plan = writes.plan_undo([_tx("t1", "c-food")], _CATEGORIES, [_move("t1", "c-fun", "c-food")])
    assert [c.model_dump() for c in plan.changes] == [
        {
            "transaction_id": "t1",
            "date": "2026-09-01",
            "amount": -12.34,
            "payee": "Corner Shop",
            "from_category_id": "c-food",
            "from_category": "Groceries",
            "to_category_id": "c-fun",
            "to_category": "Leisure",
            "approved": False,
        }
    ]
    assert not plan.conflicts


def test_undo_back_to_no_category_names_none() -> None:
    """A transaction that had no category goes back to none, not to an empty name."""
    changes = writes.plan_undo(
        [_tx("t1", "c-food")], _CATEGORIES, [_move("t1", None, "c-food")]
    ).changes
    assert len(changes) == 1
    assert (changes[0].to_category_id, changes[0].to_category) == (None, None)


def test_undo_of_a_move_to_no_category_names_what_it_came_from() -> None:
    """An operation that cleared a category: undoing it says so on both sides."""
    changes = writes.plan_undo([_tx("t1", None)], _CATEGORIES, [_move("t1", "c-fun", None)]).changes
    assert len(changes) == 1
    assert (changes[0].from_category_id, changes[0].from_category) == (None, None)
    assert (changes[0].to_category_id, changes[0].to_category) == ("c-fun", "Leisure")


def test_undo_leaves_alone_what_changed_since_and_goes_on() -> None:
    """A conflict is listed, never overwritten, and does not stop the moves after it."""
    plan = writes.plan_undo(
        [_tx("gone-since", "c-fun"), _tx("t2", "c-food")],
        _CATEGORIES,
        [
            _move("t404", "c-fun", "c-food"),
            _move("gone-since", "c-fun", "c-food"),
            _move("t2", "c-fun", "c-food"),
        ],
    )
    assert [c.transaction_id for c in plan.changes] == ["t2"]
    assert plan.conflicts == ["t404", "gone-since"]


def test_undo_shows_bank_text_safely() -> None:
    """The payee goes into a confirmation question: on one line, visible characters only."""
    forged = _tx("t1", "c-food", payee_name="Shop\nRENT 0.00")
    changes = writes.plan_undo([forged], _CATEGORIES, [_move("t1", None, "c-food")]).changes
    assert len(changes) == 1
    assert changes[0].payee == "Shop RENT 0.00"


def test_approvals_reads_each_transactions_approval() -> None:
    """A transaction without an approval counts as unapproved."""
    txs = [_tx("t1", approved=True), _tx("t2", approved=False), _tx("t3")]
    assert writes.approvals(txs) == {"t1": True, "t2": False, "t3": False}
