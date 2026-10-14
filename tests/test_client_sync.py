# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""get_transactions(fresh=True): a full reload that never loses the plan's copy."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from avenir_mcp import client

_FULL = {"data": {"transactions": [{"id": "t1"}, {"id": "t2"}], "server_knowledge": 1}}


def _load(get: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """Read plan b1's transactions with `get` standing for YNAB."""
    with patch("avenir_mcp.client._get", get):
        return asyncio.run(client.get_transactions("b1", **kwargs))


def test_a_fresh_load_replaces_the_copy() -> None:
    """Fresh asks for every transaction, and what it returns becomes the whole copy."""
    _load(AsyncMock(return_value=_FULL))
    reload = {"data": {"transactions": [{"id": "t1"}], "server_knowledge": 5}}
    get = AsyncMock(return_value=reload)
    assert _load(get, fresh=True) == [{"id": "t1"}]
    assert "last_knowledge_of_server" not in get.call_args.kwargs["params"]
    get = AsyncMock(return_value={"data": {"transactions": [], "server_knowledge": 5}})
    assert _load(get) == [{"id": "t1"}]
    assert get.call_args.kwargs["params"]["last_knowledge_of_server"] == 5


def test_a_fresh_load_that_fails_keeps_the_copy() -> None:
    """The copy is replaced only once the full load has arrived: a failure leaves it whole."""
    _load(AsyncMock(return_value=_FULL))
    with pytest.raises(RuntimeError):
        _load(AsyncMock(side_effect=RuntimeError("YNAB is down")), fresh=True)
    get = AsyncMock(return_value={"data": {"transactions": [], "server_knowledge": 1}})
    assert _load(get) == [{"id": "t1"}, {"id": "t2"}]
    assert get.call_args.kwargs["params"]["last_knowledge_of_server"] == 1


def test_a_fresh_filtered_load_leaves_the_copy_alone() -> None:
    """A filtered read bypasses the copy, fresh or not."""
    _load(AsyncMock(return_value=_FULL))
    _load(AsyncMock(return_value=_FULL), fresh=True, since_date="2026-09-01")
    get = AsyncMock(return_value={"data": {"transactions": [], "server_knowledge": 1}})
    assert _load(get) == [{"id": "t1"}, {"id": "t2"}]
    assert get.call_args.kwargs["params"]["last_knowledge_of_server"] == 1


def test_a_delta_during_a_failed_fresh_load_is_merged_into_the_whole_copy() -> None:
    """A delta that lands while a fresh load is on its way still merges into every transaction."""

    async def run() -> list[dict[str, Any]]:
        delta_sent, fresh_sent = asyncio.Event(), asyncio.Event()
        release_delta, delta_done = asyncio.Event(), asyncio.Event()

        async def get(_path: str, params: dict[str, Any]) -> dict[str, Any]:
            if "last_knowledge_of_server" in params:
                delta_sent.set()
                await release_delta.wait()
                return {"data": {"transactions": [{"id": "t3"}], "server_knowledge": 2}}
            fresh_sent.set()
            await delta_done.wait()
            raise RuntimeError("YNAB is down")

        with patch("avenir_mcp.client._get", AsyncMock(return_value=_FULL)):
            await client.get_transactions("b1")
        with patch("avenir_mcp.client._get", get):
            delta = asyncio.create_task(client.get_transactions("b1"))
            await delta_sent.wait()
            fresh = asyncio.create_task(client.get_transactions("b1", fresh=True))
            await fresh_sent.wait()
            release_delta.set()
            await delta
            delta_done.set()
            with pytest.raises(RuntimeError):
                await fresh
        empty = {"data": {"transactions": [], "server_knowledge": 2}}
        with patch("avenir_mcp.client._get", AsyncMock(return_value=empty)):
            return await client.get_transactions("b1")

    assert asyncio.run(run()) == [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}]
