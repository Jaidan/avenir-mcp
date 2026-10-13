# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Tests for server.py — FastMCP instance and all 14 MCP tools."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import Client, Context
from fastmcp.exceptions import ToolError

import avenir_mcp
from avenir_mcp import server, tools_budget, updates

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------


def test_mcp_instance_name() -> None:
    """The FastMCP instance must be named 'avenir'."""
    assert server.mcp.name == "avenir-mcp"


def test_catalog_is_exactly_the_published_tools() -> None:
    """One tool per task: tools superseded by safer ones are gone."""
    tool_names = sorted(t.name for t in asyncio.run(server.mcp.list_tools()))
    assert tool_names == sorted(
        [
            "list_plans",
            "list_accounts",
            "list_category_groups",
            "get_category_balances",
            "get_monthly_summary",
            "get_budget_vs_actual",
            "get_spending_trends",
            "suggest_categories",
            "find_transactions",
            "list_scheduled_transactions",
            "forecast_balance",
            "apply_categories",
            "split_transaction",
            "undo_operation",
            "reconcile_account",
            "update_category",
            "create_category",
            "set_category_budget",
            "set_category_budgets",
            "move_money",
            "create_transactions",
            "approve_transactions",
            "import_transactions",
            "flag_transactions",
            "find_recurring_charges",
            "get_net_worth_trend",
            "get_runway",
            "get_savings_rate",
            "get_underfunded_targets",
            "get_debt_payoff_plan",
            "get_age_of_money",
            "set_category_target",
            "list_payees",
            "rename_payee",
        ]
    )


def test_all_names_the_entry_points_and_no_tool() -> None:
    """__all__ names the ways into the server; a tool is never re-exported there.

    A tool reaches an agent by registering on mcp, not by being an attribute of
    server: listing some tools in __all__ said twice what the registry says once,
    and the two drifted apart.
    """
    assert server.__all__ == ["WRITE_TAG", "configure", "http_options", "main", "mcp", "today"]
    server.configure(enable_writes=True)  # count the write tools too
    registered = {tool.name for tool in asyncio.run(server.mcp.list_tools())}
    assert registered.isdisjoint(server.__all__)


def test_every_tool_module_is_imported_so_its_tools_register() -> None:
    """A new tools_*.py module registers nothing until server.py imports it."""
    modules = sorted(path.stem for path in Path(server.__file__).parent.glob("tools_*.py"))
    assert modules
    missing = [name for name in modules if not isinstance(getattr(server, name, None), ModuleType)]
    assert not missing, missing


# ---------------------------------------------------------------------------
# list_plans
# ---------------------------------------------------------------------------


def test_list_budgets_keeps_what_an_agent_needs() -> None:
    """Each budget comes back as its id, name and months, without YNAB's other settings."""
    budgets = [
        {
            "id": "b1",
            "name": "Business",
            "first_month": "2026-01-01",
            "last_month": "2026-09-01",
            "currency_format": {"iso_code": "EUR"},
        },
        {"id": "b2", "name": "Empty"},
    ]
    with patch("avenir_mcp.client.get_plans", new=AsyncMock(return_value=budgets)):
        result = asyncio.run(tools_budget.list_plans())
    assert [b.model_dump() for b in result] == [
        {"id": "b1", "name": "Business", "first_month": "2026-01-01", "last_month": "2026-09-01"},
        {"id": "b2", "name": "Empty", "first_month": None, "last_month": None},
    ]


# ---------------------------------------------------------------------------
# get_category_balances
# ---------------------------------------------------------------------------


def test_get_category_balances_default_month() -> None:
    """Default month is 'current'."""
    cats = [{"id": "c1", "name": "Rent", "budgeted": 500_000, "activity": 0, "balance": 500_000}]
    with patch(
        "avenir_mcp.client.get_month_categories", new=AsyncMock(return_value=cats)
    ) as mock_fn:
        asyncio.run(tools_budget.get_category_balances("b1"))
    mock_fn.assert_called_once_with("b1", "current")


def test_get_category_balances_explicit_month() -> None:
    """Explicit month is forwarded to client.get_month_categories."""
    cats: list[dict[str, Any]] = []
    with patch(
        "avenir_mcp.client.get_month_categories", new=AsyncMock(return_value=cats)
    ) as mock_fn:
        asyncio.run(tools_budget.get_category_balances("b1", "2026-03-01"))
    mock_fn.assert_called_once_with("b1", "2026-03-01")


# ---------------------------------------------------------------------------
# get_monthly_summary
# ---------------------------------------------------------------------------


