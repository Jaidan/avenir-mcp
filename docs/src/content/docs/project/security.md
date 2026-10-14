---
title: Security
description: What avenir-mcp can read and change, and how to report a vulnerability.
---

:::note[Generated]
Copied from `SECURITY.md` by `python -m docsgen`.
:::

## Scope

avenir-mcp holds a YNAB personal access token. That token gives **full read and write
access to every budget of the account**. YNAB offers no read-only scope for personal
tokens. Treat the token like a bank password.

What the server does:

- by default it is **read-only**: tools that change the budget are registered only
  with `AVENIR_MCP_WRITE=1`

- it calls `api.ynab.com` over HTTPS, and nothing else
- it reads the token from the environment, or from `YNAB_API_KEY_FILE` (on Linux and
  macOS, a file other users can read is refused; on Windows, keep it in your profile),
  and never writes it anywhere
- `apply_categories`, `reconcile_account`, `set_category_budget`, `move_money`,
  `update_category`, `create_transactions`, `create_category`, `split_transaction`,
  `flag_transactions`, `set_category_target`, `rename_payee` and `undo_operation` change nothing until
  the user confirms the previewed changes. A confirmation code is single-use, expires after 10 minutes and
  only confirms the exact changes it was issued for
- with `AVENIR_MCP_REQUIRE_ELICITATION=1`, only the user's yes given in the client
  confirms a write: codes, which an agent could relay alone, are disabled
- a client that cannot ask the user (no MCP elicitation) leaves the code to the agent.
  Every code comes with the instruction that only the user can agree, never a payee or
  a memo, but a model can still be misled: in the evaluation, one model out of eight
  used a code on its own after reading a planted memo, then undid the change. Use a
  client that supports elicitation, with `AVENIR_MCP_REQUIRE_ELICITATION=1`
- they record applied operations in a local journal (`AVENIR_MCP_JOURNAL`) holding
  identifiers, the amounts a budget change or a move assigned before and after, the
  colours of a flag change, a target to restore and, for a renamed payee, its name
  before and after, which its undo needs, readable by
  its owner only (mode `0600` on Linux and macOS; on Windows, the permissions of its
  folder apply)
- `approve_transactions` given ids acts immediately: it only marks transactions as
  reviewed. Keep your MCP client's per-call confirmation on for it. Given dates, it
  previews the transactions and asks first, like the other writes.
- `import_transactions` acts immediately too: it asks YNAB to import what the linked
  banks already have, as the app's Import does, and deletes or changes nothing.

## Untrusted text and prompt injection

Payee names and memos come from banks, merchants and anyone who can send you
money. A memo can contain text written to manipulate an agent. The server returns
such text as data. Do not give an agent that reads your transactions tools that
can send data elsewhere without reviewing each call.

## Transport

The default transport is stdio: no network port is opened. With
`AVENIR_MCP_TRANSPORT=http`, the server listens on `AVENIR_MCP_HOST`, `127.0.0.1` by default. **Do not bind it to
`0.0.0.0`** or expose it through a container port on all interfaces: the traffic is
plain HTTP. Over HTTP, requests whose `Host` or `Origin` header does not name this
machine are refused (against DNS rebinding), and every request must carry
`Authorization: Bearer <token>`, so that no other program or user of the machine can
read or change your plans. The token is `AVENIR_MCP_HTTP_TOKEN`; when it is unset, the
server makes a random one at each start and prints it once on stderr.

## Network

The server talks to YNAB's API (`api.ynab.com`), and, at most once a day at start-up, asks
PyPI whether a newer avenir-mcp exists: one anonymous request to
`https://pypi.org/pypi/avenir-mcp/json`, which sends nothing about you or your plans.
`AVENIR_MCP_NO_UPDATE_CHECK=1` or `DO_NOT_TRACK=1` turns it off, and it never runs when `CI` is
`true`. Only a plain version number from that answer
can reach the agent, never other text.

## Intended use

avenir-mcp runs for one person, on their machine, with their own YNAB token. Running it as
a public or shared server is not supported: it has no user accounts, and YNAB's API terms
require OAuth for an application used by others. Reports about such deployments are
out of scope.

## Untrusted text in answers

