# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Properties that hold for any input, checked on thousands of generated cases (Hypothesis)."""

from __future__ import annotations

import asyncio
import base64
import random
import tempfile
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import SecretStr

from avenir_mcp import classifier, client, forecast, http_auth, journal, text, triage, writes
from avenir_mcp.amounts import MAX_AMOUNT

# Every amount a tool accepts, in currency units, and the milliunits YNAB stores.
amounts = st.floats(min_value=-MAX_AMOUNT, max_value=MAX_AMOUNT, allow_nan=False)
milliunits = st.integers(min_value=-MAX_AMOUNT * 1000, max_value=MAX_AMOUNT * 1000)


# ---------------------------------------------------------------------------
# Amounts
# ---------------------------------------------------------------------------


@given(milliunits)
def test_milliunits_survive_the_way_through_currency_units(value: int) -> None:
    """What YNAB stores comes back unchanged after being shown in currency units."""
    assert client.amount_to_milliunit(client.milliunit_to_amount(value)) == value


@given(amounts)
def test_an_amount_is_never_off_by_more_than_half_a_milliunit(amount: float) -> None:
    """Converting to milliunits rounds, it never drifts."""
    assert abs(client.amount_to_milliunit(amount) - amount * 1000) <= 0.5 + abs(amount) * 1e-12


@given(st.sampled_from([float("nan"), float("inf"), float("-inf")]))
def test_a_non_finite_amount_is_refused(amount: float) -> None:
    """NaN and infinities never reach YNAB."""
    with pytest.raises(ValueError, match="finite"):
        client.amount_to_milliunit(amount)


# ---------------------------------------------------------------------------
# Forecast: spreading money over days
# ---------------------------------------------------------------------------


@given(milliunits, st.integers(min_value=1, max_value=31), st.integers(min_value=0, max_value=31))
def test_spreading_keeps_every_cent_and_stays_even(total: int, first: int, span: int) -> None:
    """Spread over days, an amount keeps its whole cents; shares differ by one cent at most."""
    last = min(first + span, 31)
    shares = forecast._spread(total, first, last)  # pylint: disable=protected-access
    if not total:
        assert not shares
        return
    assert sorted(shares) == list(range(first, last + 1))
    assert sum(shares.values()) == total // 10 * 10
    assert all(share % 10 == 0 for share in shares.values())
    assert max(shares.values()) - min(shares.values()) <= 10


def _next_month(label: str) -> str:
    """The month after a YYYY-MM label."""
    year, number = int(label[:4]), int(label[5:])
    return f"{year + 1}-01" if number == 12 else f"{year}-{number + 1:02d}"


@settings(max_examples=200)
@given(
    start=st.integers(min_value=-10_000_000, max_value=10_000_000),
    variable=st.integers(min_value=-5_000_000, max_value=0),
    income=st.integers(min_value=0, max_value=5_000_000),
    today=st.dates(min_value=date(2026, 1, 1), max_value=date(2027, 12, 31)),
    months=st.integers(min_value=0, max_value=6),
)
def test_projected_months_follow_on_and_add_up(
    start: int, variable: int, income: int, today: date, months: int
) -> None:
    """Each month starts where the last ended, and ends at start plus inflows plus outflows."""
    until = today.replace(day=1) + timedelta(days=31 * months)
    projection = forecast.project(
        start_balance=start / 100,
        today=today,
        until=f"{until:%Y-%m}",
        recurring=[],
        variable_monthly=variable / 100,
        monthly_income=income / 100,
        one_offs=[],
    )
    assert projection.months[0].start == start / 100
    labels = [month.month for month in projection.months]
    assert labels[0] == f"{today:%Y-%m}" and labels[-1] == f"{until:%Y-%m}"
    assert all(_next_month(before) == after for before, after in zip(labels, labels[1:]))
    for month in projection.months:
        assert round(month.start + month.inflows + month.outflows, 2) == month.end
        assert month.lowest <= min(month.start, month.end)
    for before, after in zip(projection.months, projection.months[1:]):
        assert after.start == before.end
    shortfalls = [m.month for m in projection.months if m.lowest < 0]
    assert projection.first_shortfall == (shortfalls[0] if shortfalls else None)


