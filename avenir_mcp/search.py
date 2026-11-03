# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Find transactions by account, amount and dates, whatever their category.

Nothing here talks to YNAB. suggest_categories only shows what waits for a
category; matching a receipt, or checking a payment, needs the transactions
YNAB already categorised too.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from avenir_mcp.classifier import normalize_payee
from avenir_mcp.client import amount_to_milliunit
from avenir_mcp.model import Model
from avenir_mcp.triage import Line, internal_uncategorized, is_uncategorized, line_fields

MAX_DAYS = 366
DEFAULT_LIMIT = 50


class Match(Line):
    """A transaction found, as an agent needs it."""

    category: str | None
    """Category name; null when it has none or is split."""
    split: bool
    """True when the transaction is split: its lines carry the categories."""
    cleared: str
    """cleared, uncleared or reconciled."""
    approved: bool
    """False while it waits for review in YNAB."""


class Found(Model):
    """The transactions found."""

    transactions: list[Match]
    """Newest first."""
    truncated: bool
    """True when more transactions match than the limit: narrow the search."""
    until_date: str
    """Last date searched, YYYY-MM-DD: without until_date, today or a year after
    since_date, whichever comes first."""


def check(
    since: date,
    until: date,
    account_ids: list[str] | None,
    names: dict[str, str],
    categories: tuple[list[str] | None, dict[str, str]] = (None, {}),
) -> None:
    """Refuse a search that cannot be meant, or would read too much.

    Args:
        since: First date.
        until: Last date.
        account_ids: Accounts to search, or None for all.
        names: The plan's account names by id.
        categories: The categories to search, or None for all, and the plan's
            category names by id.

    Raises:
        ValueError: If the dates are reversed, span more than MAX_DAYS, or an
            account or a category is not in the plan.
    """
    if until < since:
        raise ValueError(f"until_date {until} is before since_date {since}: swap them.")
    if (until - since).days > MAX_DAYS:
        raise ValueError(f"The dates span more than {MAX_DAYS} days: search a shorter period.")
    unknown = [a for a in account_ids or [] if a not in names]
    if unknown:
        raise ValueError(f"Account {unknown[0]} is not in this plan: use an id from list_accounts.")
    category_ids, labels = categories
    unknown = [c for c in category_ids or [] if c not in labels]
    if unknown:
        raise ValueError(
            f"Category {unknown[0]} is not in this plan: "
            "use a category_id from get_category_balances."
        )


def _categorisation(tx: dict[str, Any], labels: dict[str, str]) -> dict[str, Any]:
    """Say how a transaction is categorised and where it stands.

    Args:
        tx: A YNAB transaction.
        labels: The plan's category names by id.

    Returns:
        category, split, cleared and approved.
    """
    split = any(not sub.get("deleted") for sub in tx.get("subtransactions") or [])
    category = tx.get("category_id")
    return {
        "category": None if split or not category else labels.get(category),
        "split": split,
        "cleared": tx.get("cleared", "uncleared"),
        "approved": bool(tx.get("approved")),
    }


def as_match(tx: dict[str, Any], labels: dict[str, str]) -> Match:
    """Turn a YNAB transaction into what an agent reads of it.

    Args:
        tx: A YNAB transaction.
        labels: The plan's category names by id.

    Returns:
        The transaction, bank text made safe to show.
    """
    return Match(**line_fields(tx), **_categorisation(tx, labels))


def _in_categories(tx: dict[str, Any], category_ids: set[str]) -> bool:
    """Tell whether a transaction, or one of its live split lines, is in the categories.

    Args:
        tx: A YNAB transaction.
        category_ids: The categories searched.

    Returns:
        True when the transaction's category, or a line's, is one of them.
    """
    lines = [sub for sub in tx.get("subtransactions") or [] if not sub.get("deleted")]
    return tx.get("category_id") in category_ids or any(
        sub.get("category_id") in category_ids for sub in lines
    )


def _names_payee(tx: dict[str, Any], payee: str) -> bool:
    """Tell whether a transaction's payee names the merchant searched.

    Both sides are reduced to the merchant (case, card numbers, dates and references
    left out), so "acme" finds "CB ACME OUTDOOR FACT 110126 525130******2".

    Args:
        tx: A YNAB transaction.
        payee: The merchant searched, or part of its name.

    Returns:
        True when the merchant searched is part of the transaction's payee.
    """
    # The empty default only marks "no payee". Another default would change the answer
    # only for a search term that is part of that very string, which says nothing about
    # what find_transactions should find. On its own line, so the pragma covers no more
    # than this one lookup.
    label = tx.get("payee_name") or ""  # pragma: no mutate
    return normalize_payee(payee) in normalize_payee(label)


