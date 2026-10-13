# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Write the reference pages from the server itself, in every language.

One page per tool, in the manner of Ruff's rule pages: what it does, how it
behaves, its parameters, what it returns, a real example with its cost in YNAB
requests, and every error it can return. Plus an index of the tools and a
catalogue of errors. Labels are translated (labels.json); descriptions come from
the code and stay in English, the language agents read them in.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastmcp import Client

from docsgen import errors
from docsgen.examples import Capture

HERE = Path(__file__).resolve().parent
LANGUAGES = ("", "fr", "es", "de", "nl")
LABELS: dict[str, dict[str, str]] = json.loads((HERE / "labels.json").read_text(encoding="utf-8"))
GUIDE_TITLES: dict[str, dict[str, str]] = json.loads(
    (HERE / "guide_titles.json").read_text(encoding="utf-8")
)

UNDOABLE = {
    "apply_categories",
    "set_category_budget",
    "move_money",
    "reconcile_account",
    "create_transactions",
    "flag_transactions",
    "set_category_target",
    "rename_payee",
}
UNCONFIRMED_WRITES = {"import_transactions"}
# Writes whose confirmation depends on the mode: ids at once, a filter after asking.
CONFIRMED_BY_MODE = {"approve_transactions"}

# Tool -> the page that shows it at work.
GUIDES = {
    "suggest_categories": "guides/classify",
    "import_transactions": "guides/classify",
    "apply_categories": "guides/classify",
    "flag_transactions": "guides/classify",
    "list_payees": "guides/classify",
    "rename_payee": "guides/classify",
    "reconcile_account": "guides/reconcile",
    "get_monthly_summary": "guides/monthly-review",
    "get_category_balances": "guides/monthly-review",
    "get_budget_vs_actual": "guides/monthly-review",
    "get_spending_trends": "guides/monthly-review",
    "get_savings_rate": "guides/monthly-review",
    "get_age_of_money": "guides/monthly-review",
    "forecast_balance": "guides/plan-ahead",
    "find_recurring_charges": "guides/plan-ahead",
    "get_net_worth_trend": "guides/plan-ahead",
    "get_runway": "guides/plan-ahead",
    "get_debt_payoff_plan": "guides/plan-ahead",
    "set_category_budget": "guides/categories",
    "move_money": "guides/monthly-review",
    "create_transactions": "guides/missing-transactions",
    "create_category": "guides/categories",
    "update_category": "guides/categories",
    "set_category_target": "guides/categories",
    "get_underfunded_targets": "guides/categories",
    "undo_operation": "concepts/journal",
}


def link(language: str, slug: str) -> str:
    """Absolute link to a page in a language."""
    prefix = f"/avenir-mcp/{language}/" if language else "/avenir-mcp/"
    return f"{prefix}{slug}/"


def tool_link(language: str, name: str) -> str:
    """Link to a tool's reference page."""
    return link(language, f"reference/tools/{name.replace('_', '-')}")


def _type(schema: dict[str, Any], defs: dict[str, Any]) -> str:
    if "$ref" in schema:
        return _type(defs.get(schema["$ref"].split("/")[-1], {}), defs)
    if "anyOf" in schema:
        return " | ".join(_type(option, defs) for option in schema["anyOf"])
    kind = schema.get("type", "object")
    if kind == "array":
        return f"array of {_type(schema.get('items', {}), defs)}"
    if "const" in schema:
        return json.dumps(schema["const"])
    if "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    return str(kind)


def _fields(
    schema: dict[str, Any] | None, defs: dict[str, Any], prefix: str = ""
) -> list[tuple[str, str, str]]:
    """(field path, type, description) rows of an object schema, two levels deep."""
    if not schema:
        return []
    if "$ref" in schema:
        return _fields(defs.get(schema["$ref"].split("/")[-1]), defs, prefix)
    rows = []
    for name, spec in schema.get("properties", {}).items():
        path = f"{prefix}{name}"
        resolved = defs.get(spec["$ref"].split("/")[-1], {}) if "$ref" in spec else spec
        rows.append((path, _type(spec, defs), resolved.get("description", "")))
        if prefix.count(".") >= 1:
            continue
        items = resolved.get("items", {}) if resolved.get("type") == "array" else {}
        if "$ref" in items or items.get("properties"):
            rows += _fields(items, defs, f"{path}[].")
        elif resolved.get("properties"):
            rows += _fields(resolved, defs, f"{path}.")
    return rows