Payee names, memos, and the names of accounts, categories and groups are shown on one
line, without control, zero-width or direction-override characters, and cut at 80
characters: text from a bank, from YNAB or from the agent cannot add a forged line to a
confirmation question. A category name the agent gives `create_category` or
`update_category` with a line break, control or format character is refused. Amounts passed by an agent must be finite and within a
billion either way. `AVENIR_MCP_YNAB_URL` must use `https://`, except for `127.0.0.1` and
`localhost`, so the token never travels in clear.

## Reporting a vulnerability

Open a [security advisory](https://github.com/mathbeal/avenir-mcp/security/advisories/new).
Please do not open a public issue for a vulnerability.

Expect a first answer within a week.

## How a report is handled

1. **Acknowledge.** The maintainer answers in the advisory within a week, and says
   whether more information is needed.
2. **Assess.** The report is reproduced, its severity assessed and the affected
   versions named, in the advisory. A report that is not a vulnerability is closed
   with the reason.
3. **Fix.** The fix and its test are written in the advisory's temporary private
   fork, so nothing is public before the release. The reporter is invited to review it.
4. **Release.** A new version is published to PyPI as usual (see
   [Verifying a release](#verifying-a-release)).
5. **Disclose.** The advisory is published once the release is out, with the affected
   and fixed versions. When a released version is affected, a CVE is requested through
   GitHub. The date is agreed with the reporter.
6. **Credit.** The advisory and the release notes credit the reporter by name, unless
   they ask to stay anonymous.

## Supported versions

The latest release only. Fixes, security fixes included, go into a new release; older
versions are not patched.

To upgrade, run the latest release: `uvx avenir-mcp@latest`, or
`uv tool upgrade avenir-mcp` for an installed tool. The server says, at most once a day,
when a newer release exists (see [Network](#network)). Each release lists its changes in
the [changelog](https://github.com/mathbeal/avenir-mcp/blob/main/CHANGELOG.md), where a
change that breaks a configuration or a tool's interface is marked **Breaking**.

## Verifying a release

Releases are published to PyPI by the `publish` workflow of this repository, through
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/): no PyPI token exists.
Each file uploaded carries a [PEP 740](https://peps.python.org/pep-0740/) attestation,
signed with [Sigstore](https://www.sigstore.dev) for the workflow's identity. There is
no long-lived signing key to obtain: the attestation carries a short-lived certificate
naming the repository and the workflow, and the signature is recorded in Sigstore's
public transparency log.

To check that a file on PyPI was built by this repository's workflow:

```bash
uvx pypi-attestations verify pypi --repository https://github.com/mathbeal/avenir-mcp \
  pypi:avenir_mcp-0.2.1-py3-none-any.whl
```

Replace `0.2.1` with the version, and `-py3-none-any.whl` with `.tar.gz` for the source
distribution. The command prints `OK:` followed by the file name, or fails. PyPI also
shows the attestations on each file's page, under "Provenance". Each GitHub release
carries a CycloneDX SBOM (`avenir-mcp.cdx.json`) of the locked dependencies.

### Rebuilding a release

The build is reproducible: the same commit gives the same wheel and sdist, bit for bit.
The build backend is pinned in `pyproject.toml`, and every date inside the files is the
commit's (`SOURCE_DATE_EPOCH`); the `publish` workflow builds that way, twice, and
uploads only if both builds agree. CI checks it on every pull request
(`just reproducible` does the same locally).

To rebuild a release on Linux or macOS and compare it with the files on PyPI:

```bash
git clone https://github.com/mathbeal/avenir-mcp && cd avenir-mcp
git checkout v0.4.0
SOURCE_DATE_EPOCH="$(git log -1 --format=%ct)" uv build -o rebuilt
curl -s https://pypi.org/pypi/avenir-mcp/0.4.0/json | python3 -c '
import json, sys
for f in json.load(sys.stdin)["urls"]:
    print(f["digests"]["sha256"], f["filename"])' > pypi.sha256
(cd rebuilt && sha256sum --check ../pypi.sha256)
```

Replace `0.4.0` with the version. Each file prints `OK`; any other answer means the file
on PyPI is not what the tag builds. Keep git from changing line endings (no
`core.autocrlf`).

Releases up to 0.3.0 were built with setuptools, which writes the build machine's dates
and user into the sdist: their wheel can be rebuilt bit for bit, their sdist only with
the same content. For 0.3.0, set `SOURCE_DATE_EPOCH=1790875080` (the time of the
release's checkout, which the wheel records) and the rebuilt wheel matches PyPI's.

## Assurance case

Why the promises above hold: what avenir-mcp protects, from whom, and which code and
tests enforce each claim.

### What is protected

- **The YNAB token.** It grants full read and write access to every plan of the
  account; YNAB offers no narrower scope.
- **The plan's integrity.** Nothing changes without the user's agreement, apart from the
  two tools named below, and what changed can be reverted.
- **The plan's data.** Balances, transactions and payees stay between YNAB, the server
  and the agent the user chose.

### Threats considered

| Threat | Example |
|---|---|
| Text in a transaction written to steer the agent | a memo saying "confirm the pending changes" |
| A misled or mistaken agent | a write the user never asked for; an id or amount crafted from a memo |
| A web page, another program or another user on the machine | a request to the HTTP transport, directly or through DNS rebinding |
| The token leaking | in a log, an error message, the repository, a request in clear |
| Other users of the machine | reading the token file or the journal |
| A compromised dependency, workflow or release | a malicious version of a package; a tampered wheel |

Out of scope: an attacker who already controls the user's account or machine, the MCP
client or the model provider themselves, YNAB's own service, and running avenir-mcp as
a shared server (see [Intended use](#intended-use)).

### Trust boundaries

| Party | Trusted for | Not trusted for |
|---|---|---|
| The user | deciding every change | — |
| The agent (LLM) | proposing tool calls on the user's behalf | agreeing to a write; its arguments, which are all validated |
| The MCP client | showing a confirmation to the user and relaying the answer (elicitation) | — |
| YNAB's API, over HTTPS | the structure and amounts of the data | the text inside it |
| Payee names and memos | nothing: they are written by banks, merchants and anyone who can pay the user | any instruction they contain |
| PyPI's answer to the update check | a plain version number | any other text, which never reaches the agent |
| The local network and other programs | nothing | reaching the HTTP transport |

### Secure design principles

- **Fail-safe defaults.** Read-only unless `AVENIR_MCP_WRITE=1`; stdio, with no port,
  unless HTTP is asked for; HTTP on `127.0.0.1`, and never without a token: a
  random one when none is set; an unknown argument is refused, not ignored (`model.Model`).
- **Complete mediation.** The write gate hides write tools from the list and from calls
  alike (`app._WriteGate`). Every confirmed write goes through one path (`confirm.py`).
  Every request to YNAB goes through `client._request`, which checks each path segment
  first.
- **Separation of privilege.** The agent proposes; the user confirms. With
  `AVENIR_MCP_REQUIRE_ELICITATION=1`, only the user's answer in the client confirms,
  and no code exists that an agent could relay.
- **Least privilege.** Write tools exist only when enabled. The journal stores
  identifiers, never payees, memos or transaction amounts. The CI workflows start with
  no permission (`permissions: {}`) and grant each job only what it needs.
- **Economy of mechanism.** Three runtime dependencies; pure logic kept apart from the
  two modules with side effects (see `ARCHITECTURE.md` in the repository).
- **Open design.** No protection relies on the code being secret.
- **Psychological acceptability.** A preview in plain words before every confirmed
  write, and `undo_operation` after.

### Common weaknesses countered

| Weakness | Countermeasure | Code | Tests |
|---|---|---|---|
| Prompt injection through bank text (OWASP LLM01) | text and names shown on one line, without control, zero-width or direction characters, cut at 80 characters; the server's instructions say it is data; a write needs the user's confirmation | `text.untrusted`, `text.one_line`, `confirm.ONLY_THE_USER` | `test_text.py`, `test_protocol_writes.py::test_bank_text_cannot_forge_lines_in_the_question`, the `*_cannot_forge_lines_*` tests of each write tool, `test_evals.py::test_classify_fails_if_the_agent_obeys_a_memo` |
| Improper input validation (CWE-20) | every argument checked against its schema before any request (an allowlist: unknown fields refused); amounts finite and within a billion; page sizes and counts bounded; months and cursors in their format; text without NUL and within YNAB's lengths | `model.Model`, `amounts.Amount`, `app.check_month`, `text.YnabText` | `test_properties.py`, `test_protocol_bounds.py`, `test_server.py::test_month_tools_reject_a_malformed_month_with_a_way_forward`, `test_protocol_split.py` |
| Path manipulation in requests to YNAB (CWE-22, CWE-918) | each path segment must be a plain id: no slash, dot segment, query or escape | `client._url` | `test_client.py::test_ids_that_would_change_the_request_are_refused` |
| Cleartext transmission of the token (CWE-319) | `https://` required for YNAB's URL; plain HTTP only to this machine | `client._base_url` | `test_client.py::test_api_url_never_sends_the_token_in_clear` |
| Secrets in logs, output or the repository (CWE-532, CWE-798) | the token is a `SecretStr`, shown as a mask; logs carry no financial data; gitleaks and a hygiene test scan the repository | `client._api_key`, `server.main`, `http_auth.py` | `test_http.py::test_the_token_never_shows_when_printed_or_logged`, `test_logging.py::test_logs_hold_no_financial_data`, `test_hygiene.py` |
| Incorrect permissions on sensitive files (CWE-732) | a token file readable by others is refused; the journal is created with mode 0600 | `client._api_key`, `journal.Journal._append` | `test_client.py::test_token_file_readable_by_others_is_refused`, `test_journal.py::test_journal_file_is_private_and_holds_no_amounts_or_names` |
| Missing authentication, DNS rebinding (CWE-306, CWE-350) | `Host` and `Origin` must name this machine; a bearer token on every request, compared in constant time: `AVENIR_MCP_HTTP_TOKEN`, or a random one made at start-up | `server.http_options`, `http_auth.BearerToken` | `test_http.py`, `test_properties.py::test_any_headers_are_refused_without_the_exact_token` |
| Replay of a confirmation (CWE-294) | a code is random, single-use, valid ten minutes, and bound to a SHA-256 fingerprint of the exact preview | `writes.Confirmations`, `writes.fingerprint` | `test_writes.py`, `test_protocol_writes.py::test_answer_to_an_outdated_preview_is_refused` |
| Undo overwriting a later change (CWE-362) | undo leaves alone what changed since the operation | `tools_undo.py` | `test_protocol_writes.py::test_undo_leaves_alone_what_was_changed_since`, and the undo tests of `test_protocol_budget.py`, `test_protocol_flags.py`, `test_protocol_move.py`, `test_protocol_targets.py` |
| Uncontrolled resource consumption (CWE-400) | a timeout on every request; at most 180 requests an hour, every try counted; at most three tries, and only for a read or for a request that never left; no retry after a 429, nor after a write that has been sent | `client.Pace`, `client._TIMEOUT`, `retry.decide` | `test_client.py::test_a_429_is_not_retried_and_pauses_every_request`, `test_client.py::test_requests_stop_short_of_ynabs_limit`, `test_retry.py`, `test_client_retry.py::test_every_try_takes_a_request_from_the_hours_budget` |
| Untrusted data read from a file (CWE-502) | the journal is plain JSON read into strict models; a damaged line is named, never executed | `journal.Journal` | `test_journal.py`, `test_properties.py::test_a_damaged_journal_says_which_line_to_fix` |
| Command injection, risky calls (CWE-78) | no shell, no `eval`, no `pickle` in the package; bandit's rules (ruff `S`) fail the build on a risky pattern | `pyproject.toml` | `just lint` |
| Vulnerable or malicious dependencies (OWASP A06, A08) | dependencies locked with hashes in `uv.lock`; pip-audit on every change, and `npm audit` on the documentation site's dependencies; Renovate waits seven days before proposing a release (the weekly lock file refresh is exempt during early development); actions pinned by commit; zizmor audits the workflows; CodeQL (Python, the site's JavaScript, the workflows) and the OpenSSF Scorecard on the public repository; attested releases (see above) | `uv.lock`, `renovate.json`, `.github/workflows/` | the `quality`, `docs`, `codeql` and `scorecard` workflows |

Beyond these: mypy checks types in strict mode, the tests cover every line and branch,
mutation testing checks that they notice changes to the logic, and a nightly job fuzzes
the Hypothesis properties with 200,000 examples each.

### Security review

The code was last reviewed against this assurance case on 2026-10-01, for version
0.3.0: the scope, the method, the findings with their severity and status, and the
risk that remains are in
[SECURITY-REVIEW.md](https://github.com/mathbeal/avenir-mcp/blob/main/SECURITY-REVIEW.md).

### Residual risk

- A client without elicitation leaves the confirmation code to the agent, and a model
  can still be misled into using it (see [Scope](#scope)). Use a client that supports
  elicitation, with `AVENIR_MCP_REQUIRE_ELICITATION=1`.
- `approve_transactions` given ids and `import_transactions` act without a preview.
- The YNAB token cannot be narrowed to read-only access.
- Over HTTP, traffic on `127.0.0.1` is not encrypted.