# ---------------------------------------------------------------------------
# Pagination cursors
# ---------------------------------------------------------------------------


_WINDOW_DATES = st.none() | st.dates()


@given(st.integers(min_value=0, max_value=10**12), _WINDOW_DATES, _WINDOW_DATES)
def test_a_cursor_gives_back_its_offset_and_window(
    offset: int, since: date | None, until: date | None
) -> None:
    """A cursor issued for an offset and a window leads back to both."""
    cursor = triage._encode_cursor(offset, since, until)  # pylint: disable=protected-access
    assert triage._decode_cursor(cursor) == (offset, since, until)  # pylint: disable=protected-access


def test_a_cursor_outside_the_url_safe_alphabet_is_refused() -> None:
    """A cursor with a character URL-safe Base64 does not use is refused, not decoded around it.

    Python 3.15 warns that such characters will be discarded: a cursor altered by one
    could then decode to another page.
    """
    valid = triage._encode_cursor(12, None, None)  # pylint: disable=protected-access
    with pytest.raises(ValueError, match="next_cursor"):
        triage._decode_cursor(valid[:4] + "////" + valid[4:])  # pylint: disable=protected-access


@given(st.text())
def test_any_other_cursor_is_refused_with_a_way_forward(cursor: str) -> None:
    """Whatever an agent passes as a cursor, the answer is an offset or a clear refusal."""
    try:
        offset, _, _ = triage._decode_cursor(cursor)  # pylint: disable=protected-access
    except ValueError as error:
        assert "next_cursor" in str(error)
    else:
        assert offset >= 0


# ---------------------------------------------------------------------------
# Transfers between accounts
# ---------------------------------------------------------------------------


def _pairs_one_by_one(pending: list[dict[str, Any]]) -> dict[str, str]:
    """The rule written plainly: each outflow takes the first inflow that mirrors it."""
    pairs: dict[str, str] = {}
    for tx in pending:
        if tx["id"] in pairs or tx["amount"] >= 0:
            continue
        for other in pending:
            days = date.fromisoformat(other["date"]) - date.fromisoformat(tx["date"])
            if (
                other["id"] not in pairs
                and other["amount"] == -tx["amount"]
                and other["account_id"] != tx["account_id"]
                and abs(days.days) <= triage.TRANSFER_WINDOW_DAYS
            ):
                pairs[tx["id"]], pairs[other["id"]] = other["id"], tx["id"]
                break
    return pairs


pending_transactions = st.lists(
    st.tuples(
        st.sampled_from([-30000, -12000, 12000, 30000, 45000]),
        st.sampled_from(["acc-1", "acc-2", "acc-3"]),
        st.integers(min_value=0, max_value=10),
    ),
    max_size=40,
).map(
    lambda rows: [
        {
            "id": f"t{i}",
            "amount": amount,
            "account_id": account,
            "date": (date(2026, 9, 1) + timedelta(days=day)).isoformat(),
        }
        for i, (amount, account, day) in enumerate(rows)
    ]
)


@given(pending_transactions)
def test_transfer_pairing_follows_the_plain_rule(pending: list[dict[str, Any]]) -> None:
    """Indexing by amount finds exactly the pairs the one-by-one rule finds, in the same order."""
    found = triage._transfer_pairs(pending)  # pylint: disable=protected-access
    assert found == _pairs_one_by_one(pending)


# ---------------------------------------------------------------------------
# Bank text
# ---------------------------------------------------------------------------


@given(st.one_of(st.none(), st.text()))
def test_bank_text_is_one_short_line_of_visible_characters(raw: str | None) -> None:
    """No line break, control or invisible character survives, and the length is bounded."""
    shown = text.untrusted(raw)
    assert len(shown) <= text.MAX_TEXT
    assert shown == shown.strip()
    assert "  " not in shown
    assert not any(unicodedata.category(ch) in ("Cc", "Cf", "Zl", "Zp") for ch in shown)


