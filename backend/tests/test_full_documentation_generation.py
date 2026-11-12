import sys
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as app_module
from documentation_generation import full_documentation_generator as generator
from llm import ollama_client


@pytest.fixture
def client():
    return TestClient(app_module.app)


@pytest.fixture(autouse=True)
def mock_repository_rag(monkeypatch, tmp_path):
    monkeypatch.setattr(
        app_module,
        "GENERATION_STORE_PATH",
        tmp_path / "generations.sqlite3"
    )
    monkeypatch.setattr(
        generator,
        "index_repository_documentation",
        lambda _repository_path: {
            "indexed_files": [],
            "skipped_files": [],
            "deleted_files": [],
            "indexed_chunks": 0,
            "errors": []
        }
    )
    monkeypatch.setattr(
        generator,
        "retrieve_repository_context",
        lambda repository_path, query, top_k=3: {
            "query": query,
            "repository_id": "test-repository",
            "available": True,
            "error": None,
            "documents": [],
            "metadatas": [],
            "distances": [],
            "context_characters": 0
        }
    )


def write_file(root, relative_path, content):
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def valid_method_markdown():
    return (
        "**Purpose and behavior**\n"
        "Returns the supplied value.\n\n"
        "**Parameters**\n"
        "- value: input value.\n\n"
        "**Returns**\n"
        "- The supplied integer.\n\n"
        "**Behavior**\n"
        "- Returns the input without modification."
    )


def mock_model(monkeypatch, response=None):
    prompts = []

    def generate(prompt):
        prompts.append(prompt)
        if response is not None:
            return response(prompt) if callable(response) else response
        if "repository overview" in prompt:
            return "The repository provides the analyzed Java services."
        if "Java class" in prompt:
            return "Implements the source-backed operations listed below."
        return valid_method_markdown()

    monkeypatch.setattr(generator, "generate_response", generate)
    return prompts


def generate(root, **kwargs):
    return generator.generate_full_documentation(
        str(root),
        include_repository_overview=False,
        **kwargs
    )


def test_generates_one_undocumented_method_from_actual_source(
    tmp_path,
    monkeypatch
):
    write_file(
        tmp_path,
        "src/A.java",
        "package sample;\n"
        "class A {\n"
        "    int value(int input) {\n"
        "        return input + 1;\n"
        "    }\n"
        "}\n"
    )
    write_file(tmp_path, "API.md", "## A\n")
    prompts = mock_model(monkeypatch)

    result = generate(tmp_path)

    assert result["generation_status"] == "complete"
    assert len(result["generated_methods"]) == 1
    assert result["generated_methods"][0]["signature"] == "value(int)"
    assert "return input + 1;" in prompts[0]
    assert "sample.A" in prompts[0]
    assert "Source line range: 3–5" in prompts[0]
    assert result["generated_markdown"].startswith("# Repository Documentation")


def test_generates_multiple_methods(tmp_path, monkeypatch):
    write_file(
        tmp_path,
        "A.java",
        "class A {\n"
        "    int first() { return 1; }\n"
        "    int second() { return 2; }\n"
        "}\n"
    )
    write_file(tmp_path, "API.md", "## A\n")
    mock_model(monkeypatch)

    result = generate(tmp_path)

    assert [item["method"] for item in result["generated_methods"]] == [
        "first",
        "second"
    ]


@pytest.mark.parametrize("include_overview", [False, True])
def test_generation_without_retrieval_does_not_index(tmp_path, monkeypatch, include_overview):
    monkeypatch.setattr(
        generator,
        "index_repository_documentation",
        lambda _path: pytest.fail("No vector context is needed"),
    )
    result = generator.generate_full_documentation(
        str(tmp_path),
        target_documentation_file="API.md",
        include_repository_overview=include_overview,
    )
    assert result["retrieval"]["indexing"] is None
    assert result["retrieval"]["query_count"] == 0


