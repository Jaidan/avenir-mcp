---
title: "Tools"
description: "Alle Tools, die avenir-mcp bereitstellt: Zweck, lesend oder schreibend, Kosten."
sidebar:
  order: 1
---

avenir-mcp stellt diese Tools bereit. Lesende Tools sind immer verfügbar; schreibende existieren nur mit `AVENIR_MCP_WRITE=1`, und alle außer `import_transactions` werden als Vorschau gezeigt und bestätigt; `approve_transactions` fragt vorher, wenn es nach Datum genehmigt, und wendet übergebene IDs sofort an.

## Lesen

| Tool | Kurzbeschreibung |
|---|---|
| [`find_recurring_charges`](/avenir-mcp/de/reference/tools/find-recurring-charges/) | List the subscriptions and other charges paid every month, with their yearly cost. |
| [`find_transactions`](/avenir-mcp/de/reference/tools/find-transactions/) | Find transactions by date, amount, account, category or payee, categorised or not. |
| [`forecast_balance`](/avenir-mcp/de/reference/tools/forecast-balance/) | Project the balance month by month and say when money would run out. |
| [`get_age_of_money`](/avenir-mcp/de/reference/tools/get-age-of-money/) | YNAB's Age of Money: how old the money spent is today, and its trend month by month. |
| [`get_budget_vs_actual`](/avenir-mcp/de/reference/tools/get-budget-vs-actual/) | Share of each category's budget spent in a month, to see what is over or close. |
| [`get_category_balances`](/avenir-mcp/de/reference/tools/get-category-balances/) | Budgeted, spent (activity) and available (balance) per category for a month. |
| [`get_debt_payoff_plan`](/avenir-mcp/de/reference/tools/get-debt-payoff-plan/) | When the debts would be paid off, highest rate first (avalanche) or smallest first. |
| [`get_monthly_summary`](/avenir-mcp/de/reference/tools/get-monthly-summary/) | A month at a glance: income, budgeted, spent, Ready to Assign, overspent categories. |
| [`get_net_worth_trend`](/avenir-mcp/de/reference/tools/get-net-worth-trend/) | Assets, debts and net worth at the end of each month, to see debts go down. |
| [`get_runway`](/avenir-mcp/de/reference/tools/get-runway/) | How many months the money available would last without income, at the usual spending. |
| [`get_savings_rate`](/avenir-mcp/de/reference/tools/get-savings-rate/) | How much of the income was kept, month by month: income, spending, saved, rate. |
| [`get_spending_trends`](/avenir-mcp/de/reference/tools/get-spending-trends/) | Spending per category, month by month, over the last N months. |
| [`get_underfunded_targets`](/avenir-mcp/de/reference/tools/get-underfunded-targets/) | The categories whose target still needs money this month, the most urgent first. |
| [`list_accounts`](/avenir-mcp/de/reference/tools/list-accounts/) | List the plan's accounts with their balances, bank link and last reconciliation. |
| [`list_category_groups`](/avenir-mcp/de/reference/tools/list-category-groups/) | List the category groups a new category can be created in. |
| [`list_payees`](/avenir-mcp/de/reference/tools/list-payees/) | List the payees of a plan, those most transactions name first. |
| [`list_plans`](/avenir-mcp/de/reference/tools/list-plans/) | List all YNAB plans accessible with the current API key. |
| [`list_scheduled_transactions`](/avenir-mcp/de/reference/tools/list-scheduled-transactions/) | List the scheduled transactions due between two dates: bills, salary, transfers. |
| [`suggest_categories`](/avenir-mcp/de/reference/tools/suggest-categories/) | List the transactions waiting for a category, with a suggestion when history allows. |

## Schreiben

| Tool | Kurzbeschreibung |
|---|---|
| [`apply_categories`](/avenir-mcp/de/reference/tools/apply-categories/) | Assign categories to transactions, after the user confirms, and journal it for undo. |
| [`approve_transactions`](/avenir-mcp/de/reference/tools/approve-transactions/) | Mark transactions as approved, i.e. reviewed (clears YNAB's "unapproved" badge). |
| [`create_category`](/avenir-mcp/de/reference/tools/create-category/) | Create a category in a group, after the user confirms. |
| [`create_transactions`](/avenir-mcp/de/reference/tools/create-transactions/) | Create transactions on an account, e.g. ones the bank import missed, after the user confirms. |
| [`flag_transactions`](/avenir-mcp/de/reference/tools/flag-transactions/) | Set or remove the coloured flag of transactions, after the user confirms. |
| [`import_transactions`](/avenir-mcp/de/reference/tools/import-transactions/) | Import the latest transactions from the plan's linked bank accounts into YNAB. |
| [`move_money`](/avenir-mcp/de/reference/tools/move-money/) | Move money budgeted in one category to another for a month, after the user confirms. |
| [`reconcile_account`](/avenir-mcp/de/reference/tools/reconcile-account/) | Compare an account with the balance your bank shows, then reconcile it. |
| [`rename_payee`](/avenir-mcp/de/reference/tools/rename-payee/) | Rename a payee, e.g. a bank label into the merchant's name, after the user confirms. |
| [`set_category_budget`](/avenir-mcp/de/reference/tools/set-category-budget/) | Set the amount budgeted ("Assigned") in a category for a month, after the user confirms. |
| [`set_category_target`](/avenir-mcp/de/reference/tools/set-category-target/) | Set, change or remove a category's target, after the user confirms. |
| [`split_transaction`](/avenir-mcp/de/reference/tools/split-transaction/) | Split one transaction across categories, e.g. from a receipt, after the user confirms. |
| [`undo_operation`](/avenir-mcp/de/reference/tools/undo-operation/) | Undo an operation made through this server: the latest one, or the one named. |
| [`update_category`](/avenir-mcp/de/reference/tools/update-category/) | Rename a category and/or move it to another group, after the user confirms. |

## Ressourcen

| URI | Beschreibung |
|---|---|
| `avenir-mcp://guide` | How to use this server's tools, and the YNAB method in brief. |
| `ynab://plans` | The plans (budgets) the token can read, with the ids tools need. |
| `ynab://plans/{plan_id}/categories` | A plan's assignable categories by group, with their ids. |
| `ynab://plans/{plan_id}/accounts` | A plan's open accounts, balances in currency units. |

## Prompts

| Prompt | Argumente | Beschreibung |
|---|---|---|
| `classify_pending` | `plan_id` | Classify the transactions waiting for a category. |
| `monthly_review` | `plan_id`, `month` (optional) | Review a month of a plan: where the money went and what needs attention. |
| `reconcile` | `plan_id`, `account_id`, `bank_balance` | Reconcile an account with the balance the bank shows. |
| `plan_next_month` | `plan_id` | Prepare next month's category amounts from the forecast and this month's categories. |
