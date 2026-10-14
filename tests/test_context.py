# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Resources and prompts through the MCP protocol."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client

from avenir_mcp import context, server

_BUDGETS = [{"id": "b1", "name": "Personal", "last_modified_on": "2026-09-24", "extra": "x"}]
_CATS = [
    {"id": "c1", "name": "Groceries", "category_group_name": "Everyday", "budgeted": 1},
    {"id": "c2", "name": "Rent", "category_group_name": "Home", "budgeted": 1},
    {
        "id": "c3",
        "name": "Inflow: Ready to Assign",
        "category_group_name": "Internal Master Category",
    },
]
_ACCOUNTS = [
    {
        "id": "a1",
        "name": "Current account",
        "type": "checking",
        "on_budget": True,
        "closed": False,
        "balance": 12.5,
    },
    {
        "id": "a2",
        "name": "Old",
        "type": "savings",
        "on_budget": True,
        "closed": True,
        "balance": 0.0,
    },
]
PROMPTS = {"monthly_review", "classify_pending", "reconcile", "plan_next_month"}


@pytest.fixture(autouse=True, name="budget")
def _budget() -> Iterator[None]:
    with (
        patch("avenir_mcp.client.get_plans", AsyncMock(return_value=_BUDGETS)),
        patch("avenir_mcp.client.get_categories", AsyncMock(return_value=_CATS)),
        patch("avenir_mcp.client.get_accounts", AsyncMock(return_value=_ACCOUNTS)),
    ):
        yield


def _run(coro_factory: Any) -> Any:
    async def run() -> Any:
        async with Client(server.mcp) as mcp_client:
            return await coro_factory(mcp_client)

    return asyncio.run(run())


def _read(uri: str) -> str:
    contents = _run(lambda c: c.read_resource(uri))
    return str(contents[0].text)


def _tool_names() -> set[str]:
    return {t.name for t in _run(lambda c: c.list_tools())}


def _named_tools(text: str) -> set[str]:
    """Words in backticks that look like tool names."""
    return set(re.findall(r"`([a-z]+(?:_[a-z]+)+)`", text))


def test_resources_and_templates_are_listed() -> None:
    """Clients can discover what context the server offers."""
    uris = {str(r.uri) for r in _run(lambda c: c.list_resources())}
    templates = {t.uri_template for t in _run(lambda c: c.list_resource_templates())}
    assert {"ynab://plans", "avenir-mcp://guide"} <= uris
    assert {
        "ynab://plans/{plan_id}/categories",
        "ynab://plans/{plan_id}/accounts",
    } <= templates


def test_budgets_resource_is_compact() -> None:
    """Only what identifies a budget."""
    assert json.loads(_read("ynab://plans")) == [
        {"plan_id": "b1", "name": "Personal", "last_modified_on": "2026-09-24"}
    ]


def test_categories_resource_groups_assignable_categories() -> None:
    """Categories by group, internal ones left out, with the ids tools need."""
    assert json.loads(_read("ynab://plans/b1/categories")) == [
        {"group": "Everyday", "categories": [{"category_id": "c1", "name": "Groceries"}]},
        {"group": "Home", "categories": [{"category_id": "c2", "name": "Rent"}]},
    ]


def test_accounts_resource_lists_open_accounts_in_currency() -> None:
    """Closed accounts are left out; balances are in currency units."""
    assert json.loads(_read("ynab://plans/b1/accounts")) == [
        {
            "account_id": "a1",
            "name": "Current account",
            "type": "checking",
            "on_budget": True,
            "balance": 12.5,
        }
    ]


def test_guide_only_names_tools_that_exist() -> None:
    """The guide cannot drift from the catalog."""
    guide = _read("avenir-mcp://guide")
    named = _named_tools(guide)
    assert named, "the guide should name the tools it explains"
    assert named <= _tool_names() | PROMPTS


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_guide_is_given_as_server_instructions(mode: str) -> None:
    """The guide reaches the model as the server's instructions, whatever the protocol.

    A client that passes them on needs no resource attached, whichever protocol
    generation it negotiates.
    """

    async def run() -> tuple[str | None, str]:
        async with Client(server.mcp, mode=mode) as mcp_client:
            if mode == "legacy":
                assert mcp_client.initialize_result is not None
                instructions = mcp_client.initialize_result.instructions
            else:
                instructions = mcp_client.instructions
            contents = await mcp_client.read_resource("avenir-mcp://guide")
            return instructions, str(contents[0].text)

    instructions, guide = asyncio.run(run())
    assert instructions == guide
    assert 'Users often still say "budget"' in guide


def test_prompts_are_listed_with_their_arguments() -> None:
    """Each workflow is a prompt the user can pick."""
    prompts = {p.name: p for p in _run(lambda c: c.list_prompts())}
    assert set(prompts) == PROMPTS
    reconcile_args = {a.name: a.required for a in prompts["reconcile"].arguments}
    assert reconcile_args == {"plan_id": True, "account_id": True, "bank_balance": True}


@pytest.mark.parametrize(
    ("name", "args", "must_name"),
    [
        ("classify_pending", {"plan_id": "b1"}, {"suggest_categories", "apply_categories"}),
        ("monthly_review", {"plan_id": "b1", "month": "2026-09-01"}, {"get_monthly_summary"}),
        (
            "reconcile",
            {"plan_id": "b1", "account_id": "a1", "bank_balance": "1234.56"},
            {"reconcile_account"},
        ),
        ("plan_next_month", {"plan_id": "b1"}, {"forecast_balance", "set_category_budget"}),
    ],
)
def test_prompts_carry_their_arguments_and_only_real_tools(
    name: str, args: dict[str, str], must_name: set[str]
) -> None:
    """A prompt fills in the user's values and names tools that exist."""
    result = _run(lambda c: c.get_prompt(name, args))
    text = "\n".join(m.content.text for m in result.messages)
    for value in args.values():
        assert value in text
    named = _named_tools(text)
    assert must_name <= named
    assert named <= _tool_names()


def test_without_auto_confirm_the_guide_is_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default guide is byte for byte the one written: every write waits for a yes."""
    monkeypatch.delenv("AVENIR_MCP_AUTO_CONFIRM", raising=False)
    assert context.guide_text(auto_confirm=False) is context.GUIDE
    assert _read("avenir-mcp://guide") == context.GUIDE
    assert "Every write shows a preview and waits for the user's confirmation" in context.GUIDE


def test_with_auto_confirm_the_guide_says_what_still_asks(monkeypatch: pytest.MonkeyPatch) -> None:
    """AVENIR_MCP_AUTO_CONFIRM=1 (fork only): undoable writes apply at once, the rest ask."""
    monkeypatch.setenv("AVENIR_MCP_AUTO_CONFIRM", "1")
    raw = _read("avenir-mcp://guide")
    assert raw == context.guide_text(auto_confirm=True)
    text = " ".join(raw.split())
    assert "Every write shows a preview" not in text
    assert "apply at once" in text
    assert "`undo_operation` can revert" in text
    for still_asks in (
        "Splits",
        "creating or editing categories",
        "approving by dates",
        "`apply_categories` with `approve`",
        "a target YNAB cannot set back",
        "undos",
    ):
        assert still_asks in text
    assert "reconciles on the first call when the balances match" in text
    assert "pass `adjust` only when the user asked" in text
    assert "never use a code on your own initiative" in text
