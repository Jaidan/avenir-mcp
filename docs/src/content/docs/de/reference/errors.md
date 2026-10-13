---
title: "Fehler"
description: "Jede Fehlermeldung, die avenir-mcp zurückgeben kann, Tool für Tool."
sidebar:
  order: 2
---

Ein Fehler kommt als Tool-Ergebnis mit `isError` zurück, mit einer Meldung, die sagt, was zu korrigieren ist, damit der Agent seinen Aufruf berichtigen kann. Teile in geschweiften Klammern stehen für den übergebenen Wert.

## Von YNAB

Jedes Tool, das YNAB aufruft, kann den Fehler von YNAB zurückgeben: `Error calling tool '<tool>': YNAB <status>: <detail>` — zum Beispiel `YNAB 401` für ein falsches oder widerrufenes Token, `YNAB 429`, wenn die 200 Anfragen pro Stunde aufgebraucht sind. Eine `401`-Antwort enthält die eigenen Angaben von avenir-mcp anstelle der von YNAB: `YNAB 401: the token is invalid or was revoked; create a new Personal Access Token in YNAB's settings.` Wenn YNAB überhaupt nicht antwortet, gibt die Meldung an, ob sich möglicherweise etwas geändert hat: Bei einem Lesevorgang wird mitgeteilt, dass YNAB nicht erreichbar war und dass keine Änderungen vorgenommen wurden; bei einem bereits gesendeten Schreibvorgang wird angegeben, dass die Änderung möglicherweise übernommen wurde oder auch nicht und dass dies überprüft werden muss, bevor ein erneuter Versuch unternommen wird. Ohne `YNAB_API_KEY` weigert sich der Server, YNAB aufzurufen: `YNAB_API_KEY environment variable is not set`.

## [`find_transactions`](/avenir-mcp/de/reference/tools/find-transactions/)

- `until_date {until} is before since_date {since}: swap them.`
- `The dates span more than 366 days: search a shorter period.`
- `Account {0} is not in this plan: use an id from list_accounts.`
- `Category {0} is not in this plan: use a category_id from get_category_balances.`

## [`forecast_balance`](/avenir-mcp/de/reference/tools/forecast-balance/)

- `Unknown account(s) {unknown}: use ids from list_accounts.`
- `until must be the current month or later.`
- `until must be at most 24 months ahead.`
- `until must be a month as YYYY-MM, got '{until}'.`

## [`get_budget_vs_actual`](/avenir-mcp/de/reference/tools/get-budget-vs-actual/)

- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`

## [`get_category_balances`](/avenir-mcp/de/reference/tools/get-category-balances/)

- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`

## [`get_debt_payoff_plan`](/avenir-mcp/de/reference/tools/get-debt-payoff-plan/)

- `Unknown debt account(s) {given}: give names or ids of the open accounts that owe money: {names}.`
- `No minimum payment is known and nothing was paid into the debt accounts over the last 3 complete months: give monthly_budget, or minimum_payment in overrides.`
- `monthly_budget {given} is less than the minimum payments, {minimums}: give at least that much.`

## [`get_monthly_summary`](/avenir-mcp/de/reference/tools/get-monthly-summary/)

- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`

## [`get_runway`](/avenir-mcp/de/reference/tools/get-runway/)

- `Unknown category group(s) {given}: give names or ids of this plan's groups, as list_category_groups shows them: {names}.`

## [`get_underfunded_targets`](/avenir-mcp/de/reference/tools/get-underfunded-targets/)

- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`

## [`list_scheduled_transactions`](/avenir-mcp/de/reference/tools/list-scheduled-transactions/)

- `until_date {until} is before since_date {since}: swap them.`
- `The dates span more than 366 days: search a shorter period.`
- `Account {0} is not in this plan: use an id from list_accounts.`
- `Category {0} is not in this plan: use a category_id from get_category_balances.`

## [`suggest_categories`](/avenir-mcp/de/reference/tools/suggest-categories/)

- `until_date {until} is before since_date {since}: swap them.`
- `This cursor was issued for a different date window: pass the same since_date and until_date as for the first page, or omit the cursor to start again.`
- `Invalid cursor: pass the next_cursor value from the previous page unchanged, or omit it to start from the first page.`

## [`apply_categories`](/avenir-mcp/de/reference/tools/apply-categories/)

- `Approving failed ({error}): {outcome}{categories}.`
- `Transaction {tx_id} is assigned twice: keep one assignment.`
- `Transaction {tx_id} is not in this plan: use the transaction_id values returned by suggest_categories.`
- `Transaction {tx_id} is split across categories: change its lines in YNAB.`
- `Transaction {tx_id} is on an off-budget account: YNAB gives it no category.`
- `Transaction {tx_id} is a transfer between accounts: YNAB gives it no category.`
- `Category {category_id} is YNAB's internal Uncategorized: choose a real category.`
- `Category {category_id} is not in this plan: use a category_id from the categories returned by suggest_categories.`
- `Category {category_id} pays a credit card: YNAB ignores it on a transaction. Choose the category of what was paid for.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`approve_transactions`](/avenir-mcp/de/reference/tools/approve-transactions/)

- `Give either tx_ids, to approve those transactions, or since_date (with until_date and exclude_ids if needed), to approve a reviewed period; not both.`
- `until_date {until} is before since_date {since}: swap them.`
- `The dates span more than 366 days: search a shorter period.`
- `Account {0} is not in this plan: use an id from list_accounts.`
- `Category {0} is not in this plan: use a category_id from get_category_balances.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`create_category`](/avenir-mcp/de/reference/tools/create-category/)

