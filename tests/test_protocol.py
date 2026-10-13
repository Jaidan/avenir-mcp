# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Tests through the MCP protocol: what a client actually sees."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

from fastmcp import Client

from avenir_mcp import server

_TXS: list[dict[str, Any]] = [
    {
        "id": f"h{i}",
        "date": "2026-08-01",
        "amount": -5000,
        "payee_name": "CORNER SHOP",
        "memo": None,
        "account_name": "Checking",
        "category_id": "c-food",
        "transfer_account_id": None,
        "deleted": False,
    }
    for i in range(3)
] + [
    {
        "id": "p1",
        "date": "2026-09-02",
        "amount": -7250,
        "payee_name": "CORNER SHOP",
        "memo": None,
        "account_name": "Checking",
        "category_id": None,
        "transfer_account_id": None,
        "deleted": False,
    }
]
_CATS = [{"id": "c-food", "name": "Groceries", "category_group_name": "Everyday"}]


async def _tool(name: str) -> Any:
    async with Client(server.mcp) as mcp_client:
        return next(t for t in await mcp_client.list_tools() if t.name == name)


async def _call(name: str, args: dict[str, Any]) -> Any:
    async with Client(server.mcp) as mcp_client:
        return await mcp_client.call_tool(name, args, raise_on_error=False)


def test_suggest_categories_is_declared_read_only() -> None:
    """Clients may run it without confirmation: it changes nothing."""
    tool = asyncio.run(_tool("suggest_categories"))
    assert tool.annotations.read_only_hint is True
    assert tool.annotations.open_world_hint is True


def test_suggest_categories_publishes_a_precise_output_schema() -> None:
    """The output schema names the fields, so a client can validate the answer."""
    schema = asyncio.run(_tool("suggest_categories")).output_schema
    assert {"pending_count", "suggested_count", "items", "categories", "next_cursor"} <= set(
        schema["properties"]
    )


_ACCOUNTS = [{"id": "acc", "on_budget": True}, {"id": "acc-loan", "on_budget": False}]


def test_suggest_categories_returns_structured_content_in_three_requests() -> None:
    """One page costs three YNAB requests, whatever the number of items."""
    get_txs = AsyncMock(return_value=_TXS)
    get_cats = AsyncMock(return_value=_CATS)
    get_accounts = AsyncMock(return_value=_ACCOUNTS)
    with (
        patch("avenir_mcp.client.get_transactions", get_txs),
        patch("avenir_mcp.client.get_categories", get_cats),
        patch("avenir_mcp.client.get_accounts", get_accounts),
    ):
        result = asyncio.run(_call("suggest_categories", {"plan_id": "b1"}))
    assert not result.is_error
    data = result.structured_content
    assert data["pending_count"] == 1
    assert data["items"][0]["amount"] == -7.25
    assert data["items"][0]["suggestion"]["category_name"] == "Groceries"
    get_txs.assert_awaited_once_with("b1")
    get_cats.assert_awaited_once_with("b1")
    get_accounts.assert_awaited_once_with("b1")


def test_suggest_categories_skips_off_budget_accounts() -> None:
    """A tracking account's starting balance is not waiting for a category."""
    loan = {
        **_TXS[-1],
        "id": "loan-start",
        "account_id": "acc-loan",
        "payee_name": "Starting Balance",
    }
    with (
        patch("avenir_mcp.client.get_transactions", AsyncMock(return_value=[*_TXS, loan])),
        patch("avenir_mcp.client.get_categories", AsyncMock(return_value=_CATS)),
        patch("avenir_mcp.client.get_accounts", AsyncMock(return_value=_ACCOUNTS)),
    ):
        data = asyncio.run(_call("suggest_categories", {"plan_id": "b1"})).structured_content
    assert "loan-start" not in {item["transaction_id"] for item in data["items"]}


def test_suggest_categories_reports_a_bad_cursor_as_a_tool_error() -> None:
    """A bad cursor comes back as isError with a message the model can act on."""
    with (
        patch("avenir_mcp.client.get_transactions", AsyncMock(return_value=[])),
        patch("avenir_mcp.client.get_categories", AsyncMock(return_value=_CATS)),
        patch("avenir_mcp.client.get_accounts", AsyncMock(return_value=_ACCOUNTS)),
    ):
        result = asyncio.run(_call("suggest_categories", {"plan_id": "b1", "cursor": "x"}))
    assert result.is_error
    assert "next_cursor" in result.content[0].text