@given(st.text())
def test_bank_text_made_safe_stays_the_same_when_made_safe_again(raw: str) -> None:
    """Cleaning is stable: showing a cleaned text again changes nothing."""
    once = text.untrusted(raw)
    assert text.untrusted(once) == once


# ---------------------------------------------------------------------------
# Confirmation codes
# ---------------------------------------------------------------------------


@given(
    st.lists(
        st.dictionaries(st.sampled_from(["id", "to", "amount"]), st.integers(), min_size=1),
        max_size=8,
    ),
    st.randoms(use_true_random=False),
)
def test_a_preview_hashes_the_same_in_any_order(
    changes: list[dict[str, int]], rng: random.Random
) -> None:
    """A code confirms the same changes whatever their order in the list."""
    shuffled = list(changes)
    rng.shuffle(shuffled)
    assert writes.fingerprint("b1", changes) == writes.fingerprint("b1", shuffled)


@given(st.dictionaries(st.text(max_size=5), st.integers(), min_size=1))
def test_a_preview_of_other_changes_hashes_differently(subject: dict[str, int]) -> None:
    """Changing one value of what is confirmed changes the fingerprint."""
    key = next(iter(subject))
    other = {**subject, key: subject[key] + 1}
    assert writes.fingerprint("b1", subject) != writes.fingerprint("b1", other)
    assert writes.fingerprint("b1", subject) != writes.fingerprint("b2", subject)


# ---------------------------------------------------------------------------
# Untrusted input: bank labels, a damaged journal, HTTP headers
# ---------------------------------------------------------------------------


@given(st.text(max_size=300))
def test_any_bank_label_is_normalised_once_and_for_all(label: str) -> None:
    """Whatever a bank writes, normalising never fails and a second pass changes nothing."""
    merchant = classifier.normalize_payee(label)
    assert classifier.normalize_payee(merchant) == merchant
    assert merchant == merchant.upper().strip()


@given(st.binary(max_size=400))
def test_a_damaged_journal_says_which_line_to_fix(content: bytes) -> None:
    """Any bytes in the journal: entries are read, or the error names the file and the line."""
    with tempfile.TemporaryDirectory() as work:
        path = Path(work) / "journal.jsonl"
        path.write_bytes(content)
        try:
            journal.Journal(path).find("b1")
        except ValueError as error:
            assert str(path) in str(error)
            assert "line" in str(error)


_TOKEN = "fuzzed-token-0123456789"


@given(st.lists(st.tuples(st.binary(max_size=40), st.binary(max_size=80)), max_size=6))
def test_any_headers_are_refused_without_the_exact_token(
    headers: list[tuple[bytes, bytes]],
) -> None:
    """Arbitrary header names and values never crash the guard: 401 unless the token is sent."""
    sent: list[dict[str, Any]] = []
    passed: list[bool] = []

    async def app(*_: Any) -> None:
        passed.append(True)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    guard = http_auth.BearerToken(app, SecretStr(_TOKEN))
    scope = {"type": "http", "headers": [(name.lower(), value) for name, value in headers]}
    asyncio.run(guard(scope, receive, send))  # type: ignore[arg-type]
    authorization = next((v for n, v in headers if n.lower() == b"authorization"), b"")
    carries = authorization == f"Bearer {_TOKEN}".encode()
    assert passed == ([True] if carries else [])
    assert carries or sent[0]["status"] == 401


@pytest.mark.parametrize("window", ["20260901:", ":2026-W36-1", "2026-9-1:"])
def test_a_cursor_with_a_non_canonical_date_is_refused(window: str) -> None:
    """Only YYYY-MM-DD is read, so one window has one cursor."""
    cursor = base64.urlsafe_b64encode(f"offset:3:{window}".encode()).decode()
    with pytest.raises(ValueError, match="next_cursor"):
        triage._decode_cursor(cursor)  # pylint: disable=protected-access
