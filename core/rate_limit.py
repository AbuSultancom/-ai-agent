"""Rate Limiting — token-bucket per IP using Flask-Limiter or fallback."""

import logging
import threading
import time
from collections import defaultdict

logger = logging.getLogger(__name__)


class _TokenBucket:
    def __init__(self, rate: float, capacity: int):
        self.rate = rate        # tokens added per second
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
            self._last = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


_buckets: dict[str, _TokenBucket] = defaultdict(
    lambda: _TokenBucket(rate=1.0, capacity=60)   # 60 req/min per IP
)
_buckets_lock = threading.Lock()


def check_rate_limit(ip: str, tokens: int = 1) -> bool:
    with _buckets_lock:
        bucket = _buckets[ip]
    return bucket.consume(tokens)


def get_limiter(app=None):
    """Return a Flask-Limiter instance if available, else None."""
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        limiter = Limiter(
            app=app,
            key_func=get_remote_address,
            default_limits=["200 per minute", "2000 per hour"],
            storage_uri="memory://",
        )
        logger.info("Flask-Limiter initialized")
        return limiter
    except ImportError:
        logger.warning("flask-limiter not installed; using built-in token bucket")
        return None


def rate_limit_middleware(app):
    """Attach rate limiting to Flask app via before_request."""
    from flask import request, jsonify

    @app.before_request
    def _check():
        ip = request.remote_addr or "unknown"
        if not check_rate_limit(ip):
            return jsonify({"error": "Rate limit exceeded. Try again in a moment."}), 429