def test_budget_vs_actual_describes_every_field() -> None:
    """Its answer has an output schema whose fields, group included, are described."""

    async def run() -> Any:
        async with Client(server.mcp) as mcp_client:
            tools = await mcp_client.list_tools()
        return next(t for t in tools if t.name == "get_budget_vs_actual").output_schema

    schema = asyncio.run(run())
    item = schema["properties"]["result"]["items"]["properties"]
    assert {"group", "utilization_pct"} <= set(item)
    assert all(field.get("description") for field in item.values())


def test_descriptions_carry_no_docstring_sections() -> None:
    """Agents read the prose of a docstring; Args, Returns and Raises stay in the code."""

    async def descriptions() -> dict[str, str]:
        server.configure(enable_writes=True)
        try:
            async with Client(server.mcp) as mcp_client:
                found = {t.name: t.description or "" for t in await mcp_client.list_tools()}
                found |= {
                    f"resource {r.name}": r.description or ""
                    for r in await mcp_client.list_resources()
                }
                found |= {
                    f"template {r.name}": r.description or ""
                    for r in await mcp_client.list_resource_templates()
                }
                found |= {
                    f"prompt {p.name}": p.description or "" for p in await mcp_client.list_prompts()
                }
                return found
        finally:
            server.configure(enable_writes=False)

    found = asyncio.run(descriptions())
    assert len(found) == 41
    leaking = {
        name
        for name, text in found.items()
        if any(section in text for section in ("Args:", "Returns:", "Raises:"))
    }
    assert not leaking


def _undescribed(schema: dict[str, Any], defs: dict[str, Any], path: str) -> list[str]:
    """Every property under a schema without a description, following $ref once each."""
    missing = []
    for name, field in schema.get("properties", {}).items():
        if not field.get("description") and "$ref" not in field and name != "result":
            missing.append(f"{path}.{name}")
        missing += _undescribed(field, defs, f"{path}.{name}")
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            missing += _undescribed(schema[key], defs, path)
    for option in schema.get("anyOf", []) + schema.get("allOf", []):
        missing += _undescribed(option, defs, path)
    ref = schema.get("$ref", "").removeprefix("#/$defs/")
    if ref and ref in defs:
        missing += _undescribed(defs.pop(ref), defs, ref)
    return missing


def test_every_parameter_and_answer_field_is_described_to_the_agent() -> None:
    """Args of a tool's docstring and field docstrings of its models reach the schemas.

    A parameter or field without a description is one the agent must guess; the
    wrapper `result` that FastMCP adds around a list is the only exception.
    """

    async def run() -> Any:
        async with Client(server.mcp) as mcp_client:
            return await mcp_client.list_tools()

    missing = []
    for tool in asyncio.run(run()):
        for kind, schema in (("in", tool.input_schema), ("out", tool.output_schema or {})):
            defs = dict(schema.get("$defs", {}))
            missing += _undescribed(schema, defs, f"{tool.name} ({kind})")
    assert missing == []


def test_suggest_categories_takes_a_window_and_fetches_the_whole_plan() -> None:
    """The window limits the items; the transactions fetched, history included, are all of them."""
    get_txs = AsyncMock(return_value=_TXS)
    with (
        patch("avenir_mcp.client.get_transactions", get_txs),
        patch("avenir_mcp.client.get_categories", AsyncMock(return_value=_CATS)),
        patch("avenir_mcp.client.get_accounts", AsyncMock(return_value=_ACCOUNTS)),
    ):
        outside = {"plan_id": "b1", "since_date": "2001-01-01", "until_date": "2001-01-31"}
        empty = asyncio.run(_call("suggest_categories", outside)).structured_content
        reversed_ = asyncio.run(
            _call(
                "suggest_categories",
                {"plan_id": "b1", "since_date": "2026-02-01", "until_date": "2026-01-01"},
            )
        )
    assert empty["pending_count"] == 0
    get_txs.assert_awaited_with("b1")
    assert reversed_.is_error
    assert "swap them" in reversed_.content[0].text
