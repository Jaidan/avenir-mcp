# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Change categories: create, rename or move one, set the amount budgeted for a month."""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastmcp import Context
from fastmcp.exceptions import ToolError
from mcp.types import InputRequiredResult
from pydantic import Field

from avenir_mcp import app, client, journal, retry
from avenir_mcp.amounts import Amount
from avenir_mcp.app import WRITE_TAG, check_month, mcp
from avenir_mcp.confirm import WriteStatus, gate, merged, rows_question
from avenir_mcp.model import Model
from avenir_mcp.text import one_line, untrusted

logger = logging.getLogger(__name__)


class CategoryUpdate(Model):
    """The outcome of update_category."""

    status: WriteStatus
    """Outcome: applied, confirmation_required (nothing changed yet; pass the code back once the
    user agrees), declined (the user said no), or nothing_to_do.
    """
    message: str
    """What happened and what to do next, for the agent to relay."""
    category_id: str
    """The category changed."""
    from_name: str
    """Name before."""
    to_name: str
    """Name after."""
    from_group: str
    """Group before."""
    to_group: str
    """Group after."""
    confirmation: str | None
    """Single-use code confirming exactly this preview, valid 10 minutes; null unless status is
    confirmation_required.
    """


def _check_name(name: str) -> None:
    """Refuse a category name the user could not read on one line.

    Args:
        name: The name the agent gave, stripped.

    Raises:
        ToolError: If it holds a line break, a control or a format character.
    """
    try:
        one_line(name)
    except ValueError as error:
        raise ToolError(str(error)) from error


@mcp.tool(
    tags={WRITE_TAG},
    annotations={
        "title": "Rename or move a category",
        "read_only_hint": False,
        "destructive_hint": True,
        "idempotent_hint": True,
        "open_world_hint": True,
    },
)
async def update_category(  # pylint: disable=too-many-arguments
    plan_id: str,
    category_id: str,
    ctx: Context,
    *,
    name: str | None = None,
    category_group_id: str | None = None,
    confirmation: str | None = None,
) -> CategoryUpdate | InputRequiredResult:
    """Rename a category and/or move it to another group, after the user confirms.

    Transactions and amounts stay attached to the category. Confirmation works as
    for apply_categories. To revert, call again with the previous name and group,
    which the result gives.

    Args:
        plan_id: YNAB plan id or 'last-used'.
        category_id: Category to change (from suggest_categories or list_category_groups).
        ctx: The MCP context, used to ask the user.
        name: New name; omit to keep it.
        category_group_id: Group to move it to (from list_category_groups); omit to keep it.
        confirmation: Code from a previous "confirmation_required" result.

    Returns:
        The names and groups before and after, or an input request the client answers by asking the
        user (protocol 2026-07-28).

    Raises:
        ToolError: If the category or group is not in the plan, the new name is empty or
            not on one line of visible characters, or the confirmation code is refused.
    """
    logger.info("Tool called: update_category")
    categories = {c["id"]: c for c in await client.get_categories(plan_id)}
    groups = {g["id"]: g["name"] for g in await client.get_category_groups(plan_id)}
    category = categories.get(category_id)
    if category is None:
        raise ToolError(
            f"Category {category_id} is not in this plan: "
            "use a category_id from suggest_categories."
        )
    if category_group_id is not None and category_group_id not in groups:
        raise ToolError(
            f"Group {category_group_id} is not in this plan: use an id from list_category_groups."
        )
    if name is not None and not name.strip():
        raise ToolError("The new name is empty: give a name, or omit it to keep the current one.")
    new_name = name.strip() if name is not None else category["name"]
    if name is not None:
        _check_name(new_name)
    new_group = category_group_id or category["category_group_id"]
    result = CategoryUpdate(
        status="nothing_to_do",
        message="Nothing to change.",
        category_id=category_id,
        from_name=untrusted(category["name"]),
        to_name=untrusted(new_name),
        from_group=untrusted(category.get("category_group_name", "")),
        to_group=untrusted(groups.get(new_group, "")),
        confirmation=None,
    )
    if new_name == category["name"] and new_group == category["category_group_id"]:
        return result
    subject = {"category_id": category_id, "name": new_name, "group": new_group}
    question = (
        f"Change category '{result.from_name}' ({result.from_group}) "
        f"to '{result.to_name}' ({result.to_group})?"
    )
    stop = await gate(ctx, plan_id, subject, question, confirmation, undoable=False)
    if stop is not None:
        return stop if isinstance(stop, InputRequiredResult) else merged(result, stop)
    await client.update_category(
        plan_id,
        category_id,
        name=new_name if new_name != category["name"] else None,
        category_group_id=new_group if new_group != category["category_group_id"] else None,
    )
    return result.model_copy(
        update={
            "status": "applied",
            "message": "Applied. To revert, call update_category with the previous name and group.",
        }
    )


