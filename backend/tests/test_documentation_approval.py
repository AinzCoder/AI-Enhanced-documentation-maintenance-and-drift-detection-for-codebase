import hashlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as app_module
from approval import generation_workflow
from approval.generation_store import create_pending_record, get_record


@pytest.fixture
def client():
    return TestClient(app_module.app)


def write_file(root, relative_path, content):
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target


def create_record(
    root,
    store_path,
    generation_id="generation-1",
    target_content="## Existing\n\nKeep this unrelated section.\n",
    status="complete",
    classes=None,
    methods=None,
    ambiguous=None
):
    source = write_file(
        root,
        "src/A.java",
        "package sample;\nclass A { int run() { return 1; } }\n"
    )
    target = root / "docs" / "API.md"
    if target_content is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(target_content, encoding="utf-8")

    class_items = classes if classes is not None else [{
        "source_file": "src/A.java",
        "package": "sample",
        "class": "A",
        "identity": "sample.A — src/A.java",
        "description": "Class A returns values from its implementation.",
        "start_line": 2,
        "end_line": 2
    }]
    method_items = methods if methods is not None else [{
        "source_file": "src/A.java",
        "package": "sample",
        "class": "A",
        "signature": "run()",
        "method": "run",
        "documentation": (
            "**Purpose and behavior**\n"
            "Returns the implementation's integer value.\n\n"
            "**Parameters**\n"
            "- None.\n\n"
            "**Returns**\n"
            "- An integer.\n\n"
            "**Behavior**\n"
            "- Returns the computed value."
        ),
        "start_line": 2,
        "end_line": 2
    }]
    target_hash = (
        hashlib.sha256(target.read_bytes()).hexdigest()
        if target_content is not None
        else "__missing__"
    )
    record = {
        "generation_id": generation_id,
        "repository": root.name,
        "repository_identity": hashlib.sha256(
            str(root.resolve()).casefold().encode("utf-8")
        ).hexdigest(),
        "repository_path": str(root.resolve()),
        "documentation_target": "docs/API.md",
        "generated_markdown": (
            "# Repository Documentation\n\n"
            "## Classes\n\n### A\n\n"
            "#### run()\n"
        ),
        "generated_classes": class_items,
        "generated_methods": method_items,
        "repository_overview": None,
        "ambiguous_documentation_mappings": ambiguous or [],
        "generation_status": status,
        "created_at": "2026-11-07T12:00:00+05:30",
        "source_hashes": {
            "src/A.java": hashlib.sha256(source.read_bytes()).hexdigest()
        },
        "target_hash_before": target_hash
    }
    create_pending_record(store_path, record)
    return record, target


def configure_storage(monkeypatch, tmp_path):
    store_path = tmp_path / "approval.sqlite3"
    history_path = tmp_path / "documentation_history.json"
    monkeypatch.setattr(app_module, "GENERATION_STORE_PATH", store_path)
    monkeypatch.setattr(app_module, "HISTORY_FILE", history_path)
    return store_path


def approve(client, generation_id="generation-1", decision="approve"):
    return client.post(
        f"/documentation/generation/{generation_id}/approve",
        json={"decision": decision}
    )


def reject(client, generation_id="generation-1", decision="reject"):
    return client.post(
        f"/documentation/generation/{generation_id}/reject",
        json={"decision": decision}
    )


