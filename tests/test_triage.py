# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Tests for triage.py — one pass over the budget to prepare classification."""

from __future__ import annotations

import base64
from typing import Any

import pytest

from avenir_mcp import text, triage

_CATEGORIES: list[dict[str, Any]] = [
    {"id": "c-food", "name": "Groceries", "category_group_name": "Everyday", "deleted": False},
    {"id": "c-fun", "name": "Leisure", "category_group_name": "Everyday", "deleted": False},
    {"id": "c-old", "name": "Old", "category_group_name": "Everyday", "deleted": True},
]


def _tx(tx_id: str, payee: str, category_id: str | None = None, **extra: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "id": tx_id,
        "date": "2026-09-01",
        "amount": -12340,
        "payee_name": payee,
        "memo": None,
        "account_name": "Checking",
        "category_id": category_id,
        "transfer_account_id": None,
        "deleted": False,
    }
    tx.update(extra)
    return tx


def _history() -> list[dict[str, Any]]:
    return [
        _tx(f"h{i}", f"CB CORNER SHOP FACT 0101{i:02d} 525130******2", "c-food") for i in range(3)
    ]


def test_pending_transactions_are_listed_with_currency_amounts() -> None:
    """Pending items carry what an agent needs, amounts in currency units."""
    result = triage.prepare(_history() + [_tx("p1", "Unknown Cafe", memo="lunch")], _CATEGORIES)
    assert result.pending_count == 1
    assert [i.model_dump() for i in result.items] == [
        {
            "transaction_id": "p1",
            "date": "2026-09-01",
            "amount": -12.34,
            "payee": "Unknown Cafe",
            "memo": "lunch",
            "account": "Checking",
            "suggestion": None,
            "possible_transfer_with": None,
        }
    ]


def test_known_merchant_gets_a_suggestion() -> None:
    """A merchant seen before under another dated label is suggested from history."""
    pending = _tx("p1", "CB CORNER SHOP FACT 300926 525130******2")
    item = triage.prepare(_history() + [pending], _CATEGORIES).items[0]
    assert item.suggestion == triage.Suggestion(
        category_id="c-food", category_name="Groceries", confidence=1.0
    )
    assert triage.prepare(_history() + [pending], _CATEGORIES).suggested_count == 1


def test_ambiguous_merchant_gets_no_suggestion() -> None:
    """Below the confidence threshold the agent decides, not the history."""
    history = [_tx("h1", "SHOP", "c-food"), _tx("h2", "SHOP", "c-fun")]
    item = triage.prepare(history + [_tx("p1", "SHOP")], _CATEGORIES, threshold=0.9).items[0]
    assert item.suggestion is None


def test_transfers_and_deleted_transactions_are_not_pending() -> None:
    """Transfers between accounts need no category; deleted ones do not exist."""
    txs = [
        _tx("t1", "Transfer : Savings", transfer_account_id="acc-2"),
        _tx("t2", "Gone", deleted=True),
    ]
    assert triage.prepare(txs, _CATEGORIES).pending_count == 0


def test_categories_are_listed_once_without_deleted_ones() -> None:
    """The agent gets the category list once, to decide the unsuggested items."""
    result = triage.prepare([_tx("p1", "Unknown Cafe")], _CATEGORIES)
    assert [c.model_dump() for c in result.categories] == [
        {"category_id": "c-food", "name": "Groceries", "group": "Everyday"},
        {"category_id": "c-fun", "name": "Leisure", "group": "Everyday"},
    ]


def test_items_are_newest_first_and_paginated_with_a_cursor() -> None:
    """A page holds `limit` items; next_cursor fetches the rest, then is None."""
    txs = [_tx(f"p{i}", f"Shop {i}", date=f"2026-09-{i:02d}") for i in range(1, 6)]
    first = triage.prepare(txs, _CATEGORIES, limit=2)
    assert [i.transaction_id for i in first.items] == ["p5", "p4"]
    assert first.next_cursor is not None
    second = triage.prepare(txs, _CATEGORIES, limit=2, cursor=first.next_cursor)
    assert [i.transaction_id for i in second.items] == ["p3", "p2"]
    third = triage.prepare(txs, _CATEGORIES, limit=2, cursor=second.next_cursor)
    assert [i.transaction_id for i in third.items] == ["p1"]
    assert third.next_cursor is None


def test_long_bank_text_is_truncated() -> None:
    """Payee and memo are untrusted and bounded, so one label cannot flood the context."""
    item = triage.prepare([_tx("p1", "X" * 300, memo="Y" * 300)], _CATEGORIES).items[0]
    assert len(item.payee) == text.MAX_TEXT
    assert item.payee.endswith("…")
    assert len(item.memo or "") == text.MAX_TEXT


