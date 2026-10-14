# avenir-mcp — an unofficial MCP server for YNAB

<!-- mcp-name: io.github.mathbeal/avenir-mcp -->

[![Works with YNAB](https://api.ynab.com/papi/works_with_ynab.svg)](https://api.ynab.com/#works-with-ynab-third-party)
[![YNAB API terms: self-checked](https://github.com/mathbeal/avenir-mcp/actions/workflows/ynab-terms.yml/badge.svg)](https://github.com/mathbeal/avenir-mcp/actions/workflows/ynab-terms.yml)

Self-checked on every change against YNAB's API terms of 2025-05-28 (naming, attribution,
YNAB's own image, a personal token for its owner only, the hourly limit); a weekly job
turns the badge red when YNAB changes its terms. Listed by YNAB in its
[Works with YNAB](https://api.ynab.com/#works-with-ynab-third-party) directory, among
third-party apps. Not endorsed by YNAB.

Built and tested against YNAB's API v1.87.0. A weekly [`YNAB API drift`](https://github.com/mathbeal/avenir-mcp/actions/workflows/api-drift.yml) check compares it with the live specification and fails when YNAB publishes a new version.

[![quality](https://github.com/mathbeal/avenir-mcp/actions/workflows/quality.yml/badge.svg)](https://github.com/mathbeal/avenir-mcp/actions/workflows/quality.yml)
[![MCP Inspector](https://github.com/mathbeal/avenir-mcp/actions/workflows/inspector.yml/badge.svg)](https://github.com/mathbeal/avenir-mcp/actions/workflows/inspector.yml)
[![docs](https://github.com/mathbeal/avenir-mcp/actions/workflows/docs.yml/badge.svg)](https://avenir-mcp.pages.dev/avenir-mcp/)

[![PyPI](https://img.shields.io/pypi/v/avenir-mcp)](https://pypi.org/project/avenir-mcp/)
[![python](https://img.shields.io/pypi/pyversions/avenir-mcp)](https://pypi.org/project/avenir-mcp/)
[![coverage](https://img.shields.io/badge/coverage-100%25%20lines%20and%20branches-brightgreen)](https://avenir-mcp.pages.dev/avenir-mcp/project/development/#the-checks)
[![types](https://img.shields.io/badge/types-mypy%20strict-blue)](https://avenir-mcp.pages.dev/avenir-mcp/project/development/#the-checks)
[![docstrings](https://img.shields.io/badge/docstrings-Google%20style%2C%20ruff-blue)](https://avenir-mcp.pages.dev/avenir-mcp/project/development/#the-checks)
[![code style](https://img.shields.io/badge/code%20style-ruff-261230)](https://avenir-mcp.pages.dev/avenir-mcp/project/development/#the-checks)
[![licence](https://img.shields.io/badge/licence-MIT-blue)](https://github.com/mathbeal/avenir-mcp/blob/main/LICENSE)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/15139/badge)](https://www.bestpractices.dev/projects/15139)
[![last commit](https://img.shields.io/github/last-commit/mathbeal/avenir-mcp)](https://github.com/mathbeal/avenir-mcp/commits/main)

> 🇬🇧 **avenir-mcp** (*avenir* is French for *the future*) lets an AI agent read your YNAB plan
> and help you plan what comes next.
>
> 🇫🇷 **avenir-mcp** permet à un agent IA de lire votre plan YNAB et de vous aider
> à préparer la suite.

Ask Claude — or any [MCP](https://modelcontextprotocol.io) client — about your plan
in plain words: where the money went, what still needs a category, whether an account
matches the bank, when money would run out. Every change is previewed, confirmed by
you, and can be undone.

**📖 Documentation: <https://avenir-mcp.pages.dev/avenir-mcp/>**

[English](https://avenir-mcp.pages.dev/avenir-mcp/) · [Français](https://avenir-mcp.pages.dev/avenir-mcp/fr/) · [Español](https://avenir-mcp.pages.dev/avenir-mcp/es/) · [Deutsch](https://avenir-mcp.pages.dev/avenir-mcp/de/) · [Nederlands](https://avenir-mcp.pages.dev/avenir-mcp/nl/)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/mathbeal/avenir-mcp/main/.github/assets/demo-dark.svg">
  <img alt="Thirty seconds, one write: move_money previews moving 30 from Tennis to Restaurants — Tennis 80.00 → 50.00, Restaurants 120.00 → 150.00 — and changes nothing; once agreed, the move is applied and journaled; undo_operation then puts both amounts back." src="https://raw.githubusercontent.com/mathbeal/avenir-mcp/main/.github/assets/demo-light.svg" width="720">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/mathbeal/avenir-mcp/main/.github/assets/conversation-dark.svg">
  <img alt="Asked how the budget is doing this month, the agent reads the month with two read-only tools and answers: one category over budget, Restaurants by 22.50, everything else on track." src="https://raw.githubusercontent.com/mathbeal/avenir-mcp/main/.github/assets/conversation-light.svg" width="720">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/mathbeal/avenir-mcp/main/.github/assets/networth-dark.svg">
  <img alt="get_net_worth_trend on the demo plan: over the last 18 months the debts shrink from 27,198 to 19,041 despite the car loan's interest, the assets grow, and the net worth rises from −24,038 to +1,230, with a dip for a car repair and another at Christmas." src="https://raw.githubusercontent.com/mathbeal/avenir-mcp/main/.github/assets/networth-light.svg" width="720">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/mathbeal/avenir-mcp/main/.github/assets/forecast-dark.svg">
  <img alt="forecast_balance on the demo plan: the month-end balance rises from this month to three months ahead, with each month's lowest day and a yearly insurance payment scheduled next month." src="https://raw.githubusercontent.com/mathbeal/avenir-mcp/main/.github/assets/forecast-light.svg" width="720">
</picture>

All four come from the invented demo plan: the write above is replayed by `python -m docsgen`,
so every line of it is what avenir-mcp answers today; then a real reply of Claude Sonnet, and
the net worth and the forecast the documentation shows. The demo plays for thirty seconds and
holds its last frame, which tells the whole story on its own: a reader whose system asks for
less motion, or a viewer that does not animate, sees that frame instead.

> **Unofficial project.** We are not affiliated, associated, or in any way officially
> connected with YNAB or any of its subsidiaries or affiliates. The official YNAB website
> can be found at https://www.ynab.com. The names YNAB and You Need A Budget, as well as
> related names, tradenames, marks, trademarks, emblems, and images are registered
> trademarks of YNAB. They are named here only to say which service avenir-mcp works with.
>
> avenir-mcp is for **personal use on your own machine, with your own YNAB token**. Running it
> as a public or shared server is not supported. It is provided as is, without warranty,
> and is not financial advice: you remain responsible for the changes you confirm. See the
> [legal notice](https://avenir-mcp.pages.dev/avenir-mcp/project/legal/).

## Why avenir-mcp

- **Tools for tasks, not endpoints.** Classify a month of transactions, reconcile an
  account, forecast your balance: one tool each, not a wrapper of YNAB's API.
- **Read-only by default.** Tools that change your plan exist only when you enable
  them.
- **Preview, confirm, undo.** Every write shows what will change and waits for your
  yes; `undo_operation` reverts it.
- **Answers an agent can read.** Currency units, short typed answers, pagination,
  errors that say what to fix, bank text treated as untrusted.
- **Verified.** 100 % line and branch coverage, and an evaluation where a real agent
  works on an invented plan: 25/25 tasks.

## Install

You need [uv](https://docs.astral.sh/uv/) and a YNAB personal access token
(YNAB → Account Settings → Developer Settings → New Token).

[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_avenir--mcp-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://insiders.vscode.dev/redirect/mcp/install?name=avenir-mcp&inputs=%5B%7B%22id%22%3A%22ynab_token%22%2C%22type%22%3A%22promptString%22%2C%22description%22%3A%22YNAB%20personal%20access%20token%22%2C%22password%22%3Atrue%7D%5D&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22avenir-mcp%22%5D%2C%22env%22%3A%7B%22YNAB_API_KEY%22%3A%22%24%7Binput%3Aynab_token%7D%22%7D%7D)
[![Install in Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=avenir-mcp&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJhdmVuaXItbWNwIl0sImVudiI6eyJZTkFCX0FQSV9LRVkiOiJ5b3VyLXRva2VuIn19)

One click installs avenir-mcp **read-only**: VS Code asks for your token in a password box and keeps it in its secret
storage; in Cursor, replace `your-token` in the server's settings. Add `AVENIR_MCP_WRITE=1` to allow changes.

Or by hand:

```bash
# Claude Code
claude mcp add avenir-mcp --env YNAB_API_KEY=your-token --env AVENIR_MCP_WRITE=1 -- uvx avenir-mcp
```

```jsonc
// Claude Desktop, Cursor: the mcpServers block of the client's configuration
{
  "mcpServers": {
    "avenir-mcp": {
      "command": "uvx",
      "args": ["avenir-mcp"],
      "env": { "YNAB_API_KEY": "your-token", "AVENIR_MCP_WRITE": "1" }
    }
  }
}
```

Drop `AVENIR_MCP_WRITE` to stay read-only. Other clients and every option:
[Install](https://avenir-mcp.pages.dev/avenir-mcp/getting-started/install/) ·
[Configuration](https://avenir-mcp.pages.dev/avenir-mcp/reference/configuration/).

## What you can ask

| You ask | avenir-mcp |
|---|---|
| "Which category is overspent this month?" | `get_monthly_summary` — totals and overspent categories |
| "Categorise what is pending." | `suggest_categories`, then `apply_categories` after your yes |
| "Split this receipt: 81.15 groceries, 5.25 household." | `split_transaction` — one transaction across categories, after your yes |
| "Which transaction is my 86.40 receipt from the 12th?" | `find_transactions` — by dates, exact amount and account, categorised or not |
| "My bank shows 3,440.80. Does YNAB agree?" | `reconcile_account` — explains the gap, changes nothing until it matches |
| "Will I go below zero before December?" | `forecast_balance` — month by month, with its assumptions |
| "Am I paying off my debts?" | `get_net_worth_trend` — assets, debts and net worth at each month end |
| "If I lost my income, how long could I last?" | `get_runway` — months the money in the budget covers the usual spending |
| "How much of my income do I keep?" | `get_savings_rate` — income, spending, saved and rate, month by month |
| "Which targets are behind this month?" | `get_underfunded_targets` — what each still needs, most urgent first, against Ready to Assign |
| "When will my debts be paid off if I put 500 a month on them?" | `get_debt_payoff_plan` — avalanche or snowball, the month each debt is paid off and the interest |
| "How old is my money?" | `get_age_of_money` — YNAB's Age of Money month by month, and its trend |
| "Move 30 from Tennis to Restaurants." | `set_category_budget`, previewed and undoable |
| "Undo that." | `undo_operation` |

Walk-throughs with real answers: [Use cases](https://avenir-mcp.pages.dev/avenir-mcp/guides/classify/).
Every tool, resource and prompt: [Reference](https://avenir-mcp.pages.dev/avenir-mcp/reference/tools/).

## Development

```bash
git clone https://github.com/mathbeal/avenir-mcp && cd avenir-mcp
uv sync
just check        # lint, types, tests at 100 % coverage, vocabulary, lockfile
just docs-serve   # the documentation, live
just evaluate     # a real agent on the demo plan (uses your Claude plan)
```

Read [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md) before opening a
pull request. Security reports: [SECURITY.md](SECURITY.md). Also:
[ARCHITECTURE.md](ARCHITECTURE.md), [ROADMAP.md](ROADMAP.md),
[GOVERNANCE.md](GOVERNANCE.md) and the [code of conduct](CODE_OF_CONDUCT.md).

## Fork changes

This fork adds `AVENIR_MCP_AUTO_CONFIRM=1`, which upstream does not have: upstream never
writes without the user's yes. With it set, a write that `undo_operation` can revert
applies without asking, and the server logs a warning for each one. Writes undo cannot
revert still ask (`split_transaction`, `create_category`, `update_category`, approving by
dates, `apply_categories` with `approve`, a target YNAB cannot set back, and every undo).
`reconcile_account` reconciles on the first call when the balances match, and with
`adjust` adds the balance adjustment at once. `approve_transactions` given ids never asks,
with or without this setting (upstream behaviour), so the question `apply_categories`
with `approve` still asks is no safeguard against approving.
It cannot be combined with `AVENIR_MCP_REQUIRE_ELICITATION=1`. See
[Configuration](https://avenir-mcp.pages.dev/avenir-mcp/reference/configuration/).

## Licence

MIT.
