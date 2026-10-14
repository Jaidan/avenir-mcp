# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""The in-memory copy of each plan's transactions, kept current by YNAB's delta sync.

The first load of a plan holds every transaction and YNAB's `server_knowledge`, a
counter of changes. A later load sends that counter back and receives only what
changed since: merged here into the copy, a changed transaction replacing the old
one and a deleted one removed. No request is made here: client.py asks YNAB.
"""

from __future__ import annotations

from typing import Any

# {plan_id: {"server_knowledge": int, "transactions": {tx_id: tx}}}
_CACHE: dict[str, dict[str, Any]] = {}


def knowledge(plan_id: str) -> int | None:
    """Return the change counter of a plan's copy, to ask YNAB for what changed since.

    Args:
        plan_id: YNAB plan id.

    Returns:
        The `server_knowledge` of the last load, or None when the plan has no copy.
    """
    if plan_id not in _CACHE:
        return None
    return int(_CACHE[plan_id]["server_knowledge"])


def merge(
    plan_id: str, changes: list[dict[str, Any]], server_knowledge: int, *, fresh: bool = False
) -> list[dict[str, Any]]:
    """Merge what YNAB returned into a plan's copy, and return the whole copy.

    The copy is replaced in one step, once YNAB has answered: a load that fails
    leaves the previous copy whole, and a delta that lands during a full reload
    still merges into every transaction. A delta older than the copy (answered
    after a newer load) holds nothing the copy lacks: it is ignored, else it could
    bring back a transaction the newer load no longer had.

    Args:
        plan_id: YNAB plan id.
        changes: The transactions YNAB returned: every one on a first load, only
            those changed since on a delta. Those marked deleted leave the copy.
        server_knowledge: YNAB's change counter for this load.
        fresh: True for a full reload: `changes` becomes the whole copy, instead of
            being merged into the previous one.

    Returns:
        Every live transaction of the plan's copy.
    """
    copy = _CACHE.get(plan_id)
    if not fresh and copy is not None and server_knowledge < copy["server_knowledge"]:
        return list(copy["transactions"].values())
    known: dict[str, dict[str, Any]] = {} if fresh or copy is None else copy["transactions"]
    for tx in changes:
        if tx.get("deleted"):
            known.pop(tx["id"], None)
        else:
            known[tx["id"]] = tx
    _CACHE[plan_id] = {"server_knowledge": server_knowledge, "transactions": known}
    return list(known.values())


def clear() -> None:
    """Drop every plan's copy: the tests and the documentation start from a cold cache."""
    _CACHE.clear()