def test_well_encoded_foreign_cursor_is_rejected() -> None:
    """A valid base64 string that is not one of our cursors is refused too."""
    forged = base64.urlsafe_b64encode(b"page:3").decode()
    try:
        triage.prepare([], _CATEGORIES, cursor=forged)
    except ValueError as error:
        assert "next_cursor" in str(error)
    else:  # pragma: no cover
        raise AssertionError("a foreign cursor must raise")


def test_suggestions_follow_the_direction_of_the_money() -> None:
    """A payee that once paid you in does not make a payment to it look like income."""
    history = [
        _tx("h1", "LENDER", "c-fun", amount=500000),
        _tx("h2", "LENDER", "c-fun", amount=500000),
    ]
    repayment = _tx("p1", "LENDER", amount=-212000)
    assert triage.prepare(history + [repayment], _CATEGORIES).items[0].suggestion is None
    refund = _tx("p2", "LENDER", amount=1000)
    assert triage.prepare(history + [refund], _CATEGORIES).items[0].suggestion is not None


def test_split_transactions_are_not_pending() -> None:
    """A split has no category of its own: its lines carry them, so it is not waiting."""
    split = _tx(
        "p1", "SUPERMARKET", subtransactions=[{"category_id": "c-food"}, {"category_id": "c-fun"}]
    )
    assert triage.prepare([split], _CATEGORIES).pending_count == 0


def test_a_split_whose_lines_are_all_deleted_is_pending() -> None:
    """With no live line left, nothing carries a category: it waits for one."""
    emptied = _tx("p1", "SUPERMARKET", subtransactions=[{"category_id": "c-food", "deleted": True}])
    assert triage.prepare([emptied], _CATEGORIES).pending_count == 1


_INTERNAL = [
    {
        "id": "c-inflow",
        "name": "Inflow: Ready to Assign",
        "category_group_name": "Internal Master Category",
        "deleted": False,
    },
    {
        "id": "c-uncat",
        "name": "Uncategorized",
        "category_group_name": "Internal Master Category",
        "deleted": False,
    },
]


def test_transactions_of_off_budget_accounts_are_never_pending() -> None:
    """A tracking account (a mortgage, a loan) takes no category in YNAB."""
    txs = [
        _tx("p1", "SHOP", account_id="acc-main"),
        _tx("p2", "Starting Balance", account_id="acc-loan"),
    ]
    page = triage.prepare(txs, _CATEGORIES, off_budget={"acc-loan"})
    assert [i.transaction_id for i in page.items] == ["p1"]
    assert page.pending_count == 1


def test_uncategorized_is_not_offered_but_counts_as_pending() -> None:
    """YNAB's internal Uncategorized is no choice; a transaction carrying it still waits."""
    page = triage.prepare([_tx("p1", "SHOP", "c-uncat")], _CATEGORIES + _INTERNAL)
    assert [i.transaction_id for i in page.items] == ["p1"]
    offered = {c.category_id for c in page.categories}
    assert "c-uncat" not in offered
    assert "c-inflow" in offered


def test_opposite_amounts_between_accounts_are_a_possible_transfer() -> None:
    """Money leaving one account and arriving in another, unlinked, is flagged both ways."""
    txs = [
        _tx("out", "To vault", amount=-25000, date="2026-03-31", account_id="acc-a"),
        _tx("in", "To vault", amount=25000, date="2026-04-01", account_id="acc-b"),
        _tx("same-account", "Refund", amount=25000, date="2026-03-31", account_id="acc-a"),
        _tx("far", "Gift", amount=-25000, date="2026-01-01", account_id="acc-c"),
    ]
    items = {i.transaction_id: i for i in triage.prepare(txs, _CATEGORIES).items}
    assert items["out"].possible_transfer_with == "in"
    assert items["in"].possible_transfer_with == "out"
    assert items["same-account"].possible_transfer_with is None
    assert items["far"].possible_transfer_with is None


def test_categories_come_with_the_first_page_only() -> None:
    """A long category list is sent once, not on every page."""
    txs = [_tx(f"p{i}", "SHOP", date=f"2026-09-0{i + 1}") for i in range(3)]
    first = triage.prepare(txs, _CATEGORIES, limit=2)
    assert first.categories
    second = triage.prepare(txs, _CATEGORIES, limit=2, cursor=first.next_cursor)
    assert second.categories == []


# ---------------------------------------------------------------------------
# Cases found by mutation testing
# ---------------------------------------------------------------------------


