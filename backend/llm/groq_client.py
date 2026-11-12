import contextvars
import logging
import math
import os
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from functools import wraps
from pathlib import Path

import groq
from dotenv import dotenv_values

from timing import timed


DEFAULT_MODEL = "openai/gpt-oss-20b"
DEFAULT_TIMEOUT = 120.0
MAX_RETRIES = 1
logger = logging.getLogger("docguard.timing")
_deadline = contextvars.ContextVar("groq_generation_deadline", default=None)


class GroqClientError(RuntimeError):
    def __init__(self, category: str, public_message: str):
        super().__init__(public_message)
        self.category = category
        self.public_message = public_message


def _config_value(name: str, default: str) -> str:
    values = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
    return (os.environ.get(name, values.get(name) or default) or "").strip()


def _positive_number(name: str, default: str) -> float:
    try:
        value = float(_config_value(name, default))
        if math.isfinite(value) and value > 0:
            return value
    except ValueError:
        pass
    raise GroqClientError("configuration", f"{name} must be a positive number.")


def generation_deadline(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        duration = _positive_number("GROQ_GENERATION_DEADLINE_SECONDS", "300")
        token = _deadline.set(time.perf_counter() + duration)
        try:
            return function(*args, **kwargs)
        finally:
            _deadline.reset(token)
    return wrapper


def _settings() -> tuple[str, str, float, int]:
    key = _config_value("GROQ_API_KEY", "")
    if not key:
        raise GroqClientError("authentication", "Groq API key is not configured.")
    model = _config_value("GROQ_MODEL", DEFAULT_MODEL)
    if not re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", model):
        raise GroqClientError("configuration", "Groq model is not configured correctly.")
    timeout = _positive_number("GROQ_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT))
    try:
        tokens = int(_config_value("GROQ_MAX_COMPLETION_TOKENS", "1024"))
    except ValueError as error:
        raise GroqClientError("configuration", "GROQ_MAX_COMPLETION_TOKENS must be between 1 and 65536.") from error
    if not 1 <= tokens <= 65536:
        raise GroqClientError("configuration", "GROQ_MAX_COMPLETION_TOKENS must be between 1 and 65536.")
    return key, model, timeout, tokens


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            seconds = (parsed - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def _rate_limit_kind(error: groq.RateLimitError) -> str:
    details = error.body.get("error", error.body) if isinstance(error.body, dict) else {}
    message = details.get("message", "") if isinstance(details, dict) else ""
    text = message.lower() if isinstance(message, str) else ""
    for token, label in (
        ("tokens per day", "tokens_per_day"), ("tpd", "tokens_per_day"),
        ("requests per day", "requests_per_day"), ("rpd", "requests_per_day"),
        ("tokens per minute", "tokens_per_minute"), ("tpm", "tokens_per_minute"),
        ("requests per minute", "requests_per_minute"), ("rpm", "requests_per_minute"),
    ):
        if re.search(r"\b" + re.escape(token) + r"\b", text):
            return label
    return "unknown"


def _safe_header(headers, name: str) -> str:
    value = headers.get(name, "")
    return value if re.fullmatch(r"[0-9.dhms]+", value, re.IGNORECASE) else "unavailable"


def _rate_limit_message(kind: str, delay: float | None) -> str:
    if kind in {"requests_per_day", "tokens_per_day"}:
        return "Groq's daily quota has been reached. Please try again after the provider resets it."
    if delay is not None:
        return f"Groq is temporarily rate-limited. Please retry in approximately {math.ceil(delay)} seconds."
    return "Groq is rate-limited. Please retry later and check the provider's quota."


@timed("llm.groq")
def generate_response(prompt: str) -> str:
    key, model, timeout, tokens = _settings()
    deadline = _deadline.get()
    if deadline is None:
        deadline = time.perf_counter() + _positive_number("GROQ_GENERATION_DEADLINE_SECONDS", "300")
    started = time.perf_counter()
    for attempt in range(MAX_RETRIES + 1):
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            raise GroqClientError("deadline", "Generation deadline reached. Try generating fewer methods.")
        try:
            with groq.Groq(api_key=key, timeout=min(timeout, remaining), max_retries=0) as client:
                options = {"reasoning_effort": "low"} if model == DEFAULT_MODEL else {}
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=tokens,
                    **options,
                )
        except groq.AuthenticationError as error:
            raise GroqClientError("authentication", "Groq authentication failed; check the backend API key.") from error
        except groq.RateLimitError as error:
            headers = error.response.headers
            delay = _retry_after(headers.get("retry-after"))
            kind = _rate_limit_kind(error)
            if kind == "unknown" and headers.get("x-ratelimit-remaining-requests") == "0":
                kind = "requests_per_day"
            details = error.body.get("error", error.body) if isinstance(error.body, dict) else {}
            message = details.get("message", "") if isinstance(details, dict) else ""
            oversized = isinstance(message, str) and "request too large" in message.lower()
            logger.warning(
                "llm.groq status=429 model=%s category=%s retry_after_seconds=%s "
                "remaining_requests=%s remaining_tokens=%s reset_requests=%s reset_tokens=%s duration_seconds=%.3f attempt=%d",
                model, kind, delay,
                _safe_header(headers, "x-ratelimit-remaining-requests"),
                _safe_header(headers, "x-ratelimit-remaining-tokens"),
                _safe_header(headers, "x-ratelimit-reset-requests"),
                _safe_header(headers, "x-ratelimit-reset-tokens"),
                time.perf_counter() - started, attempt + 1,
            )
            if oversized:
                raise GroqClientError("request_too_large", "The documentation request is too large. Try generating fewer methods.") from error
            wait = delay if delay is not None else random.uniform(1.0, 2.0) * (2 ** attempt)
            remaining = deadline - time.perf_counter()
            if (
                attempt == MAX_RETRIES
                or kind in {"requests_per_day", "tokens_per_day"}
                or wait >= remaining
            ):
                raise GroqClientError("rate_limit", _rate_limit_message(kind, delay)) from error
            time.sleep(max(wait, 0.1))
            continue
        except groq.APITimeoutError as error:
            raise GroqClientError("timeout", "Groq request timed out. Please retry.") from error
        except groq.APIConnectionError as error:
            raise GroqClientError("connection", "Unable to connect to Groq. Please check your connection and retry.") from error
        except groq.NotFoundError as error:
            raise GroqClientError("model_unavailable", "The configured Groq model is unavailable.") from error
        except groq.APIStatusError as error:
            details = error.body.get("error", error.body) if isinstance(error.body, dict) else {}
            code = details.get("code") if isinstance(details, dict) else None
            if error.status_code == 400 and code in {"model_not_found", "model_decommissioned"}:
                raise GroqClientError("model_unavailable", "The configured Groq model is unavailable.") from error
            if error.status_code == 413 or code in {"context_length_exceeded", "request_too_large"}:
                raise GroqClientError("request_too_large", "The documentation request is too large. Try generating fewer methods.") from error
            raise GroqClientError("http", f"Groq request failed (HTTP {error.status_code}).") from error
        except groq.APIError as error:
            raise GroqClientError("request", "Groq request failed.") from error
        if not response.choices:
            raise GroqClientError("empty_response", "Groq returned an empty response.")
        text = response.choices[0].message.content
        if not isinstance(text, str) or not text.strip():
            raise GroqClientError("empty_response", "Groq returned an empty response.")
        if response.choices[0].finish_reason == "length":
            raise GroqClientError("incomplete_response", "Groq returned an incomplete response. Increase GROQ_MAX_COMPLETION_TOKENS or generate fewer methods.")
        if response.usage:
            logger.info(
                "llm.groq model=%s tokens_prompt=%s tokens_completion=%s tokens_total=%s retries=%d",
                model, response.usage.prompt_tokens, response.usage.completion_tokens,
                response.usage.prompt_tokens + response.usage.completion_tokens, attempt,
            )
        return text
    raise GroqClientError("request", "Groq request failed.")