def _cell(text: str) -> str:
    """Text safe inside a Markdown table cell."""
    return " ".join(text.split()).replace("|", "\\|")


def _front(title: str, description: str, order: int | None = None) -> list[str]:
    lines = ["---", f"title: {json.dumps(title, ensure_ascii=False)}"]
    lines.append(f"description: {json.dumps(description, ensure_ascii=False)}")
    if order is not None:
        lines += ["sidebar:", f"  order: {order}"]
    return [*lines, "---", ""]


def _behaviour(tool: Any, label: dict[str, str], capture: Capture | None) -> list[str]:
    ann = tool.annotations
    read = ann.read_only_hint is True
    confirmed = not read and tool.name not in UNCONFIRMED_WRITES
    confirmation = label["confirm_yes"] if confirmed else label["confirm_no"]
    if tool.name in CONFIRMED_BY_MODE:
        confirmation = label["confirm_modes"]
    rows = [
        (label["kind"], label["read"] if read else label["write"]),
        (label["confirmation"], confirmation),
        (label["undo"], label["undo_yes"] if tool.name in UNDOABLE else label["undo_no"]),
    ]
    if not read:
        rows.append((label["destructive"], label["yes"] if ann.destructive_hint else label["no"]))
    rows.append((label["idempotent"], label["yes"] if ann.idempotent_hint else label["no"]))
    if capture is not None:
        rows.append((label["requests"], label["requests_value"].format(n=capture.requests)))
    return [f"## {label['behaviour']}", "", "| | |", "|---|---|"] + [
        f"| {key} | {value} |" for key, value in rows
    ]


def _parameters(tool: Any, label: dict[str, str]) -> list[str]:
    params = tool.input_schema.get("properties", {})
    defs = tool.input_schema.get("$defs", {})
    required = set(tool.input_schema.get("required", []))
    lines = [f"## {label['parameters']}", ""]
    if not params:
        return [*lines, label["none"] + "."]
    lines += [
        f"| {label['name']} | {label['type']} | {label['required']} | {label['default']} "
        f"| {label['description']} |",
        "|---|---|---|---|---|",
    ]
    for name, spec in params.items():
        default = "—" if name in required else f"`{json.dumps(spec.get('default'))}`"
        mandatory = label["yes"] if name in required else label["no"]
        lines.append(
            f"| `{name}` | {_cell(_type(spec, defs))} | {mandatory} | {default} "
            f"| {_cell(spec.get('description', ''))} |"
        )
    return lines


def _returns(tool: Any, label: dict[str, str]) -> list[str]:
    out = tool.output_schema or {}
    defs = out.get("$defs", {})
    wrapped = set(out.get("properties", {})) == {"result"} and out.get("x-fastmcp-wrap-result")
    shape = out["properties"]["result"] if wrapped else out
    listed = shape.get("type") == "array"
    rows = _fields(shape.get("items", {}) if listed else shape, defs)
    lines = [f"## {label['returns']}", ""]
    if listed or not rows:
        lines += [f"`{_type(shape, defs)}`", ""]
    if rows:
        lines += [
            f"| {label['field']} | {label['type']} | {label['description']} |",
            "|---|---|---|",
        ]
        lines += [f"| `{path}` | {_cell(kind)} | {_cell(about)} |" for path, kind, about in rows]
    return lines


def _example(label: dict[str, str], capture: Capture) -> list[str]:
    fence = "text" if capture.is_error else "json"
    return [
        f"## {label['example']}",
        "",
        label["request"],
        "",
        "```json",
        json.dumps(capture.args, indent=2, ensure_ascii=False),
        "```",
        "",
        label["response"],
        "",
        f"```{fence}",
        capture.text.rstrip(),
        "```",
    ]


