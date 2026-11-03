---
title: "reconcile_account"
description: "Compare an account with the balance your bank shows, then reconcile it."
---

:::note[Gegenereerd]
Gegenereerd uit de code door `python -m docsgen`; een test faalt zodra de pagina niet meer overeenkomt. De beschrijvingen komen uit de code en blijven in het Engels: de taal waarin agents ze lezen.
:::

## Doel

Compare an account with the balance your bank shows, then reconcile it.

Give the balance shown by the bank today (currency units). If YNAB's cleared
balance differs, nothing is written: the result explains the gap with the
pending transactions, the one whose amount matches the difference
(`explained_by`) and likely duplicates. Fix those first (with the user), then
call again. Only if the user wants to accept the remaining gap, call with
adjust=true: a "Balance adjustment" transaction is added to Ready to Assign.
When balances match, every cleared transaction is marked reconciled after the
user confirms (as for apply_categories). undo_operation reverts it. If the
account's transactions do not add up to the cleared balance YNAB shows, even
after reading both again, nothing is asked or written (totals_disagree): call
again in a minute, or ask the user to look in YNAB for an import matched to, or
recently deleted from, the account.

## Gedrag

| | |
|---|---|
| Soort | schrijven — verborgen zonder `AVENIR_MCP_WRITE=1` |
| Bevestiging | ja: voorbeeld, dan toegepast na akkoord van de gebruiker |
| Ongedaan maken | ja, met `undo_operation` |
| Destructief | ja |
| Idempotent | nee |
| YNAB-verzoeken | 2 voor het voorbeeld hieronder, lege cache |

## Parameters

| Naam | Type | Verplicht | Standaard | Beschrijving |
|---|---|---|---|---|
| `plan_id` | string | ja | — | YNAB plan id or 'last-used'. |
| `account_id` | string | ja | — | Account to reconcile (from list_accounts). |
| `bank_balance` | number | ja | — | In currency units, negative for money out; at most a billion either way. |
| `adjust` | boolean | nee | `false` | Record the remaining difference as an adjustment. |
| `confirmation` | string \| null | nee | `null` | Code from a previous "confirmation_required" result. |

## Resultaat

| Veld | Type | Beschrijving |
|---|---|---|
| `status` | "applied" \| "confirmation_required" \| "declined" \| "nothing_to_do" \| "difference_found" \| "totals_disagree" | Outcome: difference_found (nothing changed; see analysis), confirmation_required, applied, declined, nothing_to_do (already reconciled), or totals_disagree (nothing changed: the transactions avenir-mcp reads do not add up to YNAB's own cleared balance). |
| `message` | string | What happened and what to do next, for the agent to relay. |
| `account` | string | Account name. |
| `analysis` | object | The comparison with the bank. |
| `analysis.account_id` | string | The account analysed. |
| `analysis.bank_balance` | number | Balance the bank shows, as given. |
| `analysis.cleared_balance` | number | Sum of the account's cleared and reconciled transactions in YNAB. |
| `analysis.ynab_cleared_balance` | number \| null | Cleared balance YNAB itself shows for the account; null when not checked. It equals cleared_balance unless avenir-mcp's copy of the transactions is out of date. |
| `analysis.working_balance` | number | Sum of all the account's transactions, cleared or not. |
| `analysis.difference` | number | Bank balance minus cleared balance; negative when YNAB counts more money than the bank. |
| `analysis.to_reconcile_count` | integer | Cleared transactions not yet reconciled. |
| `analysis.uncleared_count` | integer | Transactions the bank has not shown yet. |
| `analysis.uncleared` | array of object | Up to 50 of them. |
| `analysis.explained_by` | array of string | Uncleared transactions whose amount equals the difference. |
| `analysis.possible_duplicates` | array of array of string | Pairs with the same amount and merchant, at most 3 days apart, over the last 60 days. |
| `adjustment` | number \| null | Amount of the balance adjustment created, if adjust was requested; else null. |
| `confirmation` | string \| null | Single-use code confirming exactly this preview, valid 10 minutes; null unless status is confirmation_required. |
| `operation_id` | string \| null | Journal id of the applied operation, for undo_operation; null unless status is applied. |

## Voorbeeld

Argumenten:

```json
{
  "plan_id": "demo-budget",
  "account_id": "acc-checking",
  "bank_balance": 3440.8
}
```

Antwoord op het demobudget:

```json
{
  "status": "difference_found",
  "message": "YNAB's cleared balance differs from the bank by 112.30. Nothing was changed. Check explained_by, uncleared and possible_duplicates with the user; call again once fixed, or with adjust=true to record the gap as an adjustment.",
  "account": "Betaalrekening",
  "analysis": {
    "account_id": "acc-checking",
    "bank_balance": 3440.8,
    "cleared_balance": 3328.5,
    "ynab_cleared_balance": 3328.5,
    "working_balance": 3328.5,
    "difference": 112.3,
    "to_reconcile_count": 54,
    "uncleared_count": 0,
    "uncleared": [],
    "explained_by": [],
    "possible_duplicates": [
      [
        "tx-055",
        "tx-056"
      ]
    ]
  },
  "adjustment": null,
  "confirmation": null,
  "operation_id": null
}
```

## Fouten

- `Account {account_id} is not in this plan: use an id from list_accounts.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

Fouten van YNAB zelf komen terug als `Error calling tool '<tool>': YNAB <status>: <detail>`.

## Zie ook

- [Een rekening afstemmen](/avenir-mcp/nl/guides/reconcile/)
