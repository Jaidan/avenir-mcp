# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Capture real tool answers on the demo budget, for the documentation.

Every example in the docs is what avenir-mcp actually returns on the invented demo
budget, with the date fixed and random identifiers replaced by placeholders, so
the files only change when the behaviour does. Each capture also records how
many requests the call sent to YNAB, measured on a cold cache.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, TypeVar
from unittest.mock import patch

from fastmcp import Client

from evals import fake_ynab

TODAY = date(2026, 9, 25)
BUDGET = "demo-budget"

T = TypeVar("T")


@dataclass(frozen=True)
class Call:
    """One documented call: a snippet name, a tool, its arguments."""

    name: str
    tool: str
    args: dict[str, Any]
    keep: int = 4
    # Apply the first confirmation code returned, then make this call: shows undo.
    after_applying: tuple[str, dict[str, Any]] | None = None


@dataclass(frozen=True)
class Capture:
    """What a call sent and received."""

    tool: str
    args: dict[str, Any]
    text: str
    is_error: bool
    requests: int


_APPLY = {
    "plan_id": BUDGET,
    "assignments": [
        {"transaction_id": "tx-048", "category_id": "cat-groceries"},
        {"transaction_id": "tx-049", "category_id": "cat-transport"},
    ],
}

# What the documented writes type in, in each documentation language.
_TYPED: dict[str, dict[str, str]] = {
    "fr": {
        "Bills": "Charges fixes",
        "Everyday": "Quotidien",
        "not imported by the bank": "non importé par la banque",
        "Pets": "Animaux",
        "Sport": "Sport",
    },
    "es": {
        "Bills": "Facturas",
        "Everyday": "Día a día",
        "not imported by the bank": "no importado por el banco",
        "Pets": "Mascotas",
        "Sport": "Deporte",
    },
    "de": {
        "Bills": "Fixkosten",
        "Everyday": "Alltag",
        "not imported by the bank": "nicht von der Bank importiert",
        "Pets": "Haustiere",
        "Sport": "Sport",
    },
    "nl": {
        "Bills": "Vaste lasten",
        "Everyday": "Dagelijks",
        "not imported by the bank": "niet door de bank geïmporteerd",
        "Pets": "Huisdieren",
        "Sport": "Sport",
    },
}


def _typed(data: Any, language: str) -> Any:
    """The same arguments, with what a person types written in their language."""
    if isinstance(data, dict):
        return {key: _typed(value, language) for key, value in data.items()}
    if isinstance(data, list):
        return [_typed(item, language) for item in data]
    if isinstance(data, str):
        return _TYPED.get(language, {}).get(data, data)
    return data


