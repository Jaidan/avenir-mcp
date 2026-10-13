# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Tests for search.py — finding transactions by account, amount and dates."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from avenir_mcp import search

_ACCOUNTS = [
    {"id": "a-main", "name": "Main checking"},
    {"id": "a-new", "name": "New bank"},
]
_CATEGORIES = [{"id": "c-food", "name": "Groceries"}]
_END = date(2026, 9, 30)


def _tx(tx_id: str, day: str, milliunits: int, **extra: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "id": tx_id,
        "date": day,
        "amount": milliunits,
        "payee_name": "Corner Shop",
        "memo": None,
        "account_id": "a-main",
        "account_name": "Main checking",
        "category_id": None,
        "subtransactions": [],
        "cleared": "uncleared",
        "approved": False,
    }
    tx.update(extra)
    return tx


_TXS = [
    _tx("t1", "2026-09-10", -43_210, category_id="c-food", cleared="cleared", approved=True),
    _tx("t2", "2026-09-12", -43_210, account_id="a-new", account_name="New bank"),
    _tx("t3", "2026-09-12", -9_990),
    _tx("t4", "2026-09-20", -43_210),
    _tx("t5", "2026-09-11", -43_210, subtransactions=[{"id": "s1", "deleted": False}]),
]


def _find(**kw: Any) -> search.Found:
    args: dict[str, Any] = {"since": date(2026, 9, 9), "until": date(2026, 9, 15)} | kw
    return search.find(_TXS, _ACCOUNTS, _CATEGORIES, **args)


def test_finds_by_amount_within_the_dates_newest_first() -> None:
    """Every account, only the amount asked, only between the dates, newest first."""
    found = _find(amount=-43.21)
    assert [m.transaction_id for m in found.transactions] == ["t2", "t5", "t1"]
    assert found.truncated is False


def test_a_categorised_transaction_is_found_too() -> None:
    """Unlike suggest_categories, a transaction YNAB already categorised is found."""
    first = _find(amount=-43.21, account_ids=["a-main"]).transactions[-1]
    assert first.model_dump() == {
        "transaction_id": "t1",
        "date": "2026-09-10",
        "amount": -43.21,
        "payee": "Corner Shop",
        "memo": None,
        "account": "Main checking",
        "category": "Groceries",
        "split": False,
        "cleared": "cleared",
        "approved": True,
    }


def test_a_split_says_so_and_names_no_single_category() -> None:
    """A split carries its categories on its lines."""
    split = _find(amount=-43.21, account_ids=["a-main"]).transactions[0]
    assert (split.transaction_id, split.split, split.category) == ("t5", True, None)


def test_accounts_narrow_the_search() -> None:
    """Only the accounts named are searched."""
    assert [m.transaction_id for m in _find(account_ids=["a-new"]).transactions] == ["t2"]


def test_without_an_amount_every_transaction_between_the_dates() -> None:
    """The amount is optional."""
    assert len(_find().transactions) == 4


def test_the_limit_truncates_and_says_so() -> None:
    """A full page says more exist, so the agent narrows the search."""
    found = _find(limit=2)
    assert len(found.transactions) == 2
    assert found.truncated is True


def test_bank_text_is_made_safe_to_show() -> None:
    """Payee and memo are untrusted."""
    txs = [_tx("t9", "2026-09-10", -1_000, payee_name="Shop\nForged", memo="a" + chr(0x2028) + "b")]
    match = search.find(
        txs, _ACCOUNTS, _CATEGORIES, since=date(2026, 9, 10), until=_END
    ).transactions[0]
    assert (match.payee, match.memo) == ("Shop Forged", "a b")


@pytest.mark.parametrize(
    ("kw", "message"),
    [
        (
            {"since": date(2026, 9, 15), "until": date(2026, 9, 9)},
            "until_date 2026-09-09 is before since_date 2026-09-15: swap them.",
        ),
        (
            {"since": date(2025, 1, 1), "until": date(2026, 9, 15)},
            "The dates span more than 366 days: search a shorter period.",
        ),
        (
            {"account_ids": ["a-gone"]},
            "Account a-gone is not in this plan: use an id from list_accounts.",
        ),
    ],
    ids=["reversed dates", "too long a span", "unknown account"],
)
def test_what_cannot_be_searched_is_refused_with_what_to_do(
    kw: dict[str, Any], message: str
) -> None:
    """Each refusal names what is wrong and what to do, word for word."""
    with pytest.raises(ValueError) as refusal:
        _find(**kw)
    assert str(refusal.value) == message