class BudgetChange(Model):
    """The outcome of set_category_budget."""

    status: WriteStatus
    """Outcome: applied, confirmation_required (nothing changed yet; pass the code back once the
    user agrees), declined (the user said no), or nothing_to_do.
    """
    message: str
    """What happened and what to do next, for the agent to relay."""
    category_id: str
    """The category changed."""
    category: str
    """Category name."""
    month: str
    """Month changed, YYYY-MM-01 ('current' is resolved)."""
    from_amount: float
    """Amount budgeted before."""
    to_amount: float
    """Amount budgeted after."""
    confirmation: str | None
    """Single-use code confirming exactly this preview, valid 10 minutes; null unless status is
    confirmation_required.
    """
    operation_id: str | None
    """Journal id of the applied operation, for undo_operation; null unless status is applied."""


@mcp.tool(
    tags={WRITE_TAG},
    annotations={
        "title": "Set a category's budgeted amount",
        "read_only_hint": False,
        "destructive_hint": True,
        "idempotent_hint": True,
        "open_world_hint": True,
    },
)
async def set_category_budget(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    plan_id: str,
    month: str,
    category_id: str,
    amount: Amount,
    ctx: Context,
    confirmation: str | None = None,
) -> BudgetChange | InputRequiredResult:
    """Set the amount budgeted ("Assigned") in a category for a month, after the user confirms.

    The amount is absolute, in currency units, not a change. The result gives the
    amount before and after; undo_operation restores the previous one. For more than
    one category, use set_category_budgets: one confirmation for all of them.
    Confirmation works as for apply_categories.

    Args:
        plan_id: YNAB plan id or 'last-used'.
        month: 'YYYY-MM-01' or 'current'.
        category_id: Category (from get_category_balances or suggest_categories).
        amount: New budgeted amount, in currency units.
        ctx: The MCP context, used to ask the user.
        confirmation: Code from a previous "confirmation_required" result.

    Returns:
        The amounts before and after, or an input request the client answers by asking the user
        (protocol 2026-07-28).

    Raises:
        ToolError: If the month is malformed, the category is not in the plan, or the
            confirmation code is refused.
    """
    logger.info("Tool called: set_category_budget(month=%r)", month)
    check_month(month)
    month = app.resolve_month(month)
    categories = {c["id"]: c for c in await client.get_month_categories(plan_id, month)}
    category = _category(categories, category_id)
    before, after = category["budgeted"], client.amount_to_milliunit(amount)
    result = BudgetChange(
        status="nothing_to_do",
        message="Nothing to change.",
        category_id=category_id,
        category=untrusted(category["name"]),
        month=month,
        from_amount=client.milliunit_to_amount(before),
        to_amount=client.milliunit_to_amount(after),
        confirmation=None,
        operation_id=None,
    )
    if before == after:
        return result
    question = (
        f"Budget {result.category} for {month}: {result.from_amount:.2f} → {result.to_amount:.2f}?"
    )
    subject = {"category": category_id, "month": month, "amount": after}
    stop = await gate(ctx, plan_id, subject, question, confirmation, undoable=True)
    if stop is not None:
        return stop if isinstance(stop, InputRequiredResult) else merged(result, stop)
    await client.set_category_budgeted(plan_id, month, category_id, amount)
    operation_id = journal.Journal(journal.default_path()).record(
        plan_id,
        "budget",
        [],
        {"month": month, "category_id": category_id, "from": before, "to": after},
    )
    return result.model_copy(
        update={
            "status": "applied",
            "message": f"Applied. undo_operation with operation_id {operation_id} reverts it.",
            "operation_id": operation_id,
        }
    )


class BudgetItem(Model):
    """A category's new budgeted amount."""

    category_id: str
    """Category (from get_category_balances)."""
    amount: Amount
    """New budgeted amount, in currency units: absolute, not a change."""


class BudgetLine(Model):
    """One category of set_category_budgets: its amount budgeted before and after."""

    category_id: str
    """The category."""
    category: str
    """Category name."""
    from_amount: float
    """Amount budgeted before."""
    to_amount: float
    """Amount budgeted after."""


