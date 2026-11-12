from types import SimpleNamespace

import groq
import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from documentation_generation import full_documentation_generator as generator
from llm import groq_client
from rag import llm_generator


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setattr(groq_client, "dotenv_values", lambda _path: {})
    monkeypatch.setenv("GROQ_API_KEY", "test-secret-key")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-20b")
    monkeypatch.setenv("GROQ_TIMEOUT_SECONDS", "120")
    monkeypatch.setenv("GROQ_GENERATION_DEADLINE_SECONDS", "300")
    monkeypatch.setenv("GROQ_MAX_COMPLETION_TOKENS", "1024")
    monkeypatch.setattr(groq_client.time, "sleep", lambda _seconds: None)


def fake_client(monkeypatch, response=None, failure=None):
    captured = {}

    class Client:
        def __init__(self, **kwargs):
            captured["config"] = kwargs
            self.chat = SimpleNamespace(completions=self)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def create(self, **kwargs):
            captured["request"] = kwargs
            if failure:
                raise failure
            return response

    monkeypatch.setattr(groq_client.groq, "Groq", Client)
    return captured


def completion(content="documentation", reason="stop"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason=reason)],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=7),
    )


def status_error(cls, status):
    response = httpx.Response(status, request=httpx.Request("POST", "https://example.test"))
    return cls("test-secret-key provider detail", response=response, body={"error": {"code": "model_not_found"}})


def test_groq_chat_configuration_and_prompt(monkeypatch, caplog):
    captured = fake_client(monkeypatch, completion())
    with caplog.at_level("INFO", logger="docguard.timing"):
        assert groq_client.generate_response("private source") == "documentation"
    assert captured["config"] == {"api_key": "test-secret-key", "timeout": 120.0, "max_retries": 0}
    assert captured["request"] == {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": "private source"}],
        "max_completion_tokens": 1024,
        "reasoning_effort": "low",
    }
    assert "test-secret-key" not in caplog.text
    assert "private source" not in caplog.text
    assert "tokens_prompt=5" in caplog.text


@pytest.mark.parametrize(
    "failure, category",
    [
        (status_error(groq.AuthenticationError, 401), "authentication"),
        (status_error(groq.RateLimitError, 429), "rate_limit"),
        (status_error(groq.NotFoundError, 404), "model_unavailable"),
        (status_error(groq.BadRequestError, 400), "model_unavailable"),
        (status_error(groq.InternalServerError, 500), "http"),
        (groq.APITimeoutError(request=httpx.Request("POST", "https://example.test")), "timeout"),
        (groq.APIConnectionError(request=httpx.Request("POST", "https://example.test")), "connection"),
    ]
)
def test_error_classification_is_secret_safe(monkeypatch, failure, category):
    fake_client(monkeypatch, failure=failure)
    with pytest.raises(groq_client.GroqClientError) as error:
        groq_client.generate_response("prompt")
    assert error.value.category == category
    assert "test-secret-key" not in str(error.value)


@pytest.mark.parametrize("response", [completion(" "), completion(None), SimpleNamespace(choices=[], usage=None)])
def test_empty_response_is_rejected(monkeypatch, response):
    fake_client(monkeypatch, response=response)
    with pytest.raises(groq_client.GroqClientError, match="empty response"):
        groq_client.generate_response("prompt")


def test_truncated_response_is_rejected(monkeypatch):
    fake_client(monkeypatch, completion("partial", "length"))
    with pytest.raises(groq_client.GroqClientError, match="incomplete"):
        groq_client.generate_response("prompt")