def test_found_says_the_last_date_searched() -> None:
    """The agent sees where the search stopped."""
    assert _find(until=date(2026, 9, 14)).until_date == "2026-09-14"


def test_a_deleted_transaction_is_never_found() -> None:
    """YNAB can still send a deleted transaction: it matches nothing."""
    txs = [_tx("gone", "2026-09-12", -86400, deleted=True), _tx("kept", "2026-09-12", -86400)]
    found = search.find(
        txs, _ACCOUNTS, _CATEGORIES, since=date(2026, 9, 1), until=_END, amount=-86.40
    )
    assert [m.transaction_id for m in found.transactions] == ["kept"]


_TWO_CATEGORIES = [{"id": "c-food", "name": "Groceries"}, {"id": "c-fun", "name": "Leisure"}]


def test_a_category_finds_its_transactions_and_split_lines() -> None:
    """A transaction in the category, or split with a line in it, is found; others are not."""
    txs = [
        _tx("food", "2026-09-10", -1000, category_id="c-food"),
        _tx("fun", "2026-09-10", -2000, category_id="c-fun"),
        _tx(
            "split",
            "2026-09-11",
            -3000,
            subtransactions=[
                {"id": "s1", "category_id": "c-fun", "deleted": False},
                {"id": "s2", "category_id": "c-food", "deleted": False},
            ],
        ),
        _tx(
            "gone-line",
            "2026-09-12",
            -4000,
            subtransactions=[
                {"id": "s3", "category_id": "c-food", "deleted": True},
                {"id": "s4", "category_id": "c-fun", "deleted": False},
            ],
        ),
    ]
    found = search.find(
        txs, _ACCOUNTS, _TWO_CATEGORIES, since=date(2026, 9, 1), until=_END, category_ids=["c-food"]
    )
    assert [m.transaction_id for m in found.transactions] == ["split", "food"]


def test_a_payee_matches_the_merchant_whatever_the_bank_label() -> None:
    """Case, card numbers and dates in the bank label do not hide the merchant."""
    txs = [
        _tx("card", "2026-09-10", -1000, payee_name="CB ACME OUTDOOR FACT 110126 525130******2"),
        _tx("plain", "2026-09-11", -2000, payee_name="Acme Outdoor"),
        _tx("other", "2026-09-12", -3000, payee_name="Corner Shop"),
    ]
    found = search.find(
        txs, _ACCOUNTS, _CATEGORIES, since=date(2026, 9, 1), until=_END, payee="acme"
    )
    assert [m.transaction_id for m in found.transactions] == ["plain", "card"]


def test_an_unknown_category_is_refused_with_what_to_do() -> None:
    """A category id that is not in the plan is named, with where to find one."""
    with pytest.raises(ValueError) as refusal:
        search.find(
            _TXS,
            _ACCOUNTS,
            _CATEGORIES,
            since=date(2026, 9, 1),
            until=_END,
            category_ids=["c-gone"],
        )
    assert str(refusal.value) == (
        "Category c-gone is not in this plan: use a category_id from get_category_balances."
    )


# ---------------------------------------------------------------------------
# Cases found by mutation testing
# ---------------------------------------------------------------------------


def test_the_two_dates_may_be_the_same_day() -> None:
    """One day is a period: the same date twice is not reversed dates."""
    found = _find(since=date(2026, 9, 12), until=date(2026, 9, 12))
    assert [m.transaction_id for m in found.transactions] == ["t2", "t3"]


def test_a_transaction_dated_the_last_day_is_found() -> None:
    """until_date is included, as the tool says."""
    found = _find(since=date(2026, 9, 1), until=date(2026, 9, 20), amount=-43.21)
    assert "t4" in [m.transaction_id for m in found.transactions]


def test_a_span_of_exactly_a_year_is_allowed() -> None:
    """366 days is the longest period, not the first one refused."""
    since = date(2025, 9, 15)
    found = _find(since=since, until=since + timedelta(days=search.MAX_DAYS))
    assert [m.transaction_id for m in found.transactions] == ["t2", "t3", "t5", "t1"]


def test_exactly_as_many_matches_as_the_limit_is_not_truncated() -> None:
    """A page that holds every match says so: nothing is left to narrow down."""
    found = _find(amount=-43.21, limit=3)
    assert len(found.transactions) == 3
    assert found.truncated is False