def test_get_monthly_summary_is_compact_and_in_currency() -> None:
    """The summary is totals in currency units, not YNAB's raw month."""
    month = {
        "month": "2026-04-01",
        "income": 1_000_000,
        "budgeted": 5_000_000,
        "activity": -3_200_000,
        "to_be_budgeted": 0,
        "categories": [{"id": "c1", "name": "Rent", "balance": 1_000, "note": "x" * 5000}],
    }
    with patch("avenir_mcp.client.get_month", new=AsyncMock(return_value=month)):
        result = asyncio.run(tools_budget.get_monthly_summary("b1", "2026-04-01"))
    assert result.activity == -3200.0
    assert "categories" not in result.model_dump()
    assert result.overspent == []


def test_get_category_balances_are_in_currency() -> None:
    """Category lines carry currency amounts, not milliunits."""
    cats = [{"id": "c1", "name": "Rent", "budgeted": 500_000, "activity": 0, "balance": 500_000}]
    with patch("avenir_mcp.client.get_month_categories", new=AsyncMock(return_value=cats)):
        result = asyncio.run(tools_budget.get_category_balances("b1"))
    assert result[0].budgeted == 500.0


@pytest.mark.parametrize("month", ["2026-13-01", "2026-04", "april", "2026-04-15"])
def test_month_tools_reject_a_malformed_month_with_a_way_forward(month: str) -> None:
    """A bad month is refused before calling YNAB, saying the expected format."""
    for tool in (
        tools_budget.get_monthly_summary,
        tools_budget.get_category_balances,
        tools_budget.get_budget_vs_actual,
    ):
        with patch("avenir_mcp.client.get_month", new=AsyncMock()) as fetch:
            with pytest.raises(ToolError, match="YYYY-MM-01"):
                asyncio.run(tool("b1", month))
        fetch.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_budget_vs_actual
# ---------------------------------------------------------------------------


def test_get_budget_vs_actual_returns_analytics_output() -> None:
    """get_budget_vs_actual should chain get_month_categories and analytics."""
    cats = [
        {"id": "c1", "name": "Rent", "budgeted": 500_000, "activity": -400_000, "balance": 100_000}
    ]
    with patch("avenir_mcp.client.get_month_categories", new=AsyncMock(return_value=cats)):
        result = asyncio.run(tools_budget.get_budget_vs_actual("b1"))
    assert result[0].utilization_pct == 80.0


# ---------------------------------------------------------------------------
# get_spending_trends
# ---------------------------------------------------------------------------


def test_get_spending_trends_fetches_last_n_months() -> None:
    """get_spending_trends with months_count=2 should fetch 2 months of categories."""
    months = [{"month": "2026-02-01"}, {"month": "2026-03-01"}, {"month": "2026-04-01"}]
    cats = [{"id": "c1", "name": "AWS", "budgeted": 0, "activity": -100_000, "balance": 0}]

    mock_get_months = AsyncMock(return_value=months)
    mock_month_cats = AsyncMock(return_value=cats)

    with (
        patch("avenir_mcp.client.get_months", mock_get_months),
        patch("avenir_mcp.client.get_month_categories", mock_month_cats),
    ):
        result = asyncio.run(tools_budget.get_spending_trends("b1", months_count=2))

    # Should have fetched categories for exactly 2 months (last 2)
    assert mock_month_cats.call_count == 2
    assert "AWS" in result


# ---------------------------------------------------------------------------
# list_category_groups / create_category
# ---------------------------------------------------------------------------


def test_list_category_groups_delegates_to_client() -> None:
    """list_category_groups must return client.get_category_groups output."""
    groups = [{"id": "g1", "name": "Software"}]
    with patch(
        "avenir_mcp.client.get_category_groups", new=AsyncMock(return_value=groups)
    ) as mock_fn:
        result = asyncio.run(tools_budget.list_category_groups("b1"))
    mock_fn.assert_called_once_with("b1")
    assert [g.model_dump() for g in result] == groups


# ---------------------------------------------------------------------------
# set_category_budget / list_accounts
# ---------------------------------------------------------------------------


def test_list_accounts_delegates_to_client() -> None:
    """list_accounts must return client.get_accounts output."""
    accounts = [
        {
            "uncleared_balance": 0.0,
            "cleared_balance": 8000.0,
            "balance": 8000.0,
            "closed": True,
            "on_budget": False,
            "type": "savings",
            "name": "Old savings",
            "id": "a9",
            "bank_link": "broken",
            "last_reconciled": "2026-03-31",
        }
    ]
    with patch("avenir_mcp.client.get_accounts", new=AsyncMock(return_value=accounts)) as mock_fn:
        result = asyncio.run(tools_budget.list_accounts("b1"))
    mock_fn.assert_called_once_with("b1")
    assert [a.model_dump() for a in result] == accounts
    assert result[0].on_budget is False