class BudgetChanges(Model):
    """The outcome of set_category_budgets."""

    status: WriteStatus
    """Outcome: applied, confirmation_required (nothing changed yet; pass the code back once the
    user agrees), declined (the user said no), or nothing_to_do.
    """
    message: str
    """What happened and what to do next, for the agent to relay."""
    month: str
    """Month changed, YYYY-MM-01 ('current' is resolved)."""
    changes: list[BudgetLine]
    """The categories whose amount changes, in the order given."""
    unchanged_count: int
    """Categories given that already had their amount: left out of changes."""
    confirmation: str | None
    """Single-use code confirming exactly this preview, valid 10 minutes; null unless status is
    confirmation_required.
    """
    operation_id: str | None
    """Journal id of the applied operation, for undo_operation; null unless status is applied."""


def _category(categories: dict[str, dict[str, Any]], category_id: str) -> dict[str, Any]:
    """Find a category of the month, or say where to find a valid id.

    Args:
        categories: The month's categories by id, as YNAB returns them.
        category_id: The category the agent gave.

    Returns:
        The category, as YNAB returns it.

    Raises:
        ToolError: If it is not in the plan.
    """
    category = categories.get(category_id)
    if category is None:
        raise ToolError(
            f"Category {category_id} is not in this plan: "
            "use a category_id from get_category_balances."
        )
    return category


def _budget_lines(
    categories: dict[str, dict[str, Any]], budgets: list[BudgetItem]
) -> tuple[list[BudgetLine], list[dict[str, Any]]]:
    """Check the categories given and keep those whose amount changes.

    Args:
        categories: The month's categories by id, as YNAB returns them.
        budgets: The new amounts, in the order given.

    Returns:
        A line per category whose amount changes, in the order given, and the same
        changes in milliunits as the journal keeps them.

    Raises:
        ToolError: If a category is given twice or is not in the plan.
    """
    seen: set[str] = set()
    lines = []
    changes = []
    for item in budgets:
        if item.category_id in seen:
            raise ToolError(
                f"Category {item.category_id} more than once: give each category one amount."
            )
        seen.add(item.category_id)
        category = _category(categories, item.category_id)
        before, after = category["budgeted"], client.amount_to_milliunit(item.amount)
        if before != after:
            lines.append(
                BudgetLine(
                    category_id=item.category_id,
                    category=untrusted(category["name"]),
                    from_amount=client.milliunit_to_amount(before),
                    to_amount=client.milliunit_to_amount(after),
                )
            )
            changes.append({"category_id": item.category_id, "from": before, "to": after})
    return lines, changes


def _journal_budgets(plan_id: str, month: str, applied: list[dict[str, Any]]) -> str:
    """Record the categories set as one operation, for undo_operation.

    Args:
        plan_id: YNAB plan id or 'last-used'.
        month: The month, YYYY-MM-01.
        applied: The changes YNAB accepted, in milliunits.

    Returns:
        The journal id of the operation.
    """
    return journal.Journal(journal.default_path()).record(
        plan_id, "budgets", [], {"month": month, "changes": applied}
    )


def _stopped(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    plan_id: str,
    month: str,
    lines: list[BudgetLine],
    changes: list[dict[str, Any]],
    failed: int,
    error: Exception,
) -> str:
    """Journal what was applied before a failed write, and say what was and was not.

    A write YNAB refused was not applied; one it never answered may have been, and
    the user is told to check it.

    Args:
        plan_id: YNAB plan id or 'last-used'.
        month: The month, YYYY-MM-01.
        lines: Every change, in the order written.
        changes: The same changes, in milliunits.
        failed: Index of the change YNAB refused or never answered.
        error: What YNAB answered.

    Returns:
        The error message, naming what was applied, what was not, and the operation_id
        that undoes the applied part.
    """
    category = lines[failed].category
    if isinstance(error, retry.YnabUnavailable):
        parts = [f"{category} may have been applied: check it in YNAB ({error})."]
        left = lines[failed + 1 :]
        nothing = "Nothing else was changed."
    else:
        parts = [f"YNAB refused to change {category} ({error})."]
        left = lines[failed:]
        nothing = "Nothing was changed."
    if failed:
        operation_id = _journal_budgets(plan_id, month, changes[:failed])
        parts.append(f"Applied: {', '.join(line.category for line in lines[:failed])}.")
    else:
        parts.append(nothing)
    if left:
        parts.append(f"Not applied: {', '.join(line.category for line in left)}.")
    if failed:
        parts.append(f"undo_operation with operation_id {operation_id} reverts the applied part.")
    return " ".join(parts)


