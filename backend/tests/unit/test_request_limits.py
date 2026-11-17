from __future__ import annotations

import asyncio

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
