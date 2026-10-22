#!/usr/bin/env python3
"""Outline webhook consumer: the seat for your bots.

Verifies every delivery's HMAC signature, rejects replays, then hands the
event to handle(). Standard library only; runs inside the Outline Compose
network and is never published on the host.

Signature format (Outline): header ``Outline-Signature: t=<ms>,s=<hex>`` where
``s`` is HMAC-SHA256 over ``f"{t}.{body}"`` with the subscription secret.
"""
import hashlib
import hmac
import json
import logging
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SECRET = os.environ.get("OUTLINE_WEBHOOK_SECRET", "").encode()
REPLAY_WINDOW_SECONDS = int(os.environ.get("REPLAY_WINDOW_SECONDS", "300"))
MAX_BODY = 1_000_000

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("automation")


def verify(header: str, body: bytes, secret: bytes, now_ms: int | None = None) -> bool:
    """Return True when the Outline-Signature header matches the body."""
    try:
        parts = dict(part.split("=", 1) for part in header.split(","))
        timestamp = int(parts["t"])
        provided = parts["s"]
    except (ValueError, KeyError, AttributeError):
        return False
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    if abs(now_ms - timestamp) > REPLAY_WINDOW_SECONDS * 1000:
        return False
    expected = hmac.new(secret, f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


def handle(event: dict) -> None:
    """Your bot logic. Replace or extend; keep it quick (Outline waits for 2xx).

    Examples: on ``comments.create`` call an agent and reply through the API;
    on ``documents.publish`` index the document somewhere else.
    """
    log.info("event=%s actor=%s model=%s", event.get("event"), event.get("actorId"),
             (event.get("payload") or {}).get("id"))


class Handler(BaseHTTPRequestHandler):
    server_version = "outline-automation/1"

    def do_POST(self) -> None:  # noqa: N802 (http.server naming)
        if self.path != "/outline":
            return self._reply(404)
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY:
            return self._reply(413)
        body = self.rfile.read(length)
        signature = self.headers.get("Outline-Signature", "")
        if not SECRET or not verify(signature, body, SECRET):
            log.warning("rejected delivery: bad signature")
            return self._reply(401)
        try:
            event = json.loads(body)
        except ValueError:
            return self._reply(400)
        try:
            handle(event)
        except Exception:  # noqa: BLE001 - never let a bot bug fail the webhook
            log.exception("handler error")
        return self._reply(200)

    def do_GET(self) -> None:  # noqa: N802
        self._reply(200 if self.path == "/health" else 404)

    def log_message(self, *_args) -> None:  # quiet default access log
        return

    def _reply(self, status: int) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()


def main() -> None:
    if not SECRET:
        log.error("OUTLINE_WEBHOOK_SECRET is not set")
        sys.exit(1)
    port = int(os.environ.get("LISTEN_PORT", "8080"))
    log.info("listening on :%d", port)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