async def _set_each(
    plan_id: str, month: str, lines: list[BudgetLine], changes: list[dict[str, Any]]
) -> str:
    """Set each category in turn, then journal them as one operation.

    Args:
        plan_id: YNAB plan id or 'last-used'.
        month: The month, YYYY-MM-01.
        lines: The changes, in the order to write them.
        changes: The same changes, in milliunits, for the journal.

    Returns:
        The journal id of the operation.

    Raises:
        ToolError: If YNAB refused a write or answered nothing: the categories before it
            stay applied and journaled, the error names them and the operation_id.
    """
    for index, line in enumerate(lines):
        try:
            await client.set_category_budgeted(plan_id, month, line.category_id, line.to_amount)
        except RuntimeError as error:
            raise ToolError(_stopped(plan_id, month, lines, changes, index, error)) from error
    return _journal_budgets(plan_id, month, changes)


@mcp.tool(
    tags={WRITE_TAG},
    annotations={
        "title": "Set several categories' budgeted amounts",
        "read_only_hint": False,
        "destructive_hint": True,
        "idempotent_hint": True,
        "open_world_hint": True,
    },
)
async def set_category_budgets(
    plan_id: str,
    month: str,
    budgets: Annotated[list[BudgetItem], Field(min_length=1, max_length=100)],
    ctx: Context,
    confirmation: str | None = None,
) -> BudgetChanges | InputRequiredResult:
    """Set the amounts budgeted ("Assigned") in several categories for a month, confirmed once.

    The way to fund a month: one preview, one confirmation and one undo_operation
    for every category, where set_category_budget would take one each. Amounts are
    absolute, in currency units, not changes. The preview lists each change before
    and after; a category already at its amount is only counted (unchanged_count).
    Categories are written one at a time, in the order given; if YNAB refuses one,
    the rest are not written and the error names what was applied and the
    operation_id that undoes it. Confirmation works as for apply_categories.

    Args:
        plan_id: YNAB plan id or 'last-used'.
        month: 'YYYY-MM-01' or 'current'.
        budgets: 1 to 100 categories (from get_category_balances), each once, with its new
            amount in currency units.
        ctx: The MCP context, used to ask the user.
        confirmation: Code from a previous "confirmation_required" result.

    Returns:
        Each change before and after, or an input request the client answers by asking the user
        (protocol 2026-07-28).

    Raises:
        ToolError: If the month is malformed, a category is not in the plan or given twice,
            YNAB refuses a change, or the confirmation code is refused.
    """
    logger.info("Tool called: set_category_budgets(month=%r, count=%d)", month, len(budgets))
    check_month(month)
    month = app.resolve_month(month)
    categories = {c["id"]: c for c in await client.get_month_categories(plan_id, month)}
    lines, changes = _budget_lines(categories, budgets)
    result = BudgetChanges(
        status="nothing_to_do",
        message="Nothing to change.",
        month=month,
        changes=lines,
        unchanged_count=len(budgets) - len(lines),
        confirmation=None,
        operation_id=None,
    )
    if not lines:
        return result
    question = rows_question(
        "Budget",
        [f"{line.category}: {line.from_amount:.2f} → {line.to_amount:.2f}" for line in lines],
        f"categories for {month}",
    )
    subject = {
        "month": month,
        "budgets": sorted((change["category_id"], change["to"]) for change in changes),
    }
    stop = await gate(ctx, plan_id, subject, question, confirmation, undoable=True)
    if stop is not None:
        return stop if isinstance(stop, InputRequiredResult) else merged(result, stop)
    operation_id = await _set_each(plan_id, month, lines, changes)
    return result.model_copy(
        update={
            "status": "applied",
            "message": f"Applied. undo_operation with operation_id {operation_id} reverts it.",
            "operation_id": operation_id,
        }
    )


class CategoryMove(Model):
    """One side of a move: a category's amount budgeted before and after."""

    category_id: str
    """The category."""
    name: str
    """Category name."""
    from_amount: float
    """Amount budgeted before."""
    to_amount: float
    """Amount budgeted after."""
    available_after: float
    """Amount available in the category once the move is applied; negative means overspent."""