def tool_page(tool: Any, language: str, capture: Capture | None, messages: list[str]) -> str:
    """One tool's reference page."""
    label = LABELS[language]
    doc = (tool.description or "").strip()
    note = label["generated"] + (f" {label['english']}" if label["english"] else "")
    lines = _front(tool.name, doc.splitlines()[0])
    lines += [f":::note[{label['generated_title']}]", note, ":::", ""]
    lines += [f"## {label['what']}", "", doc, ""]
    lines += _behaviour(tool, label, capture) + [""]
    lines += _parameters(tool, label) + [""]
    lines += _returns(tool, label) + [""]
    if capture is not None:
        lines += _example(label, capture) + [""]
    lines += [f"## {label['errors']}", ""]
    if messages:
        lines += [f"- `{_cell(m)}`" for m in messages] + ["", label["ynab_errors"]]
    else:
        lines.append(label["no_errors"])
    guide = GUIDES.get(tool.name)
    if guide:
        title = GUIDE_TITLES[language][guide]
        lines += ["", f"## {label['see_also']}", "", f"- [{title}]({link(language, guide)})"]
    return "\n".join(lines) + "\n"


def index_page(tools: list[Any], context: tuple[Any, Any, Any], language: str) -> str:
    """The list of tools, resources and prompts."""
    resources, templates, prompts = context
    label = LABELS[language]
    lines = _front(label["tools_title"], label["tools_description"], 1)
    lines += [label["tools_intro"], ""]
    for title, read in ((label["read_tools"], True), (label["write_tools"], False)):
        lines += [f"## {title}", "", f"| {label['tool']} | {label['summary']} |", "|---|---|"]
        for tool in tools:
            if (tool.annotations.read_only_hint is True) == read:
                summary = _cell((tool.description or "").strip().splitlines()[0])
                lines.append(f"| [`{tool.name}`]({tool_link(language, tool.name)}) | {summary} |")
        lines.append("")
    lines += [f"## {label['resources']}", "", f"| {label['uri']} | {label['description']} |"]
    lines += ["|---|---|"]
    lines += [f"| `{r.uri}` | {_cell(r.description or '')} |" for r in resources]
    lines += [f"| `{t.uri_template}` | {_cell(t.description or '')} |" for t in templates]
    lines += [
        "",
        f"## {label['prompts']}",
        "",
        f"| Prompt | {label['arguments']} | {label['description']} |",
    ]
    lines += ["|---|---|---|"]
    for prompt in prompts:
        args = ", ".join(
            f"`{a.name}`" + ("" if a.required else f" ({label['optional']})")
            for a in prompt.arguments or []
        )
        lines.append(f"| `{prompt.name}` | {args} | {_cell(prompt.description or '')} |")
    return "\n".join(lines) + "\n"


def errors_page(tools: list[Any], messages: dict[str, list[str]], language: str) -> str:
    """Every error message, tool by tool."""
    label = LABELS[language]
    lines = _front(label["errors_title"], label["errors_description"], 2)
    lines += [label["errors_intro"], "", f"## {label['general']}", "", label["general_text"], ""]
    for tool in tools:
        if messages.get(tool.name):
            lines += [f"## [`{tool.name}`]({tool_link(language, tool.name)})", ""]
            lines += [f"- `{_cell(m)}`" for m in messages[tool.name]] + [""]
    return "\n".join(lines)


async def _server_view() -> tuple[list[Any], tuple[Any, Any, Any]]:
    from avenir_mcp import server  # pylint: disable=import-outside-toplevel

    server.configure(enable_writes=True)
    async with Client(server.mcp) as mcp_client:
        tools = sorted(
            await mcp_client.list_tools(),
            key=lambda t: (t.annotations.read_only_hint is False, t.name),
        )
        context = (
            await mcp_client.list_resources(),
            await mcp_client.list_resource_templates(),
            await mcp_client.list_prompts(),
        )
    return tools, context


def generate(captures: dict[str, dict[str, Capture]]) -> dict[str, str]:
    """Relative path under the content folder -> page, for every language.

    Args:
        captures: Each language's captures, on the demo budget named in that language.
    """
    tools, context = asyncio.run(_server_view())
    messages = errors.tool_errors()
    pages: dict[str, str] = {}
    for language in LANGUAGES:
        by_tool: dict[str, Capture] = {}
        for capture in captures[language].values():
            if not capture.is_error:
                by_tool.setdefault(capture.tool, capture)
        base = f"{language}/reference" if language else "reference"
        pages[f"{base}/tools/index.md"] = index_page(tools, context, language)
        pages[f"{base}/errors.md"] = errors_page(tools, messages, language)
        for tool in tools:
            pages[f"{base}/tools/{tool.name.replace('_', '-')}.md"] = tool_page(
                tool, language, by_tool.get(tool.name), messages.get(tool.name, [])
            )
    return pages