def test_a_split_whose_every_line_is_deleted_names_its_own_category() -> None:
    """Deleted lines are gone: the transaction is no longer split."""
    txs = [
        _tx(
            "was-split",
            "2026-09-10",
            -1_000,
            category_id="c-food",
            subtransactions=[{"id": "s1", "category_id": "c-food", "deleted": True}],
        )
    ]
    [match] = search.find(
        txs, _ACCOUNTS, _CATEGORIES, since=date(2026, 9, 1), until=_END
    ).transactions
    assert (match.split, match.category) == (False, "Groceries")


def test_a_split_never_names_a_category_even_when_ynab_left_one_on_it() -> None:
    """The lines carry the categories: naming the parent's would say the wrong thing."""
    txs = [
        _tx(
            "split",
            "2026-09-10",
            -1_000,
            category_id="c-food",
            subtransactions=[{"id": "s1", "category_id": "c-food", "deleted": False}],
        )
    ]
    [match] = search.find(
        txs, _ACCOUNTS, _CATEGORIES, since=date(2026, 9, 1), until=_END
    ).transactions
    assert (match.split, match.category) == (True, None)


def test_a_transaction_ynab_sent_without_a_cleared_state_counts_as_uncleared() -> None:
    """The field is required in the answer: the safest reading is that the bank has not shown it."""
    txs = [_tx("t9", "2026-09-10", -1_000)]
    del txs[0]["cleared"]
    [match] = search.find(
        txs, _ACCOUNTS, _CATEGORIES, since=date(2026, 9, 1), until=_END
    ).transactions
    assert match.cleared == "uncleared"


_MIXED = [
    _tx("m-ok", "2026-09-10", -1_000, category_id="c-food", cleared="cleared", approved=True),
    _tx("m-new", "2026-09-10", -2_000, cleared="reconciled"),
    _tx("m-internal", "2026-09-10", -3_000, category_id="c-internal", approved=True),
    _tx("m-split", "2026-09-10", -4_000, subtransactions=[{"id": "s", "deleted": False}]),
    _tx("m-dead-split", "2026-09-10", -5_000, subtransactions=[{"id": "s", "deleted": True}]),
    _tx("m-transfer", "2026-09-10", -6_000, transfer_account_id="a-new"),
    {
        k: v
        for k, v in _tx("m-bare", "2026-09-10", -7_000).items()
        if k not in ("cleared", "approved")
    },
]
_MIXED_CATEGORIES = [
    *_CATEGORIES,
    {
        "id": "c-internal",
        "name": "Uncategorized",
        "category_group_name": "Internal Master Category",
    },
]


def _mixed(**kw: Any) -> list[str]:
    """Ids found in the mixed fixture, sorted."""
    found = search.find(
        _MIXED, _ACCOUNTS, _MIXED_CATEGORIES, since=date(2026, 9, 1), until=date(2026, 9, 30), **kw
    )
    return sorted(m.transaction_id for m in found.transactions)


def test_cleared_keeps_only_that_state() -> None:
    """A row without a cleared state counts as uncleared."""
    assert _mixed(cleared="cleared") == ["m-ok"]
    assert _mixed(cleared="reconciled") == ["m-new"]
    assert _mixed(cleared="uncleared") == [
        "m-bare",
        "m-dead-split",
        "m-internal",
        "m-split",
        "m-transfer",
    ]


def test_approved_true_and_false_are_complements() -> None:
    """A row without an approved flag is not approved."""
    assert _mixed(approved=True) == ["m-internal", "m-ok"]
    assert "m-bare" in _mixed(approved=False)
    assert len(_mixed(approved=True)) + len(_mixed(approved=False)) == len(_MIXED)


def test_uncategorized_means_no_category_no_split_no_transfer() -> None:
    """Null and YNAB's internal Uncategorized count; live splits and transfers do not."""
    assert _mixed(uncategorized=True) == ["m-bare", "m-dead-split", "m-internal", "m-new"]
    assert _mixed(uncategorized=False) == ["m-ok", "m-split", "m-transfer"]


