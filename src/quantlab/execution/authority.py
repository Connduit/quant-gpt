"""Sandbox capabilities are signed and bound to exact intents; LIVE is unavailable."""

import hashlib
import hmac
import json
from datetime import timedelta
from enum import StrEnum

from quantlab.discovery.common import fingerprint
from quantlab.paper.events import instant


class ExecutionMode(StrEnum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    BROKER_SANDBOX = "BROKER_SANDBOX"
    LIVE = "LIVE"


LIVE_ENABLED = False


class ExecutionDenied(PermissionError):
    pass


class Authority:
    def __init__(self, secret, *, mode, account_id):
        self.mode = ExecutionMode(mode)
        self.account_id = account_id
        if self.mode == ExecutionMode.LIVE:
            raise ExecutionDenied(
                "LIVE is disabled in this build; no configuration or agent can enable it"
            )
        if self.mode != ExecutionMode.BROKER_SANDBOX:
            raise ExecutionDenied("Broker operations require explicit BROKER_SANDBOX mode")
        if not isinstance(secret, bytes) or len(secret) < 32 or not account_id:
            raise ValueError("Private authorization key and exact sandbox account required")
        self._secret = secret

    def sign(self, body):
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        return {
            "body": body,
            "signature": hmac.new(self._secret, encoded, hashlib.sha256).hexdigest(),
        }

    def verify(self, signed, *, now):
        body = signed.get("body", {})
        expected = self.sign(body)["signature"]
        if not hmac.compare_digest(expected, str(signed.get("signature", ""))):
            raise ExecutionDenied("Authorization signature invalid")
        if body.get("mode") != self.mode or body.get("account_id") != self.account_id:
            raise ExecutionDenied("Authorization mode/account mismatch")
        if instant(body["expires_at"]) <= instant(now):
            raise ExecutionDenied("Authorization expired")
        return body

    def permit(self, operation, payload, *, now):
        if operation not in ("submit", "cancel", "replace"):
            raise ExecutionDenied("Unknown broker capability")
        return self.sign(
            {
                "operation": operation,
                "payload_hash": fingerprint(payload),
                "account_id": self.account_id,
                "mode": self.mode,
                "expires_at": (instant(now) + timedelta(seconds=30)).isoformat(),
            }
        )

    def require(self, permit, operation, payload, *, now):
        body = self.verify(permit, now=now)
        if body.get("operation") != operation or body.get("payload_hash") != fingerprint(payload):
            raise ExecutionDenied("Capability does not authorize this exact operation")