class MoneyMove(Model):
    """The outcome of move_money."""

    status: WriteStatus
    """Outcome: applied, confirmation_required (nothing changed yet; pass the code back once the
    user agrees), or declined (the user said no).
    """
    message: str
    """What happened and what to do next, for the agent to relay."""
    month: str
    """Month changed, YYYY-MM-01 ('current' is resolved)."""
    amount: float
    """Amount moved, in currency units."""
    from_category: CategoryMove
    """The category the money is taken from."""
    to_category: CategoryMove
    """The category the money goes to."""
    confirmation: str | None
    """Single-use code confirming exactly this preview, valid 10 minutes; null unless status is
    confirmation_required.
    """
    operation_id: str | None
    """Journal id of the applied operation, for undo_operation; null unless status is applied."""


def _side(category: dict[str, Any], change: int) -> CategoryMove:
    """Describe one category of a move.

    Args:
        category: The month category, as YNAB returns it, in milliunits.
        change: Milliunits added to its budgeted amount (negative when taken).

    Returns:
        Its name and amounts before and after, in currency units.
    """
    return CategoryMove(
        category_id=category["id"],
        name=untrusted(category["name"]),
        from_amount=client.milliunit_to_amount(category["budgeted"]),
        to_amount=client.milliunit_to_amount(category["budgeted"] + change),
        available_after=client.milliunit_to_amount(category["balance"] + change),
    )


async def _set_both(plan_id: str, month: str, source: CategoryMove, target: CategoryMove) -> None:
    """Take from the source, then give to the target; if the second write fails, undo the first.

    `retry.YnabUnavailable` is a RuntimeError, so a second write that YNAB never
    answered puts the source back as a refusal does: the error carries what to check.

    Args:
        plan_id: YNAB plan id or 'last-used'.
        month: The month, YYYY-MM-01.
        source: The category the money is taken from.
        target: The category the money goes to.

    Raises:
        ToolError: If YNAB refused the target or answered nothing, saying whether the
            source was put back.
    """
    await client.set_category_budgeted(plan_id, month, source.category_id, source.to_amount)
    try:
        await client.set_category_budgeted(plan_id, month, target.category_id, target.to_amount)
    except RuntimeError as error:
        refused = f"YNAB refused to change {target.name} ({error})"
        try:
            await client.set_category_budgeted(
                plan_id, month, source.category_id, source.from_amount
            )
        except RuntimeError as again:
            raise ToolError(
                f"{refused}, then putting {source.name} back failed too ({again}): "
                f"set {source.name} back to {source.from_amount:.2f} in YNAB."
            ) from again
        raise ToolError(
            f"{refused}; {source.name} is back to {source.from_amount:.2f}: nothing was moved."
        ) from error


@mcp.tool(
    tags={WRITE_TAG},
    annotations={
        "title": "Move money between categories",
        "read_only_hint": False,
        "destructive_hint": True,
        "idempotent_hint": False,
        "open_world_hint": True,
    },
)
async def move_money(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals
    plan_id: str,
    month: str,
    from_category_id: str,
    to_category_id: str,
    amount: Annotated[
        Amount, Field(gt=0, description="How much to move, in currency units, greater than 0.")
    ],
    ctx: Context,
    confirmation: str | None = None,
) -> MoneyMove | InputRequiredResult:
    """Move money budgeted in one category to another for a month, after the user confirms.

    The way to cover overspending: one preview, one confirmation and one
    undo_operation for both categories, where set_category_budget would take two.
    The amount is what moves, in currency units, not a new total. The result gives
    both categories before and after, and what each will have available.
    Confirmation works as for apply_categories.

    Args:
        plan_id: YNAB plan id or 'last-used'.
        month: 'YYYY-MM-01' or 'current'.
        from_category_id: Category the money is taken from (from get_category_balances).
        to_category_id: Category the money goes to (from get_category_balances).
        amount: How much to move, in currency units, greater than 0.
        ctx: The MCP context, used to ask the user.
        confirmation: Code from a previous "confirmation_required" result.

    Returns:
        Both categories before and after, or an input request the client answers by asking the
        user (protocol 2026-07-28).

    Raises:
        ToolError: If the month is malformed, a category is not in the plan, both are the same,
            YNAB refuses the change, or the confirmation code is refused.
    """
    logger.info("Tool called: move_money(month=%r)", month)
    check_month(month)
    month = app.resolve_month(month)
    if from_category_id == to_category_id:
        raise ToolError("Give two different categories: money moves from one to another.")
    categories = {c["id"]: c for c in await client.get_month_categories(plan_id, month)}
    for category_id in (from_category_id, to_category_id):
        _category(categories, category_id)
    moved = client.amount_to_milliunit(amount)
    source = _side(categories[from_category_id], -moved)
    target = _side(categories[to_category_id], moved)
    result = MoneyMove(
        status="applied",
        message="",
        month=month,
        amount=client.milliunit_to_amount(moved),
        from_category=source,
        to_category=target,
        confirmation=None,
        operation_id=None,
    )
    question = (
        f"Move {result.amount:.2f} from {source.name} to {target.name} for {month}?\n"
        f"- {source.name}: {source.from_amount:.2f} → {source.to_amount:.2f}\n"
        f"- {target.name}: {target.from_amount:.2f} → {target.to_amount:.2f}"
    )
    subject = {"from": from_category_id, "to": to_category_id, "month": month, "amount": moved}
    stop = await gate(ctx, plan_id, subject, question, confirmation, undoable=True)
    if stop is not None:
        return stop if isinstance(stop, InputRequiredResult) else merged(result, stop)
    await _set_both(plan_id, month, source, target)
    operation_id = journal.Journal(journal.default_path()).record(
        plan_id,
        "move",
        [],
        {
            "month": month,
            "changes": [
                {
                    "category_id": side.category_id,
                    "from": categories[side.category_id]["budgeted"],
                    "to": client.amount_to_milliunit(side.to_amount),
                }
                for side in (source, target)
            ],
        },
    )
    return result.model_copy(
        update={
            "message": f"Moved. undo_operation with operation_id {operation_id} moves it back.",
            "operation_id": operation_id,
        }
    )