def test_opposite_amounts_on_one_account_are_not_a_transfer() -> None:
    """A payment and its refund on the same account are two transactions, not a transfer."""
    txs = [
        _tx("pay", "Shop", amount=-25000, date="2026-03-30", account_id="acc-a"),
        _tx("refund", "Shop", amount=25000, date="2026-03-31", account_id="acc-a"),
    ]
    items = triage.prepare(txs, _CATEGORIES).items
    assert [i.possible_transfer_with for i in items] == [None, None]


def test_a_transfer_may_take_up_to_three_days() -> None:
    """Three days apart is still one transfer; four days apart is not."""
    txs = [
        _tx("out", "To vault", amount=-25000, date="2026-03-28", account_id="acc-a"),
        _tx("in", "To vault", amount=25000, date="2026-03-31", account_id="acc-b"),
        _tx("late-out", "To vault", amount=-9000, date="2026-03-20", account_id="acc-a"),
        _tx("late-in", "To vault", amount=9000, date="2026-03-24", account_id="acc-b"),
    ]
    items = {i.transaction_id: i for i in triage.prepare(txs, _CATEGORIES).items}
    assert items["out"].possible_transfer_with == "in"
    assert items["late-out"].possible_transfer_with is None


def test_deleted_transactions_and_transfers_teach_nothing() -> None:
    """History ignores deleted transactions and transfers, however many there are."""
    ghosts = [_tx(f"d{i}", "SHOP", "c-fun", deleted=True) for i in range(5)]
    ghosts += [_tx(f"t{i}", "SHOP", "c-fun", transfer_account_id="acc-2") for i in range(5)]
    history = [_tx("h1", "SHOP", "c-food")]
    item = triage.prepare(ghosts + history + [_tx("p1", "SHOP")], _CATEGORIES).items[0]
    assert item.suggestion is not None
    assert item.suggestion.category_id == "c-food"


def test_the_threshold_given_is_the_one_applied() -> None:
    """A lower threshold lets a two-in-three history suggest, rounded to two decimals."""
    history = [_tx("h1", "SHOP", "c-food"), _tx("h2", "SHOP", "c-food"), _tx("h3", "SHOP", "c-fun")]
    pending = [_tx("p1", "SHOP")]
    assert triage.prepare(history + pending, _CATEGORIES).items[0].suggestion is None
    item = triage.prepare(history + pending, _CATEGORIES, threshold=0.6).items[0]
    assert item.suggestion is not None
    assert item.suggestion.confidence == 0.67


def test_an_empty_memo_is_no_memo() -> None:
    """A blank memo is reported as null, not as an empty string."""
    assert triage.prepare([_tx("p1", "SHOP", memo="")], _CATEGORIES).items[0].memo is None


def test_a_full_last_page_has_no_next_cursor() -> None:
    """When the items fill the page exactly, there is nothing more to fetch."""
    txs = [_tx(f"p{i}", "SHOP", date=f"2026-09-0{i + 1}") for i in range(2)]
    assert triage.prepare(txs, _CATEGORIES, limit=2).next_cursor is None


def test_an_invalid_cursor_says_exactly_what_to_pass() -> None:
    """The message is what the agent reads to recover a page: checked word for word."""
    with pytest.raises(ValueError) as refusal:
        triage.prepare([], _CATEGORIES, cursor="banana")
    assert str(refusal.value) == (
        "Invalid cursor: pass the next_cursor value from the previous page unchanged, "
        "or omit it to start from the first page."
    )


def test_a_transaction_of_an_account_ynab_does_not_name_shows_an_empty_name() -> None:
    """A pending transaction is still listed when its account carries no name."""
    bare = _tx("p1", "SHOP")
    del bare["account_name"]
    [item] = triage.prepare([bare], _CATEGORIES).items
    assert item.account == ""


def test_a_category_in_no_group_is_offered_with_an_empty_group() -> None:
    """YNAB always groups a category, but a missing group must not hide it from the agent."""
    loose: list[dict[str, Any]] = [{"id": "c-loose", "name": "Loose", "deleted": False}]
    page = triage.prepare([_tx("p1", "SHOP")], loose)
    assert [(c.category_id, c.group) for c in page.categories] == [("c-loose", "")]


def test_a_transaction_of_nothing_is_not_money_out() -> None:
    """0.00 goes with the money coming in, when it is learnt and when it is read."""
    learnt = [_tx(f"h{i}", "ADJUSTMENT", "c-fun", amount=0) for i in range(3)]
    other_way = [_tx(f"o{i}", "ADJUSTMENT", "c-food", amount=-1_000) for i in range(3)]
    page = triage.prepare(learnt + other_way + [_tx("p1", "ADJUSTMENT", amount=0)], _CATEGORIES)
    [item] = page.items
    assert item.suggestion is not None
    assert item.suggestion.category_id == "c-fun"
