# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""get_underfunded_targets through the MCP protocol: read-only, one YNAB request."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client

from avenir_mcp import server

from .mcp_helpers import call, tool_schema


def _cat(key: str, needed: int, due: str | None = None) -> dict[str, Any]:
    return {
        "id": key,
        "name": key.title(),
        "category_group_name": "Everyday",
        "hidden": False,
        "deleted": False,
        "goal_type": "NEED",
        "goal_target": 300_000,
        "goal_target_date": due,
        "goal_cadence": 0 if due else 1,
        "goal_cadence_frequency": 1,
        "goal_under_funded": needed,
        "goal_overall_left": needed,
        "goal_percentage_complete": 50,
        "goal_months_to_budget": 2 if due else None,
        "goal_snoozed_at": None,
    }


_MONTH = {
    "month": "2026-09-01",
    "to_be_budgeted": 100_000,
    "categories": [
        _cat("groceries", 50_000),
        _cat("rail", 80_000, due="2026-10-01"),
        _cat("rent", 0),
    ],
}


@pytest.fixture(name="ynab")
def _ynab() -> Iterator[AsyncMock]:
    month = AsyncMock(return_value=_MONTH)
    with patch("avenir_mcp.client.get_month", month):
        yield month


def _tools(enable_writes: bool) -> dict[str, Any]:
    async def listed() -> dict[str, Any]:
        server.configure(enable_writes=enable_writes)
        try:
            async with Client(server.mcp) as mcp_client:
                return {tool.name: tool for tool in await mcp_client.list_tools()}
        finally:
            server.configure(enable_writes=False)

    return asyncio.run(listed())


def test_underfunded_targets_is_read_only() -> None:
    """Declared read-only and idempotent: a client may call it without asking."""
    found = _tools(enable_writes=False)["get_underfunded_targets"].annotations
    assert found.read_only_hint is True
    assert found.idempotent_hint is True
    assert found.open_world_hint is True


def test_the_month_in_one_request(ynab: AsyncMock) -> None:
    """The dated target first; 130 needed, 100 to assign: 30 short."""
    answer = call(
        "get_underfunded_targets", {"plan_id": "b1", "month": "2026-09-01"}
    ).structured_content
    assert [t["category_id"] for t in answer["targets"]] == ["rail", "groceries"]
    assert (answer["needed"], answer["ready_to_assign"], answer["short_by"]) == (130.0, 100.0, 30.0)
    assert answer["month"] == "2026-09-01"
    ynab.assert_awaited_once_with("b1", "2026-09-01")


def test_the_current_month_by_default(ynab: AsyncMock) -> None:
    """Without a month, YNAB is asked for the current one."""
    answer = call("get_underfunded_targets", {"plan_id": "b1", "limit": 1}).structured_content
    assert [t["category_id"] for t in answer["targets"]] == ["rail"]
    assert answer["more"] == 1
    ynab.assert_awaited_once_with("b1", "current")


def test_a_malformed_month_is_refused_before_any_request(ynab: AsyncMock) -> None:
    """The agent learns the format; YNAB is not asked."""
    answer = call("get_underfunded_targets", {"plan_id": "b1", "month": "2026-13-01"})
    assert answer.is_error
    assert "YYYY-MM-01" in answer.content[0].text
    ynab.assert_not_awaited()


@pytest.mark.parametrize("limit", [0, 201])
def test_a_limit_out_of_range_is_refused(ynab: AsyncMock, limit: int) -> None:
    """Refused before YNAB is asked anything."""
    assert call("get_underfunded_targets", {"plan_id": "b1", "limit": limit}).is_error
    ynab.assert_not_awaited()


def test_the_schema_states_the_range_of_the_limit() -> None:
    """The agent sees 1 to 200 before calling; no limit lists every target."""
    prop = tool_schema("get_underfunded_targets")["properties"]["limit"]
    bounded = next(option for option in prop["anyOf"] if option.get("type") == "integer")
    assert (bounded["minimum"], bounded["maximum"], prop["default"]) == (1, 200, None)


def test_the_description_names_the_write_tools_only_when_they_exist() -> None:
    """Read-only, it points to YNAB itself; with writes, to the tools that budget categories."""
    read_only = _tools(enable_writes=False)["get_underfunded_targets"].description
    writing = _tools(enable_writes=True)["get_underfunded_targets"].description
    assert "move_money" not in read_only
    assert "in YNAB itself" in read_only
    assert "move_money" in writing
    assert "set_category_budget" in writing
    assert "set_category_budgets" in writing
