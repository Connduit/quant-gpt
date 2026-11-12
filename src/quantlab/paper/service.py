"""Bounded reconnecting polling service; controls are durable queued requests."""

import json
import signal
import time
from datetime import UTC, datetime

from quantlab.paper.feeds import FeedRateLimited, FeedUnavailable


def run_service(runtime, feed, strategies, *, poll_seconds=2, max_failures=5, max_polls=None):
    if poll_seconds < 1 or not 1 <= max_failures <= 100:
        raise ValueError("Positive bounded polling/reconnect settings required")
    stopped = False

    def stop(signum, frame):
        nonlocal stopped
        stopped = True

    previous = {s: signal.signal(s, stop) for s in (signal.SIGINT, signal.SIGTERM)}
    failures = polls = 0
    try:
        while not stopped and (max_polls is None or polls < max_polls):
            for identity, payload in runtime.store.db.execute(
                "SELECT id,payload FROM controls WHERE applied=0 ORDER BY id"
            ).fetchall():
                control = json.loads(payload)
                runtime.control(**control)
                with runtime.store.db:
                    runtime.store.db.execute(
                        "UPDATE controls SET applied=1 WHERE id=?", (identity,)
                    )
                if control["action"] == "stop" and control.get("strategy") is None:
                    stopped = True
            if stopped:
                break
            try:
                events = feed.poll()
                for event in events:
                    runtime.ingest(event, now=datetime.now(UTC))
                    for strategy in strategies:
                        strategy.on_event(runtime, event)
                # Recovery never automatically resumes a suspended strategy.
                runtime.heartbeat(datetime.now(UTC))
                failures = 0
                polls += 1
            except (FeedUnavailable, ValueError, KeyError, TypeError) as exc:
                failures += 1
                runtime.control(
                    "disconnect", reason="feed_or_validation_failure:" + type(exc).__name__
                )
                if failures >= max_failures:
                    raise FeedUnavailable(
                        "Reconnect budget exhausted; execution suspended"
                    ) from exc
                delay = (
                    exc.retry_after if isinstance(exc, FeedRateLimited) else min(30, 2**failures)
                )
                time.sleep(min(30, delay))
                continue
            time.sleep(min(30, poll_seconds))
    finally:
        runtime.control("disconnect", reason="service_shutdown")
        feed.close()
        for s, handler in previous.items():
            signal.signal(s, handler)
