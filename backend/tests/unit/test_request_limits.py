from __future__ import annotations

import asyncio

import pytest

from app.api.request_limits import RequestBodyLimitMiddleware


def test_chunked_api_body_is_rejected_before_application() -> None:
    called = False
    sent = []
    chunks = iter(
        [
            {"type": "http.request", "body": b"x" * 8, "more_body": True},
            {"type": "http.request", "body": b"y", "more_body": False},
        ]
    )

    async def app(scope, receive, send):
        nonlocal called
        called = True

    async def receive():
        return next(chunks)

    async def send(message):
        sent.append(message)

    async def run() -> None:
        middleware = RequestBodyLimitMiddleware(app, max_bytes=8)
        await middleware(
            {"type": "http", "path": "/api/v1/chat/sessions", "headers": []},
            receive,
            send,
        )

    asyncio.run(run())

    assert not called
    assert sent[0]["status"] == 413
    assert b"too large" in sent[1]["body"]


@pytest.mark.parametrize("size,disconnect", [(4096, False), (4097, False), (4096, True)])
def test_many_tiny_chunks_at_boundary_and_disconnect(size, disconnect) -> None:
    received = []
    sent = []
    consumed = 0

    async def receive():
        nonlocal consumed
        consumed += 1
        if consumed > size:
            return {"type": "http.disconnect"}
        return {
            "type": "http.request",
            "body": bytes([consumed % 256]),
            "more_body": disconnect or consumed < size,
        }

    async def app(scope, receive, send):
        message = await receive()
        received.append(message)
        if disconnect:
            received.append(await receive())

    async def send(message):
        sent.append(message)

    asyncio.run(
        RequestBodyLimitMiddleware(app, max_bytes=4096)(
            {"type": "http", "path": "/api/v1/chat/sessions", "headers": []},
            receive,
            send,
        )
    )
    if size > 4096:
        assert not received
        assert sent[0]["status"] == 413
    else:
        assert received[0] == {
            "type": "http.request",
            "body": bytes(i % 256 for i in range(1, size + 1)),
            "more_body": disconnect,
        }
        if disconnect:
            assert received[1] == {"type": "http.disconnect"}