class NewCategory(Model):
    """The outcome of create_category."""

    status: WriteStatus
    """Outcome: applied, confirmation_required (nothing changed yet; pass the code back once the
    user agrees), declined (the user said no), or nothing_to_do.
    """
    message: str
    """What happened and what to do next, for the agent to relay."""
    name: str
    """Name of the new category, trimmed."""
    group: str
    """Group it goes in."""
    category_id: str | None
    """YNAB id of the new category; null until applied."""
    confirmation: str | None
    """Single-use code confirming exactly this preview, valid 10 minutes; null unless status is
    confirmation_required.
    """


@mcp.tool(
    tags={WRITE_TAG},
    annotations={
        "title": "Create a category",
        "read_only_hint": False,
        "destructive_hint": False,
        "idempotent_hint": False,
        "open_world_hint": True,
    },
)
async def create_category(
    plan_id: str,
    category_group_id: str,
    name: str,
    ctx: Context,
    confirmation: str | None = None,
) -> NewCategory | InputRequiredResult:
    """Create a category in a group, after the user confirms.

    YNAB's API cannot delete a category: to undo, hide it in YNAB. A name already
    used in the group is refused. Confirmation works as for apply_categories.

    Args:
        plan_id: YNAB plan id or 'last-used'.
        category_group_id: Group to create it in (from list_category_groups).
        name: Name of the new category.
        ctx: The MCP context, used to ask the user.
        confirmation: Code from a previous "confirmation_required" result.

    Returns:
        The new category's name, group and id, or an input request the client answers by asking the
        user (protocol 2026-07-28).

    Raises:
        ToolError: If the group is not in the plan, the name is empty, not on one line of
            visible characters or already used in the group, or the confirmation code is
            refused.
    """
    logger.info("Tool called: create_category")
    groups = {g["id"]: g["name"] for g in await client.get_category_groups(plan_id)}
    if category_group_id not in groups:
        raise ToolError(
            f"Group {category_group_id} is not in this plan: use an id from list_category_groups."
        )
    new_name = name.strip()
    if not new_name:
        raise ToolError("The name is empty: give the new category a name.")
    _check_name(new_name)
    taken = {
        c["name"].casefold()
        for c in await client.get_categories(plan_id)
        if c.get("category_group_id") == category_group_id
    }
    if new_name.casefold() in taken:
        raise ToolError(f"{new_name!r} already exists in {groups[category_group_id]}.")
    result = NewCategory(
        status="applied",
        message="",
        name=new_name,
        group=untrusted(groups[category_group_id]),
        category_id=None,
        confirmation=None,
    )
    question = f"Create category '{result.name}' in {result.group}?"
    subject = {"group": category_group_id, "name": new_name}
    stop = await gate(ctx, plan_id, subject, question, confirmation, undoable=False)
    if stop is not None:
        return stop if isinstance(stop, InputRequiredResult) else merged(result, stop)
    created = await client.create_category(plan_id, category_group_id, new_name)
    return result.model_copy(update={"message": "Created.", "category_id": created["id"]})
