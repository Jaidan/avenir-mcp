---
title: "set_category_budgets"
description: "Set the amounts budgeted (\"Assigned\") in several categories for a month, confirmed once."
---

:::note[Gegenereerd]
Gegenereerd uit de code door `python -m docsgen`; een test faalt zodra de pagina niet meer overeenkomt. De beschrijvingen komen uit de code en blijven in het Engels: de taal waarin agents ze lezen.
:::

## Doel

Set the amounts budgeted ("Assigned") in several categories for a month, confirmed once.

The way to fund a month: one preview, one confirmation and one undo_operation
for every category, where set_category_budget would take one each. Amounts are
absolute, in currency units, not changes. The preview lists each change before
and after; a category already at its amount is only counted (unchanged_count).
Categories are written one at a time, in the order given; if YNAB refuses one,
the rest are not written and the error names what was applied and the
operation_id that undoes it. Confirmation works as for apply_categories.

## Gedrag

| | |
|---|---|
| Soort | schrijven — verborgen zonder `AVENIR_MCP_WRITE=1` |
| Bevestiging | ja: voorbeeld, dan toegepast na akkoord van de gebruiker |
| Ongedaan maken | ja, met `undo_operation` |
| Destructief | ja |
| Idempotent | ja |

## Parameters

| Naam | Type | Verplicht | Standaard | Beschrijving |
|---|---|---|---|---|
| `plan_id` | string | ja | — | YNAB plan id or 'last-used'. |
| `month` | string | ja | — | 'YYYY-MM-01' or 'current'. |
| `budgets` | array of object | ja | — | 1 to 100 categories (from get_category_balances), each once, with its new amount in currency units. |
| `confirmation` | string \| null | nee | `null` | Code from a previous "confirmation_required" result. |

## Resultaat

| Veld | Type | Beschrijving |
|---|---|---|
| `status` | "applied" \| "confirmation_required" \| "declined" \| "nothing_to_do" | Outcome: applied, confirmation_required (nothing changed yet; pass the code back once the user agrees), declined (the user said no), or nothing_to_do. |
| `message` | string | What happened and what to do next, for the agent to relay. |
| `month` | string | Month changed, YYYY-MM-01 ('current' is resolved). |
| `changes` | array of object | The categories whose amount changes, in the order given. |
| `changes[].category_id` | string | The category. |
| `changes[].category` | string | Category name. |
| `changes[].from_amount` | number | Amount budgeted before. |
| `changes[].to_amount` | number | Amount budgeted after. |
| `unchanged_count` | integer | Categories given that already had their amount: left out of changes. |
| `confirmation` | string \| null | Single-use code confirming exactly this preview, valid 10 minutes; null unless status is confirmation_required. |
| `operation_id` | string \| null | Journal id of the applied operation, for undo_operation; null unless status is applied. |

## Fouten

- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`
- `Category {category_id} more than once: give each category one amount.`
- `Category {category_id} is not in this plan: use a category_id from get_category_balances.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

Fouten van YNAB zelf komen terug als `Error calling tool '<tool>': YNAB <status>: <detail>`.

## Zie ook

- [Categorieën ordenen](/avenir-mcp/nl/guides/categories/)
