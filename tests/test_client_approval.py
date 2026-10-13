# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Every update the client sends carries the approval the transaction should keep."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from avenir_mcp import client

_PATH = "/plans/b1/transactions"


def test_category_update_keeps_each_transactions_approval() -> None:
    """YNAB unapproves a transaction updated without `approved`: it is always sent."""
    patched = AsyncMock(return_value={"data": {"transaction_ids": ["t1", "t2"]}})
    with patch("avenir_mcp.client._patch", patched):
        asyncio.run(
            client.set_transaction_categories(
                "b1", [("t1", "c1"), ("t2", None)], approved={"t1": True, "t2": False}
            )
        )
    assert patched.call_args.args == (
        _PATH,
        {
            "transactions": [
                {"id": "t1", "category_id": "c1", "approved": True},
                {"id": "t2", "category_id": None, "approved": False},
            ]
        },
    )


def test_split_update_keeps_the_transactions_approval() -> None:
    """A split is sent with the approval the transaction had."""
    patched = AsyncMock(return_value={"data": {"transaction_ids": ["t1"]}})
    lines = [{"amount": -1.0, "category_id": "c1", "memo": None}]
    with patch("avenir_mcp.client._patch", patched):
        asyncio.run(client.split_transaction("b1", "t1", lines, approved=True))
    sent = patched.call_args.args[1]["transactions"][0]
    assert sent["approved"] is True


def test_cleared_update_keeps_each_transactions_approval() -> None:
    """A cleared-status change is sent with each transaction's approval."""
    patched = AsyncMock(return_value={"data": {"transaction_ids": ["t1", "t2"]}})
    with patch("avenir_mcp.client._patch", patched):
        asyncio.run(
            client.set_transactions_cleared(
                "b1", ["t1", "t2"], "cleared", approved={"t1": True, "t2": False}
            )
        )
    assert patched.call_args.args == (
        _PATH,
        {
            "transactions": [
                {"id": "t1", "cleared": "cleared", "approved": True},
                {"id": "t2", "cleared": "cleared", "approved": False},
            ]
        },
    )


def test_flag_update_keeps_each_transactions_approval() -> None:
    """A flag change is sent with each transaction's approval."""
    patched = AsyncMock(return_value={"data": {"transaction_ids": ["t1", "t2"]}})
    with patch("avenir_mcp.client._patch", patched):
        asyncio.run(
            client.set_flags(
                "b1", [("t1", "red"), ("t2", None)], approved={"t1": True, "t2": False}
            )
        )
    assert patched.call_args.args == (
        _PATH,
        {
            "transactions": [
                {"id": "t1", "flag_color": "red", "approved": True},
                {"id": "t2", "flag_color": None, "approved": False},
            ]
        },
    )