def find(  # pylint: disable=too-many-arguments,too-many-locals
    transactions: list[dict[str, Any]],
    accounts: list[dict[str, Any]],
    categories: list[dict[str, Any]],
    *,
    since: date,
    until: date,
    amount: float | None = None,
    account_ids: list[str] | None = None,
    category_ids: list[str] | None = None,
    payee: str | None = None,
    cleared: Literal["cleared", "uncleared", "reconciled"] | None = None,
    approved: bool | None = None,
    uncategorized: bool | None = None,
    limit: int = DEFAULT_LIMIT,
) -> Found:
    """Find the transactions matching the filters, newest first.

    Args:
        transactions: The plan's transactions; deleted ones are never found.
        accounts: The plan's accounts.
        categories: The plan's categories.
        since: First date, included.
        until: Last date, included.
        amount: Exact amount in currency units, or None for any.
        account_ids: Accounts to search, or None for all.
        category_ids: Categories to search, a split line in one counting, or None for all.
        payee: Merchant to search, or part of its name, or None for any.
        cleared: Only this cleared state (a missing state counts as uncleared), or None.
        approved: True for approved only, False for waiting for review only, or None.
        uncategorized: True for what triage.is_uncategorized accepts only, False for the
            others, or None.
        limit: Maximum number of transactions returned.

    Returns:
        The matches, and whether more exist than the limit.

    Raises:
        ValueError: With a message saying what to fix, if the dates are reversed or
            span more than a year, or an account or a category is not in the plan.
    """
    labels = {c["id"]: c["name"] for c in categories}
    check(since, until, account_ids, {a["id"]: a["name"] for a in accounts}, (category_ids, labels))
    wanted = amount_to_milliunit(amount) if amount is not None else None
    internal = internal_uncategorized(categories)
    first, last = since.isoformat(), until.isoformat()
    kept = [
        tx
        for tx in transactions
        if not tx.get("deleted")
        and tx["date"] >= first
        and tx["date"] <= last
        and (wanted is None or tx["amount"] == wanted)
        and (account_ids is None or tx["account_id"] in account_ids)
        and (category_ids is None or _in_categories(tx, set(category_ids)))
        and (not payee or _names_payee(tx, payee))
        and (cleared is None or tx.get("cleared", "uncleared") == cleared)
        and (approved is None or bool(tx.get("approved")) == approved)
        and (uncategorized is None or is_uncategorized(tx, internal) == uncategorized)
    ]
    kept.sort(key=lambda tx: tx["date"], reverse=True)
    return Found(
        transactions=[as_match(tx, labels) for tx in kept[:limit]],
        truncated=len(kept) > limit,
        until_date=last,
    )


def approvable(  # pylint: disable=too-many-arguments
    transactions: list[dict[str, Any]],
    accounts: list[dict[str, Any]],
    categories: list[dict[str, Any]],
    *,
    since: date,
    until: date,
    exclude_ids: list[str],
) -> list[dict[str, Any]]:
    """Pick the transactions a period's review approves, oldest first.

    A transaction is kept when it is not deleted, dated within the window, not yet
    approved, seen by the bank (cleared or reconciled; a missing state counts as
    uncleared), not excluded, and has its category: one of its own, split lines or
    a transfer (triage.is_uncategorized says no), or none needed on an off-budget
    account.

    Args:
        transactions: The plan's transactions, as YNAB sends them.
        accounts: The plan's accounts.
        categories: The plan's categories.
        since: First date, included.
        until: Last date, included.
        exclude_ids: Transactions the user keeps for later.

    Returns:
        The transactions to approve, as YNAB sent them, by date then id.
    """
    off_budget = {a["id"] for a in accounts if a.get("on_budget") is False}
    internal = internal_uncategorized(categories)
    first, last, excluded = since.isoformat(), until.isoformat(), set(exclude_ids)
    kept = [
        tx
        for tx in transactions
        if not tx.get("deleted")
        and first <= tx["date"] <= last
        and not tx.get("approved")
        and tx.get("cleared", "uncleared") != "uncleared"
        and tx["id"] not in excluded
        and (tx.get("account_id") in off_budget or not is_uncategorized(tx, internal))
    ]
    return sorted(kept, key=lambda tx: (tx["date"], tx["id"]))