def test_multiple_method_retrievals_initialize_index_once(tmp_path, monkeypatch):
    write_file(tmp_path, "A.java", "class A { int first() { return 1; } int second() { return 2; } }")
    write_file(tmp_path, "API.md", "## A\n")
    mock_model(monkeypatch)
    calls = []
    monkeypatch.setattr(generator, "index_repository_documentation", lambda _path: calls.append(1) or {})
    result = generate(tmp_path)
    assert len(result["generated_methods"]) == 2
    assert result["retrieval"]["query_count"] == 2
    assert calls == [1]


def test_generates_missing_class_and_method_for_multiple_classes(
    tmp_path,
    monkeypatch
):
    write_file(
        tmp_path,
        "Services.java",
        "class Alpha { int alpha() { return 1; } }\n"
        "class Beta { int beta() { return 2; } }\n"
    )
    write_file(tmp_path, "README.md", "")
    mock_model(monkeypatch)

    result = generate(tmp_path)

    assert {item["class"] for item in result["generated_classes"]} == {
        "Alpha",
        "Beta"
    }
    assert {item["class"] for item in result["generated_methods"]} == {
        "Alpha",
        "Beta"
    }
    assert "### Alpha" in result["generated_markdown"]
    assert "### Beta" in result["generated_markdown"]


def test_class_context_uses_supported_methods_not_fields_or_constructors(
    tmp_path,
    monkeypatch
):
    write_file(
        tmp_path,
        "A.java",
        "class A {\n"
        "    private String secret;\n"
        "    A(String secret) { this.secret = secret; }\n"
        "    String value() { return secret; }\n"
        "}\n"
    )
    write_file(tmp_path, "README.md", "")
    prompts = mock_model(monkeypatch)

    generate(tmp_path)

    class_prompt = next(
        prompt for prompt in prompts
        if "Write factual Markdown documentation for this Java class" in prompt
    )
    assert "private String secret" not in class_prompt
    assert "A(String secret)" not in class_prompt
    assert "String value()" in class_prompt


def test_overloaded_methods_keep_distinct_signatures(tmp_path, monkeypatch):
    write_file(
        tmp_path,
        "A.java",
        "class A {\n"
        "    int find(int id) { return id; }\n"
        "    int find(String name) { return name.length(); }\n"
        "}\n"
    )
    write_file(tmp_path, "API.md", "## A\n")
    mock_model(monkeypatch)

    result = generate(tmp_path)

    assert {item["signature"] for item in result["generated_methods"]} == {
        "find(int)",
        "find(String)"
    }
    assert result["generated_markdown"].count("#### find(") == 2


def test_already_documented_method_is_skipped(tmp_path, monkeypatch):
    write_file(
        tmp_path,
        "A.java",
        "class A { int value() { return 1; } int missing() { return 2; } }\n"
    )
    write_file(tmp_path, "API.md", "## A\n### value()\nAlready documented.\n")
    prompts = mock_model(monkeypatch)

    result = generate(tmp_path)

    assert len(result["skipped_documented_methods"]) == 1
    assert result["skipped_documented_methods"][0]["signature"] == "value()"
    assert len(result["generated_methods"]) == 1
    assert len(prompts) == 1
    assert "Method signature: missing()" in prompts[0]


def test_empty_documentation_file_is_used_as_preview_target(
    tmp_path,
    monkeypatch
):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "README.md", "")
    mock_model(monkeypatch)

    result = generate(tmp_path)

    assert result["documentation_target"] == "README.md"
    assert result["generated_markdown"]


def test_missing_documentation_file_uses_default_target(
    tmp_path,
    monkeypatch
):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    mock_model(monkeypatch)

    result = generate(tmp_path)

    assert result["documentation_target"] == "docs/API.md"


def test_generation_works_without_git(tmp_path, monkeypatch):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "API.md", "## A\n")
    mock_model(monkeypatch)

    result = generate(tmp_path)

    assert result["generation_status"] == "complete"
    assert result["generated_methods"][0]["method"] == "run"


