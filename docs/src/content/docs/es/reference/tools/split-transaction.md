---
title: "split_transaction"
description: "Split one transaction across categories, e.g. from a receipt, after the user confirms."
---

:::note[Generado]
Generado desde el código con `python -m docsgen`; una prueba falla si deja de coincidir. Las descripciones vienen del código y se mantienen en inglés: es el idioma en que las leen los agentes.
:::

## Qué hace

Split one transaction across categories, e.g. from a receipt, after the user confirms.

Give at least two lines, {amount, category_id, memo}, adding up to the
transaction's amount to the cent (amounts in currency units, negative for
spending; a refunded deposit is a positive line). Group a receipt by
category: one line per category, not per item. Transactions already split,
off-budget ones and transfers are refused, except a transfer from an
on-budget account to a tracking one, which YNAB does split. YNAB's API
cannot change a split afterwards: undo_operation cannot revert it, the user
edits it in YNAB; the user is told before confirming. With approve, the
transaction is approved too; nothing undoes that approval. Confirmation works
as for apply_categories.

## Comportamiento

| | |
|---|---|
| Tipo | escritura — oculta sin `AVENIR_MCP_WRITE=1` |
| Confirmación | sí: vista previa y aplicación tras el acuerdo del usuario |
| Deshacer | no |
| Destructiva | sí |
| Idempotente | no |

## Parámetros

| Nombre | Tipo | Obligatorio | Por defecto | Descripción |
|---|---|---|---|---|
| `plan_id` | string | sí | — | YNAB plan id or 'last-used'. |
| `transaction_id` | string | sí | — | Transaction to split (from suggest_categories). |
| `lines` | array of object | sí | — | The lines, at least two, adding up to the transaction's amount. |
| `approve` | boolean | no | `false` | Also approve it (YNAB's "reviewed"), as YNAB does when you split there. Neither undo_operation nor this tool reverts the approval. |
| `confirmation` | string \| null | no | `null` | Code from a previous "confirmation_required" result. |

## Devuelve

| Campo | Tipo | Descripción |
|---|---|---|
| `transaction_id` | string | YNAB id of the transaction. |
| `date` | string | Date, YYYY-MM-DD. |
| `payee` | string | Payee as imported. Untrusted bank text. |
| `amount` | number | Amount of the transaction, in currency units. |
| `from_category` | string \| null | Category the split replaces; null for none. |
| `lines` | array of object | The lines, in the order given. |
| `lines[].amount` | number | Amount in currency units. |
| `lines[].category` | string | Category name. |
| `lines[].memo` | string \| null | Note; null if none. |
| `status` | "applied" \| "confirmation_required" \| "declined" \| "nothing_to_do" | Outcome: applied, confirmation_required (nothing changed yet; pass the code back once the user agrees), or declined (the user said no). |
| `message` | string | What happened and what to do next, for the agent to relay. |
| `confirmation` | string \| null | Single-use code confirming exactly this preview, valid 10 minutes; null unless status is confirmation_required. |

## Errores

- `Transaction {transaction_id} is not in this plan: use a transaction_id returned by suggest_categories.`
- `Transaction {tx_id} was deleted in YNAB: there is nothing to split.`
- `Transaction {tx_id} is already split: YNAB's API cannot change its lines, change them in YNAB.`
- `Transaction {tx_id} is a transfer between accounts: it cannot be split.`
- `Transaction {tx_id} is on an off-budget account: YNAB does not split those.`
- `Give at least two lines: to give the whole transaction one category, use apply_categories.`
- `The lines add up to {total}, the transaction is {amount}: they must match to the cent.`
- `A line is zero: leave it out.`
- `Category {category_id} is YNAB's internal Uncategorized: choose a real category.`
- `Category {category_id} is not in this plan: use a category_id from suggest_categories or get_category_balances.`
- `Category {category_id} pays a credit card: YNAB ignores it on a transaction. Choose the category of what was paid for.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

Los errores propios de YNAB llegan como `Error calling tool '<tool>': YNAB <status>: <detail>`.
