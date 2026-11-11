"""Надёжные обёртки над внешними HTTP-вызовами и LLM."""

from __future__ import annotations

import time
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from support import journal

MAX_ATTEMPTS = 3
BASE_DELAY = 0.5
TIMEOUT = 5


def _path_of(url: str) -> str:
    parsed = urlparse(url)
    return parsed.path or url


def _is_retriable(status: int | str) -> bool:
    if status in {429, "no_response"}:
        return True
    return isinstance(status, int) and 500 <= status <= 599


def read_with_retry(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    *,
    expect_json: bool = True,
) -> dict | None:
    """GET с таймаутом 5 с и до трёх попыток при 429/5xx/обрыве.

    expect_json=False: вернуть {"text": ...} для текстовых ответов
    (например календарь isdayoff.ru).
    """
    params = params or {}
    headers = headers or {}
    delay = BASE_DELAY
    path = _path_of(url)

    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.monotonic()
        response = None
        status: int | str
        try:
            response = requests.get(
                url, params=params, headers=headers, timeout=TIMEOUT,
            )
            status = response.status_code
        except requests.exceptions.RequestException:
            status = "no_response"
        took = time.monotonic() - started
        journal.log_call("GET", path, dict(params), status, attempt, took)

        if response is not None and status == 200:
            if expect_json:
                try:
                    return response.json()
                except ValueError:
                    return None
            return {"text": (response.text or "").strip()}
        if not _is_retriable(status):
            return None
        if attempt < MAX_ATTEMPTS:
            time.sleep(delay)
            delay *= 2
    return None


def write_with_check(
    url: str,
    payload: dict,
    request_id: str | None = None,
    headers: dict | None = None,
) -> dict | None:
    """POST: повторы только при наличии ключа идемпотентности."""
    headers = headers or {}
    body = dict(payload)
    max_attempts = MAX_ATTEMPTS if request_id else 1
    if request_id:
        body["request_id"] = request_id
    delay = BASE_DELAY
    path = _path_of(url)

    for attempt in range(1, max_attempts + 1):
        started = time.monotonic()
        response = None
        status: int | str
        try:
            response = requests.post(
                url, json=body, headers=headers, timeout=TIMEOUT,
            )
            status = response.status_code
        except requests.exceptions.RequestException:
            status = "no_response"
        took = time.monotonic() - started
        journal.log_call("POST", path, dict(body), status, attempt, took)

        if response is not None and status == 200:
            try:
                return response.json()
            except ValueError:
                return None
        if not _is_retriable(status):
            return None
        if attempt < max_attempts:
            time.sleep(delay)
            delay *= 2
    return None


def llm_with_retry(call: Callable[[], Any]) -> Any:
    """Повторяет вызов модели при 429, 5xx и сетевых сбоях."""
    delay = BASE_DELAY
    last_exc: Exception | None = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.monotonic()
        status: int | str = 200
        try:
            result = call()
            took = time.monotonic() - started
            journal.log_call("POST", "/v1/chat/completions", {}, status, attempt, took)
            return result
        except RateLimitError as exc:
            status = 429
            last_exc = exc
        except (APIConnectionError, APITimeoutError) as exc:
            status = "no_response"
            last_exc = exc
        except APIStatusError as exc:
            status = exc.status_code
            last_exc = exc
            took = time.monotonic() - started
            journal.log_call("POST", "/v1/chat/completions", {}, status, attempt, took)
            if not _is_retriable(status):
                raise
            if attempt < MAX_ATTEMPTS:
                time.sleep(delay)
                delay *= 2
            continue
        except Exception:
            # постоянные ошибки модели/кода не ретраим
            raise

        took = time.monotonic() - started
        journal.log_call("POST", "/v1/chat/completions", {}, status, attempt, took)
        if not _is_retriable(status):
            raise last_exc
        if attempt < MAX_ATTEMPTS:
            time.sleep(delay)
            delay *= 2

    if last_exc is not None:
        raise last_exc
    return None
