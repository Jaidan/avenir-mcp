# SPDX-FileCopyrightText: 2026 The avenir-mcp contributors
# SPDX-License-Identifier: MIT

"""Shared pytest fixtures for ynab tests."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from hypothesis import HealthCheck, settings

from avenir_mcp import client, server, sync

# `just fuzz`: the same properties, many more examples each. What fails is saved in
# .hypothesis/ and replayed, minimised, by the next ordinary run.
settings.register_profile(
    "fuzz",
    max_examples=int(os.getenv("AVENIR_MCP_FUZZ_EXAMPLES", "50000")),
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


@pytest.fixture(autouse=True)
def reset_cache() -> None:
    """Reset the in-memory delta-sync cache before every test."""
    sync.clear()
    client.PACE.reset()


@pytest.fixture(autouse=True)
def no_update_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never ask PyPI from a test: main() would otherwise check for a newer release."""
    monkeypatch.setenv("AVENIR_MCP_NO_UPDATE_CHECK", "1")


LOOPBACK = {"127.0.0.1", "::1", "localhost"}
"""The stand-in YNAB of `evals/` is a real HTTP server on this machine: it stays allowed."""


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse any request leaving this machine: a test must not depend on someone's server.

    httpx is the only client the package uses, so replacing its two real transports
    closes the way out, whichever call reaches them: httpx.get, a Client, an AsyncClient,
    or a default argument bound at import time. A stand-in transport (ASGITransport,
    MockTransport) is untouched, and so are the sockets asyncio opens for itself.

    no_proxy also spares httpx the lookup of the machine's proxy settings, which a test
    must not depend on either. On macOS that lookup calls a system framework which
    aborts the process when it runs in a forked child: `just mutate` forks for every
    mutant, and an abort there is reported as a mutant nobody could judge.
    """
    monkeypatch.setenv("no_proxy", "*")
    send = httpx.HTTPTransport.handle_request
    send_async = httpx.AsyncHTTPTransport.handle_async_request

    def check(request: httpx.Request) -> None:
        if request.url.host not in LOOPBACK:
            raise RuntimeError(
                f"A test tried to reach {request.url} off this machine. Pass a stand-in"
                " for the getter, the client or the transport instead of the real one."
            )

    def guarded(self: Any, request: httpx.Request) -> httpx.Response:
        check(request)
        return send(self, request)

    async def guarded_async(self: Any, request: httpx.Request) -> httpx.Response:
        check(request)
        return await send_async(self, request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", guarded)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", guarded_async)


@pytest.fixture(autouse=True)
def writes_enabled() -> Iterator[None]:
    """Start every test with write tools exposed, whatever an earlier test configured."""
    server.configure(enable_writes=True)
    yield
    server.configure(enable_writes=True)
