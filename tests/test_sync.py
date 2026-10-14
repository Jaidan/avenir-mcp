# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Tests for sync.py — the in-memory copy of a plan's transactions."""

from __future__ import annotations

from typing import Any

from avenir_mcp import sync


def test_a_plan_never_loaded_has_no_knowledge() -> None:
    """No copy yet: the next load is a full one."""
    assert sync.knowledge("b1") is None


def test_a_first_load_is_kept_with_its_counter() -> None:
    """The whole load is the copy, and its counter is what the next delta sends."""
    first = [{"id": "t1", "deleted": False}, {"id": "t2", "deleted": False}]
    assert sync.merge("b1", first, 7) == first
    assert sync.knowledge("b1") == 7


def test_a_delta_replaces_adds_and_removes() -> None:
    """A changed transaction replaces the old one, a new one joins, a deleted one leaves."""
    sync.merge("b1", [{"id": "t1", "memo": "old"}, {"id": "t2"}], 1)
    delta: list[dict[str, Any]] = [
        {"id": "t1", "memo": "new"},
        {"id": "t2", "deleted": True},
        {"id": "t3"},
    ]
    assert sync.merge("b1", delta, 2) == [{"id": "t1", "memo": "new"}, {"id": "t3"}]
    assert sync.knowledge("b1") == 2


def test_a_deleted_transaction_never_seen_is_ignored() -> None:
    """A delta can report the deletion of a transaction the copy never held."""
    assert not sync.merge("b1", [{"id": "gone", "deleted": True}], 3)


def test_plans_are_kept_apart() -> None:
    """Each plan has its own copy and its own counter."""
    sync.merge("b1", [{"id": "a"}], 1)
    sync.merge("b2", [{"id": "b"}], 9)
    assert (sync.knowledge("b1"), sync.knowledge("b2")) == (1, 9)


def test_a_full_reload_replaces_the_copy() -> None:
    """fresh: what YNAB returned is the whole copy, even what it no longer mentions is gone."""
    sync.merge("b1", [{"id": "stale"}, {"id": "a"}], 1)
    assert sync.merge("b1", [{"id": "a"}, {"id": "gone", "deleted": True}], 4, fresh=True) == [
        {"id": "a"}
    ]
    assert sync.knowledge("b1") == 4


def test_clear_drops_every_plan() -> None:
    """A cold cache for every plan."""
    sync.merge("b1", [{"id": "a"}], 1)
    sync.clear()
    assert sync.knowledge("b1") is None


def test_a_delta_older_than_the_copy_changes_nothing() -> None:
    """A delta that lands after a newer load holds nothing new: copy and counter stay."""
    sync.merge("b1", [{"id": "a"}], 4, fresh=True)
    assert sync.merge("b1", [{"id": "ghost"}, {"id": "a", "deleted": True}], 2) == [{"id": "a"}]
    assert sync.knowledge("b1") == 4
