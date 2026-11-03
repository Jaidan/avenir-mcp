# Architecture

avenir-mcp is an [MCP](https://modelcontextprotocol.io) server, written in Python on
[FastMCP](https://gofastmcp.com), that sits between an AI agent and the YNAB API. It
runs on the user's machine, for one person, with that person's YNAB token. This file
describes its high-level design; the
[Architecture](https://avenir-mcp.pages.dev/avenir-mcp/concepts/architecture/) page of the
documentation walks through a read call and a write call step by step.

## Data flow

```
user ── conversation ──> agent (LLM) in an MCP client
                              │  MCP: tools, resources, prompts
                              │  stdio, or streamable HTTP on 127.0.0.1
                              ▼
                         avenir-mcp ──── HTTPS, Bearer token ───> api.ynab.com/v1
                         │        │
             local journal        once a day at most, anonymous ───> pypi.org
             (writes, for undo)
```

1. The user asks the agent a question in plain words.
2. The agent calls a tool. FastMCP validates the arguments against the tool's input
   schema, generated from its signature and pydantic models.
3. The tool checks what it can before any request (a month's format, a cursor, an
   id), asks `client.py` for the data, and hands it to a pure module that computes
   the answer.
4. The answer is a pydantic model, in currency units, validated against the tool's
   output schema and returned as structured content.
5. A tool that changes the plan first returns a preview and waits for the user's
   confirmation; once applied, the change is recorded in the journal so that
   `undo_operation` can revert it.

## Transports

| Transport | When | Guards |
|---|---|---|
| stdio | default | no network port; stdout belongs to the protocol, diagnostics go to stderr |
| streamable HTTP | `AVENIR_MCP_TRANSPORT=http` | listens on `127.0.0.1:8103` by default; `Host` and `Origin` must name this machine; every request carries `Authorization: Bearer` with `AVENIR_MCP_HTTP_TOKEN`, or with a random token the server makes at start-up and prints on stderr when that variable is unset |

`server.main` chooses the transport from the environment. The server takes no
command-line option besides `--version`.

## Read-only by default

Every tool that changes a plan carries the tag `write`. `app.py` installs one
transform, the write gate, that hides those tools from the list and from calls until
`server.main` opens it, which it does only with `AVENIR_MCP_WRITE=1`. In read-only
mode a write tool does not exist for the client, and descriptions of read tools that
mention one are reworded. `tests/test_policy.py` checks the gate, the annotations
(`readOnlyHint`, `destructiveHint`, `idempotentHint`) and that the tag and the
annotation agree.

## Modules

The package `avenir_mcp/` has four layers. Only the I/O layer has side effects.

| Layer | Modules | Role |
|---|---|---|
| Entry | `server.py`, `app.py`, `http_auth.py`, `logs.py`, `updates.py` | start the server, choose the transport, open or close the write gate, guard HTTP, configure logs on stderr, check PyPI for a newer release |
| Tools | `tools_budget.py`, `tools_accounts.py`, `tools_age.py`, `tools_categories.py`, `tools_classify.py`, `tools_flags.py`, `tools_targets.py`, `tools_charges.py`, `tools_networth.py`, `tools_payoff.py`, `tools_runway.py`, `tools_savings.py`, `tools_underfunded.py`, `tools_undo.py`, `context.py` | declare what the agent sees: tools, resources and prompts; orchestrate; never compute |
| Confirmation | `confirm.py`, `writes.py` | the single path of every confirmed write: preview, confirmation, apply, journal |
| Logic | `age.py`, `analytics.py`, `classifier.py`, `triage.py`, `reconcile.py`, `forecast.py`, `charges.py`, `networth.py`, `payoff.py`, `runway.py`, `savings.py`, `schedule.py`, `search.py`, `split.py`, `flags.py`, `targets.py`, `underfunded.py` | pure functions on data already fetched: no network, no disk |
| Shared types | `model.py`, `amounts.py`, `text.py` | the base model (unknown fields refused), the amount type (finite, bounded), untrusted text made safe to show |
| I/O | `client.py` (HTTP to YNAB), `retry.py`, `journal.py` (disk) | the only code that talks to YNAB, what a failed request may do next, and the only code that writes the journal |

Amounts arrive from YNAB in milliunits and leave the logic in currency units: no
tool returns milliunits. The conversions are the two functions of `client.py`
(`milliunit_to_amount`, `amount_to_milliunit`), which the logic calls. `client.py`
also keeps an in-memory
delta-sync cache of transactions and paces requests below YNAB's limit of 200 per
hour.

`retry.py` decides, from the method and the failure alone, whether a request may leave
again and after how long: a read may, and so may anything that never reached YNAB, but a
`POST`, `PATCH` or `DELETE` that has been sent never does, because YNAB may have applied
it and a second copy would duplicate the change. Every try takes one request from the
hour's budget, and a request YNAB never answered reaches the agent as
`retry.YnabUnavailable`, whose message says whether anything may have changed.

### Confirmations

`confirm.py` asks the user through MCP elicitation when the client supports it.
Otherwise the tool returns the preview and a single-use code (`writes.Confirmations`)
bound to a SHA-256 fingerprint of exactly that preview, valid ten minutes, kept in
memory. With `AVENIR_MCP_REQUIRE_ELICITATION=1`, codes are disabled. Two write tools
act at once, without a preview: `approve_transactions` given ids (marks those
transactions as reviewed) and `import_transactions` (asks YNAB to import what linked
banks already have). `approve_transactions` given dates selects the transactions
itself, so it is previewed and confirmed like the other writes.

### Journal and undo

`journal.py` appends one JSON line per applied operation to
`$XDG_STATE_HOME/avenir-mcp/journal.jsonl` (or `AVENIR_MCP_JOURNAL`), created with mode
`0600`. A line holds identifiers and, where undo needs them, the amounts or settings
before and after; never a payee, memo or transaction amount. `tools_undo.py` reverts
an operation through the same confirmation path, and leaves alone anything changed
since.

### Update check

`updates.py` asks `https://pypi.org/pypi/avenir-mcp/json` at most once a day whether a
newer release exists, and adds one line to the server's instructions when it does. It
sends nothing about the user, never upgrades anything, and is off with
`AVENIR_MCP_NO_UPDATE_CHECK=1`, `DO_NOT_TRACK=1` or in CI. Only a plain version number
from PyPI's answer can reach the agent.

## Outside the package

| Directory | Role |
|---|---|
| `tests/` | unit, property (Hypothesis), protocol (an in-memory MCP client), documentation, API coverage and hygiene tests; 100 % line and branch coverage |
| `evals/` | an invented demo plan, a local stand-in for YNAB's API that serves it, the MCP Inspector check, and an evaluation where a real agent performs tasks on the demo plan |
| `docsgen/` | generates the tool reference, the error catalogue, the examples (by running avenir-mcp on the demo plan), the security page from `SECURITY.md`, and the API coverage page; checks YNAB's API and terms against their snapshots |
| `api/` | a snapshot of YNAB's OpenAPI operations, why each unused one is planned or left out, and the rules each sent field follows |
| `docs/` | the documentation site (Astro Starlight) in English, French, Spanish, German and Dutch |
| `benchmarks/` | timings of the logic on a generated five-year plan |

## Dependencies

At run time: `fastmcp` (the MCP protocol, schemas and transports), `httpx` (HTTP to
YNAB and PyPI) and `pydantic` (already required by fastmcp). Adding one needs a reason
written in the pull request ([AGENTS.md](AGENTS.md)).