- `Group {category_group_id} is not in this plan: use an id from list_category_groups.`
- `The name is empty: give the new category a name.`
- `'{new_name}' already exists in {group}.`
- `'{name}' contains a line break, control or format character (such as a zero-width or direction mark): give the name on one line, with visible characters only.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`create_transactions`](/avenir-mcp/de/reference/tools/create-transactions/)

- `Account {account_id} is not in this plan: use an id from list_accounts.`
- `Give at least one transaction to create.`
- `{date} is in the future: YNAB only records transactions that happened.`
- `Category {category} is not in this plan: use a category_id from get_category_balances.`
- `Category {category} pays a credit card: YNAB ignores it on a transaction. Choose the category of what was paid for.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`flag_transactions`](/avenir-mcp/de/reference/tools/flag-transactions/)

- `Give at least one flag.`
- `Transaction {twice} is named twice: give one flag each.`
- `Transaction {unknown} is not in this plan: use a transaction_id from find_transactions.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`move_money`](/avenir-mcp/de/reference/tools/move-money/)

- `Give two different categories: money moves from one to another.`
- `Category {category_id} is not in this plan: use a category_id from get_category_balances.`
- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`
- `{refused}; {name} is back to {from_amount}: nothing was moved.`
- `{refused}, then putting {name} back failed too ({again}): set {name} back to {from_amount} in YNAB.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`reconcile_account`](/avenir-mcp/de/reference/tools/reconcile-account/)

- `Account {account_id} is not in this plan: use an id from list_accounts.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`rename_payee`](/avenir-mcp/de/reference/tools/rename-payee/)

- `Payee {payee_id} is a transfer's: YNAB names it after the account the money moves to. Rename the account in YNAB itself.`
- `Payee {payee_id} is not in this plan: use a payee_id from list_payees.`
- `The new name is empty: give the merchant's name.`
- `The new name is {new_name} characters: YNAB refuses a payee name longer than 500.`
- `'{new_name}' is already the name of another payee: YNAB's API cannot merge two payees. Merge them in YNAB, or choose another name.`
- `'{name}' contains a line break, control or format character (such as a zero-width or direction mark): give the name on one line, with visible characters only.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`set_category_budget`](/avenir-mcp/de/reference/tools/set-category-budget/)

- `Category {category_id} is not in this plan: use a category_id from get_category_balances.`
- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`set_category_target`](/avenir-mcp/de/reference/tools/set-category-target/)

- `Category {category_id} is not in this plan: use a category_id from get_category_balances or list_category_groups.`
- `Give either a date or a frequency, not both: YNAB refuses the two.`
- `To remove the target, give no amount, no date and no frequency.`
- `The amount must be greater than 0; to remove the target, give none.`
- `YNAB takes neither a date nor a frequency on a category paired to a loan account: give an amount alone.`
- `YNAB takes no frequency on a credit card payment category: give an amount alone, or a date.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`split_transaction`](/avenir-mcp/de/reference/tools/split-transaction/)

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

## [`undo_operation`](/avenir-mcp/de/reference/tools/undo-operation/)

- `Nothing to undo: no operation of this plan is still in effect with id {operation_id}.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`update_category`](/avenir-mcp/de/reference/tools/update-category/)

- `Category {category_id} is not in this plan: use a category_id from suggest_categories.`
- `Group {category_group_id} is not in this plan: use an id from list_category_groups.`
- `The new name is empty: give a name, or omit it to keep the current one.`
- `'{name}' contains a line break, control or format character (such as a zero-width or direction mark): give the name on one line, with visible characters only.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`