def test_approve_transactions_delegates_to_client() -> None:
    """approve_transactions must call client.approve_transactions and be exposed."""
    with patch(
        "avenir_mcp.client.approve_transactions", new=AsyncMock(return_value={"approved": 1})
    ) as mock_fn:
        result = asyncio.run(
            tools_budget.approve_transactions("b1", MagicMock(spec=Context), ["t1"])
        )
    mock_fn.assert_called_once_with("b1", ["t1"])
    assert isinstance(result, tools_budget.Approval)
    assert result.approved == 1
    assert "approve_transactions" in [t.name for t in asyncio.run(server.mcp.list_tools())]


# ---------------------------------------------------------------------------
# main — entry point of the `avenir-mcp` command
# ---------------------------------------------------------------------------


def test_main_runs_stdio_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without configuration, the server speaks stdio, as MCP clients expect."""
    monkeypatch.delenv("AVENIR_MCP_TRANSPORT", raising=False)
    with patch.object(server.mcp, "run") as run:
        server.main()
    run.assert_called_once_with(transport="stdio")


def test_main_runs_http_on_localhost_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """AVENIR_MCP_TRANSPORT=http alone serves on 127.0.0.1:8103, never on all interfaces."""
    monkeypatch.setenv("AVENIR_MCP_TRANSPORT", "http")
    monkeypatch.delenv("AVENIR_MCP_HOST", raising=False)
    monkeypatch.delenv("AVENIR_MCP_PORT", raising=False)
    monkeypatch.setenv("HOST", "my-laptop.local")  # zsh sets HOST; it must be ignored
    with patch.object(server.mcp, "run") as run:
        server.main()
    kwargs = run.call_args.kwargs
    assert (kwargs["transport"], kwargs["host"], kwargs["port"]) == (
        "streamable-http",
        "127.0.0.1",
        8103,
    )


def test_main_runs_http_on_configured_host_and_port(monkeypatch: pytest.MonkeyPatch) -> None:
    """AVENIR_MCP_HOST and AVENIR_MCP_PORT choose the HTTP address."""
    monkeypatch.setenv("AVENIR_MCP_TRANSPORT", "http")
    monkeypatch.setenv("AVENIR_MCP_HOST", "127.0.0.2")
    monkeypatch.setenv("AVENIR_MCP_PORT", "9000")
    with patch.object(server.mcp, "run") as run:
        server.main()
    kwargs = run.call_args.kwargs
    assert (kwargs["transport"], kwargs["host"], kwargs["port"]) == (
        "streamable-http",
        "127.0.0.2",
        9000,
    )


def test_initialize_names_avenir_mcp_and_its_version() -> None:
    """A client learns which avenir-mcp it talks to, not which FastMCP runs it."""

    async def run() -> Any:
        async with Client(server.mcp) as mcp_client:
            return mcp_client.server_info

    info = asyncio.run(run())
    assert (info.name, info.version) == ("avenir-mcp", avenir_mcp.__version__)


def test_main_prints_the_version_and_stops(capsys: pytest.CaptureFixture[str]) -> None:
    """`avenir-mcp --version` answers for bug reports and starts no server."""
    with patch.object(server.mcp, "run") as run:
        server.main(["--version"])
    assert capsys.readouterr().out == (
        f"avenir-mcp {avenir_mcp.__version__} (YNAB API v{avenir_mcp.YNAB_API_VERSION})\n"
    )
    run.assert_not_called()


def test_today_is_the_real_date() -> None:
    """Tools reckon from the actual date unless a test fixes it."""
    assert server.today() == date.today()


def test_main_adds_the_update_notice_to_the_instructions(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A newer release reaches the agent's instructions, and the logs as a warning."""
    monkeypatch.delenv("AVENIR_MCP_TRANSPORT", raising=False)
    guide = server.mcp.instructions
    seen: dict[str, Any] = {}

    def check(env: Any, current: str, now: Any) -> str:
        seen.update(env=env, current=current, now=now)
        return "Update: avenir-mcp 9.9.9 is available."

    try:
        with patch.object(updates, "check", check), patch.object(server.mcp, "run"):
            server.main([])
        assert server.mcp.instructions == f"{guide}\n\nUpdate: avenir-mcp 9.9.9 is available."
        assert seen["current"] == avenir_mcp.__version__
        assert seen["env"]["AVENIR_MCP_NO_UPDATE_CHECK"] == "1"
        assert seen["now"].tzinfo is not None
        assert "Update: avenir-mcp 9.9.9 is available." in caplog.text
    finally:
        server.mcp.instructions = guide


def test_main_leaves_the_instructions_alone_when_up_to_date(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No notice, no change: the guide stays exactly as written."""
    monkeypatch.delenv("AVENIR_MCP_TRANSPORT", raising=False)
    guide = server.mcp.instructions
    with patch.object(updates, "check", return_value=None), patch.object(server.mcp, "run"):
        server.main([])
    assert server.mcp.instructions == guide