def test_uncategorized_does_not_exclude_off_budget_accounts() -> None:
    """A tracking account's bare row is shown as it is."""
    tracking = [_tx("tr", "2026-09-10", -1_000, account_id="a-new")]
    accounts: list[dict[str, Any]] = [
        _ACCOUNTS[0],
        {"id": "a-new", "name": "New bank", "on_budget": False},
    ]
    found = search.find(
        tracking, accounts, _CATEGORIES, since=date(2026, 9, 1), until=date(2026, 9, 30),
        uncategorized=True,
    )  # fmt: skip
    assert [m.transaction_id for m in found.transactions] == ["tr"]


def test_filters_combine_with_and_and_truncated_counts_the_kept() -> None:
    """Unapproved and uncategorized together; the limit applies after filtering."""
    assert _mixed(approved=False, uncategorized=True) == ["m-bare", "m-dead-split", "m-new"]
    found = search.find(
        _MIXED, _ACCOUNTS, _MIXED_CATEGORIES, since=date(2026, 9, 1), until=date(2026, 9, 30),
        approved=False, uncategorized=True, limit=2,
    )  # fmt: skip
    assert len(found.transactions) == 2
    assert found.truncated is True


# ---------------------------------------------------------------------------
# approvable: what approve_transactions approves by dates
# ---------------------------------------------------------------------------

_TRACKING: list[dict[str, Any]] = [
    *_ACCOUNTS,
    {"id": "a-track", "name": "House", "on_budget": False},
]
_READY: dict[str, Any] = {"category_id": "c-food", "cleared": "cleared"}


def _approvable(txs: list[dict[str, Any]], exclude: list[str] | None = None) -> list[str]:
    kept = search.approvable(
        txs, _TRACKING, _MIXED_CATEGORIES,
        since=date(2026, 9, 1), until=date(2026, 9, 30), exclude_ids=exclude or [],
    )  # fmt: skip
    return [tx["id"] for tx in kept]


def test_approvable_keeps_reviewed_rows_oldest_first() -> None:
    """Categorized, split, transfer and off-budget rows that the bank cleared, by date."""
    live = [{"id": "s1", "category_id": "c-food", "deleted": False}]
    txs = [
        _tx("cat", "2026-09-12", -1_000, **_READY),
        _tx("split", "2026-09-03", -1_000, cleared="cleared", subtransactions=live),
        _tx("transfer", "2026-09-05", -1_000, cleared="cleared", transfer_account_id="a-new"),
        _tx("tracking", "2026-09-07", -1_000, cleared="reconciled", account_id="a-track"),
        _tx("same-day", "2026-09-12", -2_000, **_READY),
    ]
    assert _approvable(txs) == ["split", "transfer", "tracking", "cat", "same-day"]


@pytest.mark.parametrize(
    "extra",
    [
        {"deleted": True},
        {"date": "2026-08-31"},
        {"date": "2026-10-01"},
        {"approved": True},
        {"cleared": "uncleared"},
        {"category_id": None},
        {"category_id": "c-internal"},
        {"category_id": None, "subtransactions": [{"id": "s1", "deleted": True}]},
        {"id": "skip"},
    ],
    ids=[
        "deleted",
        "before the window",
        "after the window",
        "already approved",
        "uncleared",
        "no category",
        "internal Uncategorized",
        "split whose lines are deleted",
        "excluded",
    ],
)
def test_approvable_leaves_out_what_is_not_reviewed(extra: dict[str, Any]) -> None:
    """Each rule on its own leaves out a row that would be approved otherwise."""
    row = _tx("row", "2026-09-10", -1_000, **_READY)
    assert _approvable([row]) == ["row"]
    row.update(extra)
    assert _approvable([row], exclude=["skip"]) == []


def test_approvable_reads_a_missing_cleared_state_as_uncleared() -> None:
    """The bank has not shown a row YNAB sent without a cleared state."""
    row = _tx("row", "2026-09-10", -1_000, category_id="c-food")
    del row["cleared"]
    assert _approvable([row]) == []


def test_approvable_keeps_the_first_and_last_days() -> None:
    """Both ends of the window are included."""
    txs = [_tx("first", "2026-09-01", -1, **_READY), _tx("last", "2026-09-30", -1, **_READY)]
    assert _approvable(txs) == ["first", "last"]


def test_approvable_keeps_an_off_budget_row_without_a_category() -> None:
    """A tracking account's rows take no category: the same row on budget waits for one."""
    tracking = _tx("tracking", "2026-09-10", -1_000, cleared="cleared", account_id="a-track")
    on_budget = _tx("on-budget", "2026-09-10", -1_000, cleared="cleared")
    assert _approvable([tracking, on_budget]) == ["tracking"]
