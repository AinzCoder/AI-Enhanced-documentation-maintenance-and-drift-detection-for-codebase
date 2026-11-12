import os
import re
import time

import requests
from timing import timed
from llm.markdown_response import normalize_markdown_response


OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"
DEFAULT_REQUEST_TIMEOUT = float(
    os.environ.get("OLLAMA_TIMEOUT_SECONDS", "300")
)
DEFAULT_MAX_RETRIES = int(os.environ.get("OLLAMA_MAX_RETRIES", "1"))
MAX_ALLOWED_RETRIES = 1


class OllamaClientError(RuntimeError):
    def __init__(
        self,
        category: str,
        public_message: str,
        status_code: int | None = None
    ):
        super().__init__(public_message)
        self.category = category
        self.public_message = public_message
        self.status_code = status_code


@timed("llm.ollama")
def generate_response(
    prompt: str,
    timeout: float | None = None,
    max_retries: int | None = None
) -> str:
    request_timeout = (
        DEFAULT_REQUEST_TIMEOUT if timeout is None else timeout
    )
    retry_count = DEFAULT_MAX_RETRIES if max_retries is None else max_retries
    if request_timeout <= 0:
        raise ValueError("timeout must be greater than zero.")
    if not 0 <= retry_count <= MAX_ALLOWED_RETRIES:
        raise ValueError(
            f"max_retries must be between 0 and {MAX_ALLOWED_RETRIES}."
        )

    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False
    }

    for attempt in range(retry_count + 1):
        try:
            response = requests.post(
                OLLAMA_URL,
                json=payload,
                timeout=request_timeout
            )
        except requests.Timeout as error:
            if attempt < retry_count:
                time.sleep(0.25 * (attempt + 1))
                continue
            raise OllamaClientError(
                "timeout",
                "Ollama request timed out."
            ) from error
        except requests.ConnectionError as error:
            if attempt < retry_count:
                time.sleep(0.25 * (attempt + 1))
                continue
            raise OllamaClientError(
                "connection",
                "Could not connect to the local Ollama server."
            ) from error
        except requests.RequestException as error:
            raise OllamaClientError(
                "request",
                "Ollama request failed."
            ) from error

        if response.status_code >= 400:
            status_code = response.status_code
            try:
                error_payload = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError):
                error_payload = None
            error_text = (
                error_payload.get("error", "")
                if isinstance(error_payload, dict)
                else ""
            )
            if (
                isinstance(error_text, str)
                and re.search(r"\bmodel\b.*\bnot found\b", error_text, re.I)
            ):
                raise OllamaClientError(
                    "model_unavailable",
                    f"Configured Ollama model '{MODEL_NAME}' is unavailable.",
                    status_code=status_code
                )
            if (
                attempt < retry_count
                and (status_code == 408 or status_code == 429
                     or status_code >= 500)
            ):
                time.sleep(0.25 * (attempt + 1))
                continue
            raise OllamaClientError(
                "http",
                f"Ollama returned HTTP {status_code}.",
                status_code=status_code
            )

        try:
            data = response.json()
        except (ValueError, requests.exceptions.JSONDecodeError) as error:
            raise OllamaClientError(
                "malformed_response",
                "Ollama returned malformed JSON."
            ) from error

        if not isinstance(data, dict):
            raise OllamaClientError(
                "malformed_response",
                "Ollama returned an unexpected response shape."
            )
        response_text = data.get("response")
        if not isinstance(response_text, str):
            raise OllamaClientError(
                "malformed_response",
                "Ollama response is missing text."
            )
        return response_text

    raise OllamaClientError(
        "request",
        "Ollama request failed after retry attempts."
    )