def test_java_analysis_errors_do_not_report_successful_empty_preview(
    tmp_path,
    monkeypatch
):
    write_file(tmp_path, "Broken.java", "class Broken { void run( { }\n")
    mock_model(monkeypatch)

    result = generate(tmp_path)

    assert result["generation_status"] == "failed"
    assert result["generated_markdown"] is None
    assert any(error["stage"] == "java_analysis" for error in result["errors"])


def test_method_prompt_includes_parameter_and_return_evidence(
    tmp_path,
    monkeypatch
):
    write_file(
        tmp_path,
        "A.java",
        "class A {\n"
        "    String greet(String name) {\n"
        "        return \"Hello \" + name;\n"
        "    }\n"
        "}\n"
    )
    write_file(tmp_path, "API.md", "## A\n")
    prompts = mock_model(monkeypatch)

    result = generate(tmp_path)

    prompt = next(item for item in prompts if "Method signature:" in item)
    assert "greet(String)" in prompt
    assert "- name: String" in prompt
    assert "Return type: String" in prompt
    assert "return \"Hello \" + name" in prompt
    assert result["generated_methods"][0]["signature"] == "greet(String)"


def test_exception_handling_is_described_only_from_source(tmp_path, monkeypatch):
    write_file(
        tmp_path,
        "A.java",
        "class A {\n"
        "    int value() {\n"
        "        try { return Integer.parseInt(\"1\"); }\n"
        "        catch (NumberFormatException error) { return 0; }\n"
        "    }\n"
        "}\n"
    )
    write_file(tmp_path, "API.md", "## A\n")
    prompts = mock_model(monkeypatch)

    generate(tmp_path)

    prompt = next(item for item in prompts if "Method signature:" in item)
    assert "NumberFormatException" in prompt
    assert "Mention exceptions only when" in prompt


def test_large_method_context_is_bounded_and_flagged(tmp_path, monkeypatch):
    write_file(
        tmp_path,
        "A.java",
        "class A {\n"
        "    void run() {\n"
        "        /* " + ("x" * 15000) + " */\n"
        "    }\n"
        "}\n"
    )
    write_file(tmp_path, "API.md", "## A\n")
    prompts = mock_model(monkeypatch)

    result = generate(tmp_path)

    method_prompt = next(
        item for item in prompts if "Method signature:" in item
    )
    assert len(method_prompt) < 15000
    assert "INCOMPLETE" in method_prompt
    assert result["generated_methods"][0]["source_context_complete"] is False
    assert result["generation_status"] == "partial"


def test_ollama_unavailable_returns_failed_not_successful_empty_document(
    tmp_path,
    monkeypatch
):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "API.md", "## A\n")

    def unavailable(_prompt):
        raise ConnectionError("Ollama is unavailable")

    monkeypatch.setattr(generator, "generate_response", unavailable)

    result = generate(tmp_path)

    assert result["generation_status"] == "failed"
    assert result["generated_markdown"] is None
    assert any(
        "ConnectionError" in item["message"]
        for item in result["errors"]
    )


def test_empty_ollama_response_is_a_generation_failure(tmp_path, monkeypatch):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "API.md", "## A\n")
    mock_model(monkeypatch, response=" \n ")

    result = generate(tmp_path)

    assert result["generation_status"] == "failed"
    assert result["generated_markdown"] is None
    assert "empty documentation response" in result["errors"][0]["message"]


def test_invalid_method_markdown_is_rejected(tmp_path, monkeypatch):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "API.md", "## A\n")
    mock_model(monkeypatch, response="The method does something useful.")

    result = generate(tmp_path)

    assert result["generation_status"] == "failed"
    assert result["generated_markdown"] is None
    assert "invalid method Markdown" in result["errors"][0]["message"]