CALLS: list[Call] = [
    Call("list_plans", "list_plans", {}),
    Call("list_accounts", "list_accounts", {"plan_id": BUDGET}),
    Call("list_category_groups", "list_category_groups", {"plan_id": BUDGET}),
    Call("monthly_summary", "get_monthly_summary", {"plan_id": BUDGET, "month": "2026-09-01"}),
    Call("category_balances", "get_category_balances", {"plan_id": BUDGET, "month": "2026-09-01"}),
    Call("budget_vs_actual", "get_budget_vs_actual", {"plan_id": BUDGET, "month": "2026-09-01"}),
    # Every category of a full month, for the chart on the home page.
    Call(
        "august_categories",
        "get_budget_vs_actual",
        {"plan_id": BUDGET, "month": "2026-08-01"},
        keep=100,
    ),
    Call("spending_trends", "get_spending_trends", {"plan_id": BUDGET, "months_count": 3}, 3),
    # The share of the salary kept, over the months the demo budget holds.
    Call("savings_rate", "get_savings_rate", {"plan_id": BUDGET}, keep=6),
    # The rail card and the tennis club due by a date first, then the monthly targets.
    Call(
        "underfunded_targets",
        "get_underfunded_targets",
        {"plan_id": BUDGET, "month": "2026-09-01"},
    ),
    # YNAB's own figure for every month the demo budget holds, June's still unknown.
    Call("age_of_money", "get_age_of_money", {"plan_id": BUDGET}),
    Call("suggest_categories", "suggest_categories", {"plan_id": BUDGET, "limit": 3}, 3),
    Call("apply_preview", "apply_categories", _APPLY),
    Call(
        "reconcile_gap",
        "reconcile_account",
        {"plan_id": BUDGET, "account_id": "acc-checking", "bank_balance": 3440.80},
    ),
    Call("recurring_charges", "find_recurring_charges", {"plan_id": BUDGET}, keep=10),
    # Eighteen months of paying off debts, for the chart in the README.
    Call("net_worth", "get_net_worth_trend", {"plan_id": BUDGET, "months_count": 18}, keep=18),
    # Rent, bills, groceries and transport are what a household cannot stop paying.
    Call(
        "runway",
        "get_runway",
        {"plan_id": BUDGET, "essential_groups": ["Bills", "Everyday"]},
        keep=10,
    ),
    # The car loan, 100 a month above its payment.
    Call(
        "debt_payoff",
        "get_debt_payoff_plan",
        {"plan_id": BUDGET, "monthly_budget": 500},
        keep=10,
    ),
    Call(
        "forecast",
        "forecast_balance",
        {"plan_id": BUDGET, "until": "2026-12", "monthly_income": 3200},
        6,
    ),
    Call(
        "budget_preview",
        "set_category_budget",
        {
            "plan_id": BUDGET,
            "month": "2026-09-01",
            "category_id": "cat-restaurants",
            "amount": 150,
        },
    ),
    Call(
        "move_preview",
        "move_money",
        {
            "plan_id": BUDGET,
            "month": "2026-09-01",
            "from_category_id": "cat-tennis",
            "to_category_id": "cat-restaurants",
            "amount": 30,
        },
    ),
    Call(
        "create_preview",
        "create_transactions",
        {
            "plan_id": BUDGET,
            "account_id": "acc-checking",
            "transactions": [
                {
                    "date": "2026-09-21",
                    "amount": -32.4,
                    "payee_name": "Pharmacie Centrale",
                    "memo": "not imported by the bank",
                }
            ],
        },
    ),
    Call(
        "create_category_preview",
        "create_category",
        {"plan_id": BUDGET, "category_group_id": "grp-everyday", "name": "Pets"},
    ),
    Call(
        "target_preview",
        "set_category_target",
        {"plan_id": BUDGET, "category_id": "cat-holidays", "amount": 1200, "by_date": "2027-06-01"},
    ),
    Call(
        "update_category_preview",
        "update_category",
        {"plan_id": BUDGET, "category_id": "cat-tennis", "name": "Sport"},
    ),
    # Every label the bank left for one shop: twelve payees for the same groceries.
    Call(
        "payees",
        "list_payees",
        {"plan_id": BUDGET, "search": "market fresh"},
        keep=4,
    ),
    Call(
        "rename_payee_preview",
        "rename_payee",
        {"plan_id": BUDGET, "payee_id": "pay-009", "name": "Market Fresh"},
    ),
    Call("import", "import_transactions", {"plan_id": BUDGET}),
    # The duplicate import of 19 September, flagged for the user to check in YNAB.
    Call(
        "flag_preview",
        "flag_transactions",
        {"plan_id": BUDGET, "flags": [{"transaction_id": "tx-051", "color": "orange"}]},
    ),
    Call(
        "approve",
        "approve_transactions",
        {"plan_id": BUDGET, "tx_ids": ["tx-048", "tx-049"]},
    ),
    Call(
        "undo_preview",
        "undo_operation",
        {"plan_id": BUDGET},
        after_applying=("apply_categories", _APPLY),
    ),
    Call("bad_month", "get_monthly_summary", {"plan_id": BUDGET, "month": "2026-13-01"}),
]


