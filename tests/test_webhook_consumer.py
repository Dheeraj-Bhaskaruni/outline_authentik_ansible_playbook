#!/usr/bin/env python3
"""Unit test for the webhook signature check (no network)."""
import hashlib
import hmac
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("OUTLINE_WEBHOOK_SECRET", "x" * 32)
spec = importlib.util.spec_from_file_location("consumer", ROOT / "files/automation/webhook_consumer.py")
consumer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(consumer)


def sign(secret: bytes, body: bytes, t: int) -> str:
    return f"t={t},s=" + hmac.new(secret, f"{t}.".encode() + body, hashlib.sha256).hexdigest()


def main() -> None:
    secret = b"s3cret" * 6
    body = b'{"event":"documents.publish","payload":{"id":"abc"}}'
    now = 1_700_000_000_000
    good = sign(secret, body, now)
    assert consumer.verify(good, body, secret, now_ms=now)
    assert consumer.verify(good, body, secret, now_ms=now + 60_000)          # within window
    assert not consumer.verify(good, body, secret, now_ms=now + 600_000)     # replayed later
    assert not consumer.verify(good, body + b" ", secret, now_ms=now)        # body tampered
    assert not consumer.verify(good, body, b"other", now_ms=now)             # wrong secret
    assert not consumer.verify(sign(secret, body, now)[:-1] + "0", body, secret, now_ms=now)
    assert not consumer.verify("garbage", body, secret, now_ms=now)
    assert not consumer.verify("", body, secret, now_ms=now)
    print("PASS: webhook signature verification (valid, replay, tamper, wrong secret, malformed)")


if __name__ == "__main__":
    main()
