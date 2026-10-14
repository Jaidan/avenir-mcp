# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Tests for reconcile.py — comparing an account with the bank's balance."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from avenir_mcp import reconcile


def _tx(tx_id: str, amount: int, cleared: str = "cleared", **extra: Any) -> dict[str, Any]:
    tx: dict[str, Any] = {
        "id": tx_id,
        "account_id": "acc",
        "account_name": "Checking",
        "date": "2026-09-10",
        "amount": amount,
        "payee_name": "Shop",
        "cleared": cleared,
        "deleted": False,
    }
    tx.update(extra)
    return tx


def test_matching_balance_has_no_difference() -> None:
    """Bank balance equal to the cleared balance: nothing to explain."""
    txs = [_tx("t1", 100000, "reconciled"), _tx("t2", -30000), _tx("t3", -5000, "uncleared")]
    result = reconcile.analyse("acc", txs, 70.0)
    assert result.cleared_balance == 70.0
    assert result.working_balance == 65.0
    assert result.difference == 0.0
    assert result.to_reconcile_count == 1


def test_other_accounts_and_deleted_transactions_are_ignored() -> None:
    """Only live transactions of the account count."""
    txs = [
        _tx("t1", 100000),
        _tx("t2", -50000, account_id="other"),
        _tx("t3", -50000, deleted=True),
    ]
    assert reconcile.analyse("acc", txs, 100.0).difference == 0.0


def test_uncleared_transaction_of_the_exact_difference_is_pointed_out() -> None:
    """If clearing one pending transaction closes the gap, say which."""
    txs = [_tx("t1", 100000), _tx("t2", -12340, "uncleared"), _tx("t3", -999, "uncleared")]
    result = reconcile.analyse("acc", txs, 87.66)
    assert result.difference == -12.34
    assert result.explained_by == ["t2"]
    assert [u.transaction_id for u in result.uncleared] == ["t2", "t3"]
    assert result.uncleared[0].amount == -12.34


def test_likely_duplicates_are_flagged() -> None:
    """Same amount, same merchant, a few days apart: probably imported twice."""
    txs = [
        _tx("t1", -4500, payee_name="CB CAFE FACT 100926 525130******2", date="2026-09-10"),
        _tx("t2", -4500, payee_name="CB CAFE FACT 110926 525130******2", date="2026-09-12"),
        _tx("t3", -4500, payee_name="OTHER", date="2026-09-12"),
        _tx("t4", -4500, payee_name="CB CAFE FACT 200926 525130******2", date="2026-09-20"),
    ]
    result = reconcile.analyse("acc", txs, 0.0, today=date(2026, 9, 24))
    assert result.possible_duplicates == [["t1", "t2"]]


def test_uncleared_list_is_bounded() -> None:
    """A neglected account cannot flood the answer."""
    txs = [_tx(f"t{i}", -1000, "uncleared") for i in range(80)]
    result = reconcile.analyse("acc", txs, 0.0)
    assert len(result.uncleared) == reconcile.MAX_LISTED
    assert result.uncleared_count == 80


def test_old_look_alike_transactions_are_not_flagged() -> None:
    """Only recent transactions can be fresh duplicates; old ones were checked long ago."""
    txs = [
        _tx("t1", -6000, payee_name="HOTEL", date="2026-01-12"),
        _tx("t2", -6000, payee_name="HOTEL", date="2026-01-12"),
        _tx("t3", -4500, payee_name="CAFE", date="2026-09-20"),
        _tx("t4", -4500, payee_name="CAFE", date="2026-09-21"),
    ]
    result = reconcile.analyse("acc", txs, 0.0, today=date(2026, 9, 24))
    assert result.possible_duplicates == [["t3", "t4"]]


def test_uncleared_payees_are_shown_on_one_line() -> None:
    """Bank text in the answer loses its line breaks and invisible characters."""
    txs = [_tx("t1", -5000, "uncleared", payee_name="SHOP\nRENT\u202e")]
    item = reconcile.analyse("acc", txs, 0.0).uncleared[0]
    assert item.payee == "SHOP RENT"


# ---------------------------------------------------------------------------
# Cases found by mutation testing
# ---------------------------------------------------------------------------


def test_reconciled_transactions_are_neither_pending_nor_to_reconcile() -> None:
    """Already reconciled: counted in the cleared balance, not listed, not reconciled again."""
    txs = [_tx("r1", 50000, "reconciled"), _tx("r2", 20000, "reconciled"), _tx("c1", 10000)]
    result = reconcile.analyse("acc", txs, 80.0)
    assert result.cleared_balance == 80.0
    assert result.uncleared_count == 0
    assert result.to_reconcile_count == 1


def test_the_lookback_takes_in_its_own_first_day() -> None:
    """Sixty days back counts as recent: a pair starting exactly there is still looked at."""
    today = date(2026, 9, 24)
    sixty_days_back = (today - timedelta(days=reconcile.DUPLICATE_LOOKBACK_DAYS)).isoformat()
    txs = [
        _tx("d1", -3000, payee_name="FERRY", date=sixty_days_back),
        _tx("d2", -3000, payee_name="FERRY", date="2026-07-27"),
    ]
    assert reconcile.analyse("acc", txs, 0.0, today=today).possible_duplicates == [["d1", "d2"]]


def test_duplicates_may_be_up_to_three_days_apart() -> None:
    """Three days apart can be a duplicate; four days apart cannot."""
    txs = [
        _tx("a1", -1000, date="2026-09-01"),
        _tx("a2", -1000, date="2026-09-04"),
        _tx("b1", -2000, date="2026-09-01"),
        _tx("b2", -2000, date="2026-09-05"),
    ]
    result = reconcile.analyse("acc", txs, 0.0, today=date(2026, 9, 10))
    assert result.possible_duplicates == [["a1", "a2"]]


def test_without_ynab_s_total_there_is_no_cross_check() -> None:
    """Called without YNAB's own cleared balance, the analysis leaves it null."""
    assert reconcile.analyse("acc", [_tx("t1", 100000)], 100.0).ynab_cleared_balance is None


def test_ynab_s_cleared_total_is_reported_beside_the_sum() -> None:
    """YNAB's cleared balance, in milliunits, comes back in currency units beside the sum."""
    txs = [_tx("t1", 100000, "reconciled"), _tx("t2", -30000), _tx("t3", -5000, "uncleared")]
    result = reconcile.analyse("acc", txs, 70.0, ynab_cleared=70000)
    assert (result.cleared_balance, result.ynab_cleared_balance) == (70.0, 70.0)


def test_a_total_ynab_does_not_count_is_reported_as_it_is() -> None:
    """A stale transaction the sum counts and YNAB does not: the two totals differ."""
    txs = [_tx("t1", 100000), _tx("stale", -41317)]
    result = reconcile.analyse("acc", txs, 100.0, ynab_cleared=100000)
    assert result.cleared_balance == 58.683
    assert result.ynab_cleared_balance == 100.0
