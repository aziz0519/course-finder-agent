"""Small ASGI request-body limit for the JSON API."""

from __future__ import annotations

from collections import deque

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    """Reject API bodies larger than the configured limit, including chunked bodies."""

    def __init__(self, app: ASGIApp, max_bytes: int = 1_048_576) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", ()))
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                if int(raw_length) > self.max_bytes:
                    await self._reject(send)
                    return
            except ValueError:
                await self._reject(send)
                return

        buffered: deque[Message] = deque()
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                buffered.append(message)
                break
            if message["type"] != "http.request":
                buffered.append(message)
                continue
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await self._reject(send)
                return
            buffered.append(message)
            if not message.get("more_body", False):
                break

        async def replay_receive() -> Message:
            if buffered:
                return buffered.popleft()
            return await receive()

        await self.app(scope, replay_receive, send)

    @staticmethod
    async def _reject(send: Send) -> None:
        body = b'{"detail":"Request body too large."}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
