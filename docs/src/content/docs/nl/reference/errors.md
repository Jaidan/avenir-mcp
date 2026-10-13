---
title: "Fouten"
description: "Elke foutmelding die avenir-mcp kan teruggeven, tool voor tool."
sidebar:
  order: 2
---

Een fout komt terug als toolresultaat met `isError`, met een melding die zegt wat er moet worden verbeterd, zodat de agent zijn aanroep kan corrigeren. Delen tussen accolades staan voor de doorgegeven waarde.

## Van YNAB

Elke tool die YNAB aanroept, kan de fout van YNAB teruggeven: `Error calling tool '<tool>': YNAB <status>: <detail>` — bijvoorbeeld `YNAB 401` voor een verkeerd of ingetrokken token, `YNAB 429` wanneer de 200 verzoeken per uur op zijn. Een `401`-antwoord bevat de eigen gegevens van avenir-mcp in plaats van die van YNAB: `YNAB 401: the token is invalid or was revoked; create a new Personal Access Token in YNAB's settings.` Wanneer YNAB helemaal niet reageert, geeft het bericht aan of er mogelijk iets is gewijzigd: bij een leesbewerking wordt aangegeven dat YNAB niet bereikbaar was en dat er niets is gewijzigd, terwijl bij een schrijfbewerking die al is verzonden wordt aangegeven dat de wijziging mogelijk wel of niet is doorgevoerd en dat dit moet worden gecontroleerd voordat er opnieuw een poging wordt ondernomen. Zonder `YNAB_API_KEY` weigert de server YNAB aan te roepen: `YNAB_API_KEY environment variable is not set`.

## [`find_transactions`](/avenir-mcp/nl/reference/tools/find-transactions/)

- `until_date {until} is before since_date {since}: swap them.`
- `The dates span more than 366 days: search a shorter period.`
- `Account {0} is not in this plan: use an id from list_accounts.`
- `Category {0} is not in this plan: use a category_id from get_category_balances.`

## [`forecast_balance`](/avenir-mcp/nl/reference/tools/forecast-balance/)

- `Unknown account(s) {unknown}: use ids from list_accounts.`
- `until must be the current month or later.`
- `until must be at most 24 months ahead.`
- `until must be a month as YYYY-MM, got '{until}'.`

## [`get_budget_vs_actual`](/avenir-mcp/nl/reference/tools/get-budget-vs-actual/)

- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`

## [`get_category_balances`](/avenir-mcp/nl/reference/tools/get-category-balances/)

- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`

## [`get_debt_payoff_plan`](/avenir-mcp/nl/reference/tools/get-debt-payoff-plan/)

- `Unknown debt account(s) {given}: give names or ids of the open accounts that owe money: {names}.`
- `No minimum payment is known and nothing was paid into the debt accounts over the last 3 complete months: give monthly_budget, or minimum_payment in overrides.`
- `monthly_budget {given} is less than the minimum payments, {minimums}: give at least that much.`

## [`get_monthly_summary`](/avenir-mcp/nl/reference/tools/get-monthly-summary/)

- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`

## [`get_runway`](/avenir-mcp/nl/reference/tools/get-runway/)

- `Unknown category group(s) {given}: give names or ids of this plan's groups, as list_category_groups shows them: {names}.`

## [`get_underfunded_targets`](/avenir-mcp/nl/reference/tools/get-underfunded-targets/)

- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`

## [`list_scheduled_transactions`](/avenir-mcp/nl/reference/tools/list-scheduled-transactions/)

- `until_date {until} is before since_date {since}: swap them.`
- `The dates span more than 366 days: search a shorter period.`
- `Account {0} is not in this plan: use an id from list_accounts.`
- `Category {0} is not in this plan: use a category_id from get_category_balances.`

## [`suggest_categories`](/avenir-mcp/nl/reference/tools/suggest-categories/)

- `until_date {until} is before since_date {since}: swap them.`
- `This cursor was issued for a different date window: pass the same since_date and until_date as for the first page, or omit the cursor to start again.`
- `Invalid cursor: pass the next_cursor value from the previous page unchanged, or omit it to start from the first page.`

## [`apply_categories`](/avenir-mcp/nl/reference/tools/apply-categories/)

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

## [`create_category`](/avenir-mcp/nl/reference/tools/create-category/)

- `Group {category_group_id} is not in this plan: use an id from list_category_groups.`
- `The name is empty: give the new category a name.`
- `'{new_name}' already exists in {group}.`
- `'{name}' contains a line break, control or format character (such as a zero-width or direction mark): give the name on one line, with visible characters only.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`create_transactions`](/avenir-mcp/nl/reference/tools/create-transactions/)

- `Account {account_id} is not in this plan: use an id from list_accounts.`
- `Give at least one transaction to create.`
- `{date} is in the future: YNAB only records transactions that happened.`
- `Category {category} is not in this plan: use a category_id from get_category_balances.`
- `Category {category} pays a credit card: YNAB ignores it on a transaction. Choose the category of what was paid for.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`flag_transactions`](/avenir-mcp/nl/reference/tools/flag-transactions/)

- `Give at least one flag.`
- `Transaction {twice} is named twice: give one flag each.`
- `Transaction {unknown} is not in this plan: use a transaction_id from find_transactions.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`move_money`](/avenir-mcp/nl/reference/tools/move-money/)

- `Give two different categories: money moves from one to another.`
- `Category {category_id} is not in this plan: use a category_id from get_category_balances.`
- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`
- `{refused}; {name} is back to {from_amount}: nothing was moved.`
- `{refused}, then putting {name} back failed too ({again}): set {name} back to {from_amount} in YNAB.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`reconcile_account`](/avenir-mcp/nl/reference/tools/reconcile-account/)

- `Account {account_id} is not in this plan: use an id from list_accounts.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`rename_payee`](/avenir-mcp/nl/reference/tools/rename-payee/)

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

## [`set_category_budget`](/avenir-mcp/nl/reference/tools/set-category-budget/)

- `Category {category_id} is not in this plan: use a category_id from get_category_balances.`
- `month must be 'current' or the first day of a month as YYYY-MM-01, got '{month}'.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`set_category_target`](/avenir-mcp/nl/reference/tools/set-category-target/)

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

## [`split_transaction`](/avenir-mcp/nl/reference/tools/split-transaction/)

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

## [`undo_operation`](/avenir-mcp/nl/reference/tools/undo-operation/)

- `Nothing to undo: no operation of this plan is still in effect with id {operation_id}.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`

## [`update_category`](/avenir-mcp/nl/reference/tools/update-category/)

- `Category {category_id} is not in this plan: use a category_id from suggest_categories.`
- `Group {category_group_id} is not in this plan: use an id from list_category_groups.`
- `The new name is empty: give a name, or omit it to keep the current one.`
- `'{name}' contains a line break, control or format character (such as a zero-width or direction mark): give the name on one line, with visible characters only.`
- `This client cannot ask the user to confirm, and AVENIR_MCP_REQUIRE_ELICITATION=1 forbids confirmation codes: nothing was changed. Use a client that supports MCP elicitation, or unset the variable.`
- `This confirmation code is unknown, expired, already used, or was issued for different changes. Call again without confirmation to get a new preview.`
- `Confirmation codes are disabled (AVENIR_MCP_REQUIRE_ELICITATION=1): call again without confirmation, and the user answers in the client.`
- `The plan changed between the preview and the answer. Call again without an answer to get a new preview.`
