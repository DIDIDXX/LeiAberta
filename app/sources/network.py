"""Small bounded retry policy for transient failures on official public APIs."""
from __future__ import annotations

import time
import urllib.request
from urllib.error import HTTPError, URLError


RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}


def open_with_retry(request, *, timeout: int, attempts: int = 3, base_delay: float = 0.5):
    """Retry a short list/connection of transient failures, never a bad response."""
    if attempts < 1:
        raise ValueError("attempts deve ser pelo menos 1")
    for attempt in range(attempts):
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except HTTPError as exc:
            if exc.code not in RETRYABLE_HTTP_CODES or attempt + 1 >= attempts:
                raise
        except (URLError, TimeoutError, ConnectionError, OSError):
            if attempt + 1 >= attempts:
                raise
        time.sleep(base_delay * (2 ** attempt))
    raise RuntimeError("Retry encerrado sem resposta")
