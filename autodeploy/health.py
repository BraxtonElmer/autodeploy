from __future__ import annotations

import time
from dataclasses import dataclass

import requests


@dataclass
class HealthResult:
    success: bool
    status_code: int | None
    duration_ms: int
    attempts: int
    error: str | None = None


def check(url: str, timeout: int = 30, retries: int = 3) -> HealthResult:
    """GET url, retry up to retries times with 5s between attempts."""
    last_error: str | None = None
    last_status: int | None = None

    for attempt in range(1, retries + 1):
        start = time.monotonic()
        try:
            resp = requests.get(url, timeout=timeout)
            duration_ms = int((time.monotonic() - start) * 1000)
            last_status = resp.status_code
            if resp.status_code == 200:
                return HealthResult(
                    success=True,
                    status_code=resp.status_code,
                    duration_ms=duration_ms,
                    attempts=attempt,
                )
            last_error = f"HTTP {resp.status_code}"
        except requests.exceptions.Timeout:
            duration_ms = int((time.monotonic() - start) * 1000)
            last_error = f"timed out after {timeout}s"
        except requests.exceptions.ConnectionError as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            last_error = f"connection error: {e}"
        except requests.exceptions.RequestException as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            last_error = str(e)

        if attempt < retries:
            time.sleep(5)

    return HealthResult(
        success=False,
        status_code=last_status,
        duration_ms=duration_ms,
        attempts=retries,
        error=last_error,
    )