def test_preview_is_stored_pending_and_does_not_write_before_approval(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    existing = write_file(tmp_path, "docs/API.md", "## Existing\nKeep.\n")
    original = existing.read_bytes()
    create_record(
        tmp_path,
        store_path,
        target_content=existing.read_text(encoding="utf-8")
    )

    record = client.get(
        "/documentation/generation/generation-1"
    ).json()

    assert record["status"] == "pending"
    assert record["generated_markdown"]
    assert record["source_hashes"]["src/A.java"]
    assert existing.read_bytes() == original


def test_approval_preserves_existing_markdown_and_inserts_sections(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    target = write_file(
        tmp_path,
        "docs/API.md",
        "# Existing API\n\n## Existing\n\nKeep this section unchanged.\n"
    )
    original_section = "## Existing\n\nKeep this section unchanged."
    create_record(
        tmp_path,
        store_path,
        target_content=target.read_text(encoding="utf-8")
    )

    response = approve(client)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "approved"
    content = target.read_text(encoding="utf-8")
    assert original_section in content
    assert "### A" in content
    assert "#### run()" in content
    assert content.count("# Repository Documentation") == 0


def test_rejection_records_audit_without_writing_markdown(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    target = write_file(tmp_path, "docs/API.md", "# API\nKeep.\n")
    original = target.read_bytes()
    create_record(
        tmp_path,
        store_path,
        target_content=target.read_text(encoding="utf-8")
    )

    response = reject(client)

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert target.read_bytes() == original
    assert get_record(store_path, "generation-1")["audit"]["status"] == "rejected"


def test_duplicate_approval_is_rejected(client, tmp_path, monkeypatch):
    store_path = configure_storage(monkeypatch, tmp_path)
    create_record(tmp_path, store_path)

    assert approve(client).status_code == 200
    duplicate = approve(client)

    assert duplicate.status_code == 409
    assert get_record(store_path, "generation-1")["status"] == "approved"


def test_stale_source_hash_prevents_write(client, tmp_path, monkeypatch):
    store_path = configure_storage(monkeypatch, tmp_path)
    record, target = create_record(tmp_path, store_path)
    source = tmp_path / "src" / "A.java"
    source.write_text(source.read_text(encoding="utf-8") + "// changed\n")
    original_target = target.read_bytes()

    response = approve(client, record["generation_id"])

    assert response.status_code == 409
    assert "source files changed" in response.json()["detail"]
    assert target.read_bytes() == original_target
    assert get_record(store_path, record["generation_id"])["status"] == "stale"


def test_stale_target_hash_prevents_write(client, tmp_path, monkeypatch):
    store_path = configure_storage(monkeypatch, tmp_path)
    record, target = create_record(tmp_path, store_path)
    target.write_text(target.read_text(encoding="utf-8") + "Concurrent edit.\n")
    original_target = target.read_bytes()

    response = approve(client, record["generation_id"])

    assert response.status_code == 409
    assert "target changed" in response.json()["detail"]
    assert target.read_bytes() == original_target
    assert get_record(store_path, record["generation_id"])["status"] == "stale"


def test_missing_target_is_created_only_after_approval(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    record, target = create_record(
        tmp_path,
        store_path,
        target_content=None
    )

    assert not target.exists()
    response = approve(client, record["generation_id"])

    assert response.status_code == 200, response.text
    assert target.exists()
    assert "# Repository Documentation" in target.read_text(encoding="utf-8")


def test_existing_markdown_content_is_preserved(client, tmp_path, monkeypatch):
    store_path = configure_storage(monkeypatch, tmp_path)
    original = (
        "# Project API\n\n"
        "Unrelated introductory text.\n\n"
        "## Existing Class\n\nUnrelated method docs.\n"
    )
    target = write_file(tmp_path, "docs/API.md", original)
    create_record(tmp_path, store_path, target_content=original)

    response = approve(client)

    assert response.status_code == 200
    updated = target.read_text(encoding="utf-8")
    assert "Unrelated introductory text." in updated
    assert "## Existing Class\n\nUnrelated method docs." in updated


def test_missing_class_description_is_added_above_existing_method_sections(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    target_content = "## Classes\n\n### A\n\n#### other()\nExisting method.\n"
    target = write_file(tmp_path, "docs/API.md", target_content)
    record, _ = create_record(
        tmp_path,
        store_path,
        target_content=target.read_text(encoding="utf-8")
    )

    response = approve(client, record["generation_id"])

    assert response.status_code == 200
    content = target.read_text(encoding="utf-8")
    assert "Class A returns values from its implementation." in content
    assert content.index("Class A returns") < content.index("#### other()")


def test_already_documented_method_is_not_duplicated(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    target_content = (
        "## Classes\n\n### A\n\nExisting class documentation.\n\n"
        "#### run()\nExisting method documentation.\n"
    )
    target = write_file(tmp_path, "docs/API.md", target_content)
    record, _ = create_record(
        tmp_path,
        store_path,
        target_content=target.read_text(encoding="utf-8")
    )

    response = approve(client, record["generation_id"])

    assert response.status_code == 200
    content = target.read_text(encoding="utf-8")
    assert content.count("#### run()") == 1
    assert "Existing method documentation." in content


def test_overloaded_methods_are_inserted_with_distinct_signatures(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    target = write_file(tmp_path, "docs/API.md", "## A\n")
    source = write_file(tmp_path, "src/A.java", "class A {}\n")
    hashes = {"src/A.java": hashlib.sha256(source.read_bytes()).hexdigest()}
    record = {
        "generation_id": "overloads",
        "repository": tmp_path.name,
        "repository_identity": "repository-hash",
        "repository_path": str(tmp_path.resolve()),
        "documentation_target": "docs/API.md",
        "generated_markdown": "# preview\n",
        "generated_classes": [],
        "generated_methods": [
            {
                "source_file": "src/A.java",
                "class": "A",
                "signature": "find(int)",
                "method": "find",
                "documentation": "Integer lookup.",
                "start_line": 1,
                "end_line": 1
            },
            {
                "source_file": "src/A.java",
                "class": "A",
                "signature": "find(String)",
                "method": "find",
                "documentation": "Name lookup.",
                "start_line": 1,
                "end_line": 1
            }
        ],
        "repository_overview": None,
        "ambiguous_documentation_mappings": [],
        "generation_status": "complete",
        "created_at": "2026-11-07T12:00:00+05:30",
        "source_hashes": hashes,
        "target_hash_before": hashlib.sha256(target.read_bytes()).hexdigest()
    }
    create_pending_record(store_path, record)

    response = approve(client, "overloads")

    assert response.status_code == 200
    content = target.read_text(encoding="utf-8")
    assert "### find(int)" in content
    assert "### find(String)" in content


def test_multiple_classes_are_merged_into_separate_sections(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    target = write_file(tmp_path, "docs/API.md", "# API\n")
    source = write_file(tmp_path, "src/Pair.java", "class A {} class B {}\n")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    record = {
        "generation_id": "two-classes",
        "repository": tmp_path.name,
        "repository_identity": "repo",
        "repository_path": str(tmp_path.resolve()),
        "documentation_target": "docs/API.md",
        "generated_markdown": "# preview",
        "generated_classes": [
            {
                "source_file": "src/Pair.java",
                "class": "A",
                "identity": "A — src/Pair.java",
                "description": "A class.",
                "start_line": 1,
                "end_line": 1
            },
            {
                "source_file": "src/Pair.java",
                "class": "B",
                "identity": "B — src/Pair.java",
                "description": "B class.",
                "start_line": 1,
                "end_line": 1
            }
        ],
        "generated_methods": [],
        "repository_overview": None,
        "ambiguous_documentation_mappings": [],
        "generation_status": "complete",
        "created_at": "2026-11-07T12:00:00+05:30",
        "source_hashes": {"src/Pair.java": source_hash},
        "target_hash_before": hashlib.sha256(target.read_bytes()).hexdigest()
    }
    create_pending_record(store_path, record)

    response = approve(client, "two-classes")

    assert response.status_code == 200
    content = target.read_text(encoding="utf-8")
    assert "### A" in content
    assert "### B" in content


def test_partial_preview_approval_inserts_only_generated_content(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    record, target = create_record(
        tmp_path,
        store_path,
        status="partial"
    )

    response = approve(client, record["generation_id"])

    assert response.status_code == 200
    assert response.json()["generation_status"] == "partial"
    content = target.read_text(encoding="utf-8")
    assert "run()" in content
    assert "complete repository replacement" not in content.lower()


def test_invalid_generation_id_returns_not_found(client, tmp_path, monkeypatch):
    configure_storage(monkeypatch, tmp_path)

    assert approve(client, "missing-id").status_code == 404
    assert reject(client, "missing-id").status_code == 404


def test_atomic_write_failure_keeps_target_and_records_failure(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    record, target = create_record(tmp_path, store_path)
    original = target.read_bytes()

    def fail_write(_destination, _content):
        raise OSError("simulated atomic replace failure")

    monkeypatch.setattr(
        generation_workflow,
        "atomic_write_markdown",
        fail_write
    )
    response = approve(client, record["generation_id"])

    assert response.status_code == 500
    assert target.read_bytes() == original
    stored = get_record(store_path, record["generation_id"])
    assert stored["status"] == "failed"
    assert "simulated atomic replace failure" in stored["failure_reason"]


def test_approved_unicode_is_preserved_and_hashes_recorded(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    record, target = create_record(
        tmp_path,
        store_path,
        target_content="# API\n"
    )
    record2, _ = create_record(
        tmp_path,
        store_path,
        generation_id="unicode",
        target_content="# API\n"
    )
    stored = get_record(store_path, record2["generation_id"])
    stored["generated_methods"][0]["documentation"] = (
        "Value is ₹100 — ready → complete."
    )
    from approval.generation_store import update_record
    update_record(
        store_path,
        "unicode",
        "pending",
        "2026-11-07T12:01:00+05:30",
        additions={"generated_methods": stored["generated_methods"]},
        expected_status="pending"
    )

    response = approve(client, "unicode")

    assert response.status_code == 200
    assert "₹100 — ready → complete" in target.read_text(encoding="utf-8")
    audit = get_record(store_path, "unicode")["audit"]
    assert audit["documentation_hash_before"] == record2["target_hash_before"]
    assert audit["documentation_hash_after"] != audit["documentation_hash_before"]
    assert "documentation" not in audit["generated_methods"][0]


def test_ambiguous_documentation_mapping_blocks_write(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    record, target = create_record(
        tmp_path,
        store_path,
        ambiguous=[{
            "source_file": "src/A.java",
            "class": "A",
            "finding_type": "ambiguous_documentation_mapping"
        }]
    )
    original = target.read_bytes()

    response = approve(client, record["generation_id"])

    assert response.status_code == 500
    assert target.read_bytes() == original
    assert get_record(store_path, record["generation_id"])["status"] == "failed"


def test_decision_fields_are_required_and_rejection_does_not_write(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    record, target = create_record(tmp_path, store_path)
    original = target.read_bytes()

    bad_approve = client.post(
        "/documentation/generation/generation-1/approve",
        json={"decision": "reject"}
    )
    bad_reject = client.post(
        "/documentation/generation/generation-1/reject",
        json={"decision": "approve"}
    )
    assert bad_approve.status_code == 400
    assert bad_reject.status_code == 400
    assert reject(client, record["generation_id"]).status_code == 200
    assert target.read_bytes() == original


def test_generation_history_is_exposed_without_markdown_or_source_code(
    client,
    tmp_path,
    monkeypatch
):
    store_path = configure_storage(monkeypatch, tmp_path)
    record, _ = create_record(tmp_path, store_path)
    assert approve(client, record["generation_id"]).status_code == 200

    history = client.get("/history").json()["history"]
    audit = next(
        item for item in history
        if item.get("generation_id") == record["generation_id"]
    )

    assert audit["status"] == "approved"
    assert audit["source_hashes"]
    assert "generated_markdown" not in audit
    assert all(
        "documentation" not in method
        for method in audit["generated_methods"]
    )


def test_approval_endpoints_and_legacy_decision_remain_registered(client):
    routes = {
        (method, route.path)
        for route in app_module.app.routes
        for method in getattr(route, "methods", set())
    }
    assert ("POST", "/decision") in routes
    assert ("POST", "/documentation/generation/{generation_id}/approve") in routes
    assert ("POST", "/documentation/generation/{generation_id}/reject") in routes
    assert ("GET", "/documentation/generation/{generation_id}") in routes


def test_legacy_decision_rejects_markdown_target_outside_repository(
    client,
    tmp_path
):
    repository = tmp_path / "repo"
    repository.mkdir()
    outside_target = write_file(
        tmp_path,
        "outside.md",
        "# API\n\n## A\n\nExisting documentation.\n"
    )
    original = outside_target.read_bytes()

    response = client.post(
        "/decision",
        json={
            "repository_path": str(repository),
            "documentation_file": "../outside.md",
            "class_name": "A",
            "method_name": "run",
            "decision": "approve",
            "documentation": "### run()\n\nUpdated documentation.",
        }
    )

    assert response.status_code == 400
    assert outside_target.read_bytes() == original