def test_repository_document_retrieval_failure_is_reported_but_generation_continues(
    tmp_path,
    monkeypatch
):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "API.md", "## A\n")
    mock_model(monkeypatch)

    def retrieval_failure(*_args, **_kwargs):
        raise OSError("documentation retrieval unavailable")

    monkeypatch.setattr(
        generator,
        "_extract_class_documentation",
        retrieval_failure
    )

    result = generate(tmp_path)

    assert result["generation_status"] == "partial"
    assert result["generated_methods"]
    assert any(
        item["stage"] == "documentation_retrieval"
        for item in result["errors"]
    )


def test_retrieval_is_scoped_to_selected_repository(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    unrelated = tmp_path / "other"
    write_file(repository, "A.java", "class A { void run() {} }\n")
    write_file(repository, "API.md", "## A\nRepository-specific context.\n")
    write_file(unrelated, "API.md", "## A\nUNRELATED REPOSITORY SECRET.\n")
    prompts = mock_model(monkeypatch)

    result = generate(repository)

    assert result["retrieval"]["repository_scoped"] is True
    assert "Repository-specific context." in "\n".join(prompts)
    assert "UNRELATED REPOSITORY SECRET" not in "\n".join(prompts)
    assert result["retrieval"]["vector_store_used"] is False
    assert result["retrieval"]["fallback_used"] is True


def test_partial_generation_failure_preserves_successful_method(
    tmp_path,
    monkeypatch
):
    write_file(
        tmp_path,
        "A.java",
        "class A {\n"
        "    int first() { return 1; }\n"
        "    int second() { return 2; }\n"
        "}\n"
    )
    write_file(tmp_path, "API.md", "## A\n")

    def partially_fail(prompt):
        if "Method signature: second()" in prompt:
            raise RuntimeError("model rejected second method")
        return valid_method_markdown()

    mock_model(monkeypatch, response=partially_fail)

    result = generate(tmp_path)

    assert result["generation_status"] == "partial"
    assert [item["method"] for item in result["generated_methods"]] == [
        "first"
    ]
    assert any(
        "RuntimeError" in item["message"]
        for item in result["errors"]
    )


def test_preview_generation_does_not_modify_markdown(tmp_path, monkeypatch):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    readme = write_file(tmp_path, "README.md", "")
    original = readme.read_bytes()
    mock_model(monkeypatch)

    generate(tmp_path)

    assert readme.read_bytes() == original
    assert not (tmp_path / "docs" / "API.md").exists()


def test_existing_endpoint_routes_remain_registered():
    routes = {
        (method, route.path)
        for route in app_module.app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("POST", "/documentation/generate/full") in routes
    assert ("POST", "/analyze") in routes
    assert ("POST", "/analyze/full") in routes
    assert ("POST", "/suggest") in routes
    assert ("POST", "/decision") in routes
    assert ("GET", "/history") in routes


def test_full_generation_endpoint_response_structure(
    client,
    tmp_path,
    monkeypatch
):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "API.md", "## A\n")
    monkeypatch.setattr(
        app_module,
        "GENERATION_STORE_PATH",
        tmp_path / "generations.sqlite3"
    )
    mock_model(monkeypatch)

    response = client.post(
        "/documentation/generate/full",
        json={"repository_path": str(tmp_path.resolve())}
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert {
        "repository",
        "documentation_target",
        "generated_markdown",
        "generated_classes",
        "generated_methods",
        "skipped_documented_methods",
        "errors",
        "generation_status"
    }.issubset(payload)
    assert payload["generation_status"] == "complete"
    assert payload["approval_status"] == "pending"
    assert payload["generation_id"]


def test_full_generation_endpoint_validates_path_and_target(
    client,
    tmp_path
):
    relative = client.post(
        "/documentation/generate/full",
        json={"repository_path": "relative/repository"}
    )
    invalid_target = client.post(
        "/documentation/generate/full",
        json={
            "repository_path": str(tmp_path.resolve()),
            "target_documentation_file": "../outside.md"
        }
    )
    missing_repository = client.post(
        "/documentation/generate/full",
        json={"repository_path": str((tmp_path / "missing").resolve())}
    )
    assert relative.status_code == 400
    assert invalid_target.status_code == 400
    assert missing_repository.status_code == 404


def test_repository_overview_is_optional_and_generated_when_requested(
    tmp_path,
    monkeypatch
):
    write_file(tmp_path, "A.java", "class A { int value() { return 1; } }\n")
    write_file(tmp_path, "API.md", "## A\n")
    prompts = mock_model(monkeypatch)

    result = generator.generate_full_documentation(
        str(tmp_path),
        include_repository_overview=True
    )

    assert result["generation_status"] == "complete"
    assert "## Overview" in result["generated_markdown"]
    assert any("repository overview" in prompt for prompt in prompts)


def test_large_repository_uses_bounded_mocked_model_requests(
    tmp_path,
    monkeypatch
):
    for index in range(100):
        write_file(
            tmp_path,
            f"src/package{index % 10}/Service{index:03d}.java",
            f"class Service{index:03d} {{\n"
            "    int value() {\n"
            "        return 1;\n"
            "    }\n"
            "}\n"
        )
    write_file(tmp_path, "README.md", "")
    prompts = mock_model(monkeypatch)

    result = generator.generate_full_documentation(
        str(tmp_path),
        include_repository_overview=False,
        max_methods=1
    )

    assert result["generation_status"] == "partial"
    assert len(result["generated_classes"]) == 100
    assert len(result["generated_methods"]) == 1
    assert len(prompts) == 101
    assert all(len(prompt) < 15000 for prompt in prompts)


def test_ollama_model_unavailable_is_reported(tmp_path, monkeypatch):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "API.md", "## A\n")

    def missing_model(_prompt):
        raise RuntimeError("model qwen2.5-coder:7b not found")

    monkeypatch.setattr(generator, "generate_response", missing_model)
    result = generate(tmp_path)

    assert result["generation_status"] == "failed"
    assert any(
        "RuntimeError" in error["message"]
        for error in result["errors"]
    )


def test_model_unavailable_http_error_has_safe_classification(monkeypatch):
    class Response:
        status_code = 404

        def json(self):
            return {"error": "model 'qwen2.5-coder:7b' not found"}

    monkeypatch.setattr(
        ollama_client.requests,
        "post",
        lambda *_args, **_kwargs: Response()
    )

    with pytest.raises(ollama_client.OllamaClientError) as error:
        ollama_client.generate_response("prompt", max_retries=1)

    assert error.value.category == "model_unavailable"
    assert "qwen2.5-coder:7b" in str(error.value)


@pytest.mark.parametrize(
    "response, expected",
    [
        ("  Plain **Markdown**  ", "Plain **Markdown**"),
        ("```markdown\n## Heading\n\n- item\n```", "## Heading\n\n- item"),
        ("```md\n### Heading\ntext\n```", "### Heading\ntext"),
        (
            "```markdown\nExample:\n```java\nint value = 1;\n```\n```",
            "Example:\n```java\nint value = 1;\n```"
        ),
        (
            "Value: ₹100 — ready → done.",
            "Value: ₹100 — ready → done."
        )
    ]
)
def test_normalizes_plain_and_fenced_markdown(response, expected):
    assert ollama_client.normalize_markdown_response(response) == expected


@pytest.mark.parametrize(
    "response",
    [
        "",
        "  \n ",
        "```markdown\n## Incomplete",
        "```text\nNot an allowed outer Markdown fence\n```",
        "Text\n```java\nint x = 1;"
    ]
)
def test_rejects_empty_or_malformed_markdown_fences(response):
    with pytest.raises(ValueError):
        ollama_client.normalize_markdown_response(response)


def test_generate_response_uses_configurable_timeout_and_model(
    monkeypatch
):
    captured = {}

    class Response:
        status_code = 200

        def json(self):
            return {"response": "ok"}

    def post(url, json, timeout):
        captured.update(url=url, payload=json, timeout=timeout)
        return Response()

    monkeypatch.setattr(ollama_client.requests, "post", post)

    assert ollama_client.generate_response(
        "prompt",
        timeout=17,
        max_retries=0
    ) == "ok"
    assert captured["timeout"] == 17
    assert captured["payload"]["model"] == "qwen2.5-coder:7b"


@pytest.mark.parametrize(
    "failure",
    [requests.ConnectionError("refused"), requests.Timeout("timed out")]
)
def test_transient_connection_and_timeout_failures_retry(
    monkeypatch,
    failure
):
    calls = []

    class Response:
        status_code = 200

        def json(self):
            return {"response": "recovered"}

    def post(*_args, **_kwargs):
        calls.append(True)
        if len(calls) == 1:
            raise failure
        return Response()

    monkeypatch.setattr(ollama_client.requests, "post", post)
    monkeypatch.setattr(ollama_client.time, "sleep", lambda _delay: None)

    assert ollama_client.generate_response(
        "prompt",
        timeout=1,
        max_retries=1
    ) == "recovered"
    assert len(calls) == 2


def test_http_server_error_retries_but_client_error_does_not(
    monkeypatch
):
    calls = []

    class Response:
        def __init__(self, status_code):
            self.status_code = status_code

        def json(self):
            return {"response": "ok"}

    def server_then_success(*_args, **_kwargs):
        calls.append(True)
        return Response(503 if len(calls) == 1 else 200)

    monkeypatch.setattr(
        ollama_client.requests,
        "post",
        server_then_success
    )
    monkeypatch.setattr(ollama_client.time, "sleep", lambda _delay: None)
    assert ollama_client.generate_response(
        "prompt",
        max_retries=1
    ) == "ok"
    assert len(calls) == 2

    calls.clear()
    monkeypatch.setattr(
        ollama_client.requests,
        "post",
        lambda *_args, **_kwargs: Response(400)
    )
    with pytest.raises(ollama_client.OllamaClientError) as error:
        ollama_client.generate_response("bad prompt", max_retries=1)
    assert error.value.category == "http"
    assert error.value.status_code == 400


def test_retry_exhaustion_and_http_errors_are_classified(monkeypatch):
    calls = []

    def unavailable(*_args, **_kwargs):
        calls.append(True)
        raise requests.ConnectionError("HTTPConnectionPool details")

    monkeypatch.setattr(ollama_client.requests, "post", unavailable)
    monkeypatch.setattr(ollama_client.time, "sleep", lambda _delay: None)

    with pytest.raises(ollama_client.OllamaClientError) as error:
        ollama_client.generate_response(
            "prompt",
            max_retries=1
        )

    assert error.value.category == "connection"
    assert str(error.value) == "Could not connect to the local Ollama server."
    assert len(calls) == 2


def test_timeout_exhaustion_is_classified_and_bounded(monkeypatch):
    calls = []

    def timed_out(*_args, **_kwargs):
        calls.append(True)
        raise requests.Timeout("timeout details")

    monkeypatch.setattr(ollama_client.requests, "post", timed_out)
    monkeypatch.setattr(ollama_client.time, "sleep", lambda _delay: None)

    with pytest.raises(ollama_client.OllamaClientError) as error:
        ollama_client.generate_response(
            "prompt",
            timeout=3,
            max_retries=1
        )

    assert error.value.category == "timeout"
    assert str(error.value) == "Ollama request timed out."
    assert len(calls) == 2


def test_malformed_ollama_json_is_not_retried(monkeypatch):
    calls = []

    class Response:
        status_code = 200

        def json(self):
            raise ValueError("invalid JSON")

    def post(*_args, **_kwargs):
        calls.append(True)
        return Response()

    monkeypatch.setattr(ollama_client.requests, "post", post)
    with pytest.raises(ollama_client.OllamaClientError) as error:
        ollama_client.generate_response("prompt", max_retries=1)
    assert error.value.category == "malformed_response"
    assert len(calls) == 1


def test_defaults_use_five_minute_timeout_and_at_most_one_retry(
    monkeypatch
):
    captured = []

    class Response:
        status_code = 200

        def json(self):
            return {"response": "ok"}

    def post(url, json, timeout):
        captured.append(timeout)
        if len(captured) == 1:
            raise requests.Timeout("first request timed out")
        return Response()

    monkeypatch.setattr(ollama_client.requests, "post", post)
    monkeypatch.setattr(ollama_client.time, "sleep", lambda _delay: None)
    monkeypatch.setattr(
        ollama_client,
        "DEFAULT_REQUEST_TIMEOUT",
        300
    )
    monkeypatch.setattr(ollama_client, "DEFAULT_MAX_RETRIES", 1)

    assert ollama_client.generate_response("prompt") == "ok"
    assert captured == [300, 300]


def test_more_than_one_retry_is_rejected(monkeypatch):
    calls = []
    monkeypatch.setattr(
        ollama_client.requests,
        "post",
        lambda *_args, **_kwargs: calls.append(True)
    )
    with pytest.raises(ValueError, match="between 0 and 1"):
        ollama_client.generate_response("prompt", max_retries=2)
    assert calls == []


def test_generation_accepts_fenced_class_and_method_markdown(
    tmp_path,
    monkeypatch
):
    write_file(
        tmp_path,
        "A.java",
        "class A { int value() { return 1; } }\n"
    )
    write_file(tmp_path, "API.md", "")

    def fenced(prompt):
        if "repository overview" in prompt:
            return "Overview"
        if "Java class" in prompt:
            return "```markdown\nA class based on its implementation.\n```"
        return (
            "```md\n"
            + valid_method_markdown()
            + "\n```"
        )

    mock_model(monkeypatch, response=fenced)
    result = generate(tmp_path)

    assert result["generation_status"] == "complete"
    assert len(result["generated_classes"]) == 1
    assert len(result["generated_methods"]) == 1
    assert "```markdown" not in result["generated_markdown"]


def test_class_failure_is_separate_from_successful_method_generation(
    tmp_path,
    monkeypatch
):
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "README.md", "")

    def class_failure(prompt):
        if "Java class" in prompt:
            return "```markdown\nClass response without a closing fence"
        return valid_method_markdown()

    mock_model(monkeypatch, response=class_failure)
    result = generate(tmp_path)

    assert result["generation_status"] == "partial"
    assert result["generated_classes"] == []
    assert len(result["generated_methods"]) == 1
    assert any(
        error["stage"] == "class_generation"
        for error in result["errors"]
    )


