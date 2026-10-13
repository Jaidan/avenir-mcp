---
title: "set_category_budgets"
description: "Set the amounts budgeted (\"Assigned\") in several categories for a month, confirmed once."
---

:::note[Généré]
Généré depuis le code par `python -m docsgen` ; un test échoue s'il ne correspond plus. Les descriptions viennent du code et restent en anglais : c'est la langue dans laquelle les agents les lisent.
:::

## Rôle

Set the amounts budgeted ("Assigned") in several categories for a month, confirmed once.

The way to fund a month: one preview, one confirmation and one undo_operation
for every category, where set_category_budget would take one each. Amounts are
absolute, in currency units, not changes. The preview lists each change before
and after; a category already at its amount is only counted (unchanged_count).
Categories are written one at a time, in the order given; if YNAB refuses one,
the rest are not written and the error names what was applied and the
operation_id that undoes it. Confirmation works as for apply_categories.

## Comportement

| | |
|---|---|
| Nature | écriture — masqué sans `AVENIR_MCP_WRITE=1` |
| Confirmation | oui : aperçu, puis application après accord de l'utilisateur |
| Annulation | oui, avec `undo_operation` |
| Destructif | oui |
| Idempotent | oui |

## Paramètres

| Nom | Type | Obligatoire | Défaut | Description |
|---|---|---|---|---|
| `plan_id` | string | oui | — | YNAB plan id or 'last-used'. |
| `month` | string | oui | — | 'YYYY-MM-01' or 'current'. |
| `budgets` | array of object | oui | — | 1 to 100 categories (from get_category_balances), each once, with its new amount in currency units. |
| `confirmation` | string \| null | non | `null` | Code from a previous "confirmation_required" result. |

## Retour

| Champ | Type | Description |
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

## Erreurs

- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`
- `Category {category_id} more than once: give each category one amount.`
- `Category {category_id} is not in this plan: use a category_id from get_category_balances.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

Les erreurs propres à YNAB reviennent sous la forme `Error calling tool '<tool>': YNAB <status>: <detail>`.

## Voir aussi

- [Organiser les catégories](/avenir-mcp/fr/guides/categories/)