def test_missing_key_and_invalid_timeout(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    with pytest.raises(groq_client.GroqClientError, match="not configured"):
        groq_client.generate_response("prompt")
    monkeypatch.setenv("GROQ_API_KEY", "test-secret-key")
    monkeypatch.setenv("GROQ_TIMEOUT_SECONDS", "nan")
    with pytest.raises(groq_client.GroqClientError, match="positive number"):
        groq_client.generate_response("prompt")


def test_analysis_succeeds_without_key_or_network(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    (tmp_path / "A.java").write_text("class A { int a() { return 1; } }", encoding="utf-8")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("Analysis must not invoke Groq.")

    monkeypatch.setattr(groq_client, "generate_response", forbidden)
    monkeypatch.setattr(groq_client.groq, "Groq", forbidden)
    response = TestClient(main.app).post("/analyze/full", json={"repository_path": str(tmp_path)})
    assert response.status_code == 200
    assert response.json()["summary"]["method_count"] == 1


@pytest.mark.parametrize("status, expected_calls", [(503, 1), (429, 2), (401, 1)])
def test_sdk_retry_policy_is_bounded(monkeypatch, status, expected_calls):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={"error": {"message": "provider failure"}}, request=request)

    real_groq = groq.Groq

    def build_client(**kwargs):
        return real_groq(
            **kwargs,
            http_client=httpx.Client(transport=httpx.MockTransport(handle))
        )

    monkeypatch.setattr(groq_client.groq, "Groq", build_client)
    with pytest.raises(groq_client.GroqClientError):
        groq_client.generate_response("private source")
    assert len(calls) == expected_calls


def rate_error(message, headers=None):
    response = httpx.Response(429, headers=headers, request=httpx.Request("POST", "https://example.test"))
    return groq.RateLimitError("private provider details", response=response, body={"error": {"message": message}})


def test_retry_after_then_success(monkeypatch, caplog):
    calls = []
    waits = []
    error = rate_error("Rate limit reached for tokens per minute", {
        "retry-after": "3",
        "x-ratelimit-remaining-tokens": "10",
        "x-ratelimit-remaining-requests": "999",
        "x-ratelimit-reset-tokens": "3.5s",
    })
    fake_client(monkeypatch, failure=error)
    class Client:
        def __init__(self, **kwargs):
            assert kwargs["max_retries"] == 0
            self.chat = SimpleNamespace(completions=self)
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def create(self, **kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise error
            return completion()
    monkeypatch.setattr(groq_client.groq, "Groq", Client)
    monkeypatch.setattr(groq_client.time, "sleep", waits.append)
    with caplog.at_level("INFO", logger="docguard.timing"):
        assert groq_client.generate_response("private source") == "documentation"
    assert waits == [3]
    assert len(calls) == 2
    assert "tokens_per_minute" in caplog.text
    assert "remaining_tokens=10" in caplog.text
    assert "private source" not in caplog.text
    assert "test-secret-key" not in caplog.text


def test_no_retry_after_uses_jitter_without_inventing_user_delay(monkeypatch):
    fake_client(monkeypatch, failure=rate_error("rate limited"))
    waits = []
    monkeypatch.setattr(groq_client.random, "uniform", lambda _a, _b: 1.5)
    monkeypatch.setattr(groq_client.time, "sleep", waits.append)
    with pytest.raises(groq_client.GroqClientError, match="retry later"):
        groq_client.generate_response("prompt")
    assert waits == [1.5]


@pytest.mark.parametrize("limit", ["tokens per day", "requests per day"])
def test_daily_limit_never_retries(monkeypatch, limit):
    fake_client(monkeypatch, failure=rate_error(limit, {"retry-after": "10"}))
    waits = []
    monkeypatch.setattr(groq_client.time, "sleep", waits.append)
    with pytest.raises(groq_client.GroqClientError, match="daily quota"):
        groq_client.generate_response("prompt")
    assert waits == []


def test_retry_after_exceeding_deadline_is_returned(monkeypatch):
    fake_client(monkeypatch, failure=rate_error("requests per minute", {"retry-after": "350"}))
    waits = []
    monkeypatch.setattr(groq_client.time, "sleep", waits.append)
    with pytest.raises(groq_client.GroqClientError, match="350 seconds"):
        groq_client.generate_response("prompt")
    assert waits == []


def test_oversized_request_is_actionable(monkeypatch):
    response = httpx.Response(413, request=httpx.Request("POST", "https://example.test"))
    error = groq.APIStatusError("private", response=response, body={})
    fake_client(monkeypatch, failure=error)
    with pytest.raises(groq_client.GroqClientError, match="too large") as result:
        groq_client.generate_response("prompt")
    assert result.value.category == "request_too_large"


def test_oversized_429_does_not_retry(monkeypatch):
    fake_client(monkeypatch, failure=rate_error("Request too large for model", {"retry-after": "5"}))
    waits = []
    monkeypatch.setattr(groq_client.time, "sleep", waits.append)
    with pytest.raises(groq_client.GroqClientError, match="too large"):
        groq_client.generate_response("prompt")
    assert waits == []


def test_expired_generation_deadline_skips_network(monkeypatch):
    monkeypatch.setattr(groq_client.groq, "Groq", lambda **_kwargs: pytest.fail("No network call expected"))
    token = groq_client._deadline.set(groq_client.time.perf_counter() - 1)
    try:
        with pytest.raises(groq_client.GroqClientError, match="deadline"):
            groq_client.generate_response("prompt")
    finally:
        groq_client._deadline.reset(token)


def test_change_suggestion_uses_groq_and_preserves_prompt(monkeypatch):
    prompts = []
    monkeypatch.setattr(llm_generator, "generate_response", lambda prompt: prompts.append(prompt) or " result ")
    assert llm_generator.generate_documentation_suggestion(
        "Example", "value", "method_added", "int value() { return 1; }", "Existing"
    ) == "result"
    assert "int value() { return 1; }" in prompts[0]
    assert "Existing" in prompts[0]


def test_suggestion_rejects_source_traversal_before_provider_call(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "outside.java").write_text("class Secret {}", encoding="utf-8")
    monkeypatch.setattr(main, "generate_update_for_change", lambda **_kwargs: pytest.fail("Groq must not be called"))
    response = TestClient(main.app).post("/suggest", json={
        "repository_path": str(repo),
        "file_path": "../outside.java",
        "class_name": "Secret",
        "method_name": "x",
        "change_type": "method_added",
    })
    assert response.status_code == 200
    assert "repository-relative" in response.json()["error"]


@pytest.mark.parametrize(
    ("category", "message"),
    [
        ("authentication", "Groq authentication failed."),
        ("rate_limit", "Groq is temporarily rate-limited. Please retry in approximately 35 seconds."),
    ],
)
def test_partial_provider_failure_never_persists_preview(tmp_path, monkeypatch, category, message):
    (tmp_path / "A.java").write_text("class A { int a() { return 1; } int b() { return 2; } int c() { return 3; } }", encoding="utf-8")
    (tmp_path / "API.md").write_text("## A\n", encoding="utf-8")
    store = tmp_path / "generation.sqlite3"
    monkeypatch.setattr(main, "GENERATION_STORE_PATH", store)
    monkeypatch.setattr(generator, "index_repository_documentation", lambda _path: {})
    monkeypatch.setattr(generator, "retrieve_repository_context", lambda **_kwargs: {"available": True, "documents": [], "metadatas": []})
    calls = []

    def generate(_prompt):
        calls.append(True)
        if len(calls) == 1:
            return "**Purpose and behavior**\nReturns 1.\n**Parameters**\nNone.\n**Returns**\n1.\n**Behavior**\nReturns 1."
        raise groq_client.GroqClientError(category, message)

    monkeypatch.setattr(generator, "generate_response", generate)
    response = TestClient(main.app).post("/documentation/generate/full", json={
        "repository_path": str(tmp_path),
        "target_documentation_file": "API.md",
        "include_repository_overview": False,
        "max_methods": 3,
    })
    assert response.status_code == 200
    assert response.json()["generation_status"] == "partial"
    assert response.json()["generation_id"] is None
    assert response.json()["approval_status"] == "unavailable"
    assert len(calls) == 2
    assert not store.exists()
    assert (tmp_path / "API.md").read_text(encoding="utf-8") == "## A\n"
    assert message in response.text
    assert "test-secret-key" not in response.text