def test_invalid_markdown_format_is_not_retried_by_generation(
    monkeypatch
):
    calls = []

    def invalid_response(_prompt):
        calls.append(True)
        return "```markdown\nincomplete"

    monkeypatch.setattr(generator, "generate_response", invalid_response)

    markdown, error = generator._call_model(
        "prompt",
        "class_generation"
    )

    assert markdown is None
    assert "malformed or incomplete" in error
    assert len(calls) == 1


def test_unicode_survives_python_json_and_fastapi_transport(
    client,
    tmp_path,
    monkeypatch
):
    unicode_text = "₹100 — ready → complete"
    write_file(tmp_path, "A.java", "class A { void run() {} }\n")
    write_file(tmp_path, "API.md", "## A\n")
    mock_model(
        monkeypatch,
        response=(
            "**Purpose and behavior**\n" + unicode_text
            + "\n\n**Parameters**\n- None\n\n**Returns**\n- void\n\n"
            "**Behavior**\n- No additional behavior."
        )
    )

    response = client.post(
        "/documentation/generate/full",
        json={
            "repository_path": str(tmp_path.resolve()),
            "include_repository_overview": False
        }
    )

    assert response.status_code == 200
    assert unicode_text in response.content.decode("utf-8")
    assert unicode_text in response.json()["generated_markdown"]
    assert "â" not in response.content.decode("utf-8")