def _placeholders(data: Any) -> Any:
    """Replace random confirmation codes and operation ids."""
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if key == "confirmation" and value:
                out[key] = "<confirmation code>"
            elif key == "operation_id" and value:
                out[key] = "<operation id>"
            else:
                out[key] = _placeholders(value)
        return out
    if isinstance(data, list):
        return [_placeholders(item) for item in data]
    if isinstance(data, str) and "operation_id " in data:
        head, _, tail = data.partition("operation_id ")
        return head + "operation_id <operation id>" + tail[tail.find(" ") :]
    return data


def _trim(data: Any, items: int = 4) -> Any:
    """Keep the first few entries of long lists, saying how many were left out."""
    if isinstance(data, list) and len(data) > items:
        return [_trim(d, items) for d in data[:items]] + [f"… {len(data) - items} more"]
    if isinstance(data, dict):
        return {k: _trim(v, items) for k, v in data.items()}
    return data


async def _apply_first(mcp_client: Client[Any], tool: str, args: dict[str, Any]) -> None:
    """Preview then apply with the returned code, as a client without elicitation does."""
    preview = await mcp_client.call_tool(tool, args, raise_on_error=False)
    code = (preview.structured_content or {}).get("confirmation")
    await mcp_client.call_tool(tool, {**args, "confirmation": code}, raise_on_error=False)


async def _capture(language: str) -> dict[str, Capture]:
    from avenir_mcp import client, server, sync  # pylint: disable=import-outside-toplevel

    server.configure(enable_writes=True)
    # Each language replays the same calls: the demo is not YNAB's hourly allowance.
    client.PACE.reset()
    captures: dict[str, Capture] = {}
    async with Client(server.mcp) as mcp_client:
        for call in CALLS:
            args = _typed(call.args, language)
            if call.after_applying:
                await _apply_first(mcp_client, *call.after_applying)
            sync.clear()
            before = fake_ynab.STATE.requests
            result = await mcp_client.call_tool(call.tool, args, raise_on_error=False)
            requests = fake_ynab.STATE.requests - before
            if result.is_error:
                text = result.content[0].text + "\n"
            else:
                data = result.structured_content
                if isinstance(data, dict) and set(data) == {"result"}:
                    data = data["result"]
                text = json.dumps(
                    _trim(_placeholders(data), call.keep), indent=2, ensure_ascii=False
                )
                text += "\n"
            captures[call.name] = Capture(call.tool, args, text, result.is_error, requests)
    return captures


def on_demo_plan(session: Callable[[], Coroutine[Any, Any, T]], language: str = "") -> T:
    """Run a session of tool calls against a fresh demo budget, named in one language.

    The date is fixed, a fake YNAB serves the invented plan, and the journal lives in a
    temporary folder: nothing of the machine's own configuration is read or written.

    Args:
        session: Makes the coroutine that calls the tools.
        language: The language the demo budget is named in.

    Returns:
        What the session returned.
    """
    fake_ynab.STATE = fake_ynab.DemoBudget(language)
    demo = fake_ynab.serve()
    try:
        with tempfile.TemporaryDirectory() as work:
            env = {
                "YNAB_API_KEY": "demo",
                "AVENIR_MCP_YNAB_URL": f"http://127.0.0.1:{demo.server_port}/v1",
                "AVENIR_MCP_JOURNAL": str(Path(work) / "journal.jsonl"),
            }
            with patch.dict(os.environ, env), patch("avenir_mcp.app.today", lambda: TODAY):
                return asyncio.run(session())
    finally:
        demo.shutdown()
        demo.server_close()


def capture_all(language: str = "") -> dict[str, Capture]:
    """Run every documented call against a fresh demo budget, named in one language."""
    return on_demo_plan(lambda: _capture(language), language)


def generate() -> dict[str, str]:
    """Snippet name -> JSON (or error) text, for the guides."""
    return {name: c.text for name, c in capture_all().items()}
