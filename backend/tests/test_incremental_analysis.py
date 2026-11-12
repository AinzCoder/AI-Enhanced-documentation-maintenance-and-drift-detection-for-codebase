import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from git import Repo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as app_module


@pytest.fixture
def client():
    return TestClient(app_module.app)


def create_repository(path, files):
    path.mkdir(parents=True, exist_ok=True)
    repo = Repo.init(path)
    with repo.config_writer() as config:
        config.set_value("user", "name", "DocGuard Test")
        config.set_value("user", "email", "docguard@example.test")
    for file_path, content in files.items():
        target = path / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return repo


def commit_all(repo, message):
    repo.git.add(A=True)
    return repo.index.commit(message)


def analyze(client, repository_path, **payload):
    return client.post(
        "/analyze",
        json={
            "repository_path": str(repository_path),
            **payload
        }
    )


def only_file_result(response, file_path=None):
    assert response.status_code == 200, response.text
    results = response.json()["results"]
    if file_path is not None:
        results = [
            result for result in results
            if result["file"] == file_path
        ]
    assert len(results) == 1, results
    return results[0]


def event(result, event_type, method=None):
    matches = [
        change
        for change in result["changes"]
        if change["type"] == event_type
        and (method is None or change.get("method") == method)
    ]
    assert len(matches) == 1, matches
    return matches[0]


def test_head_against_modified_working_tree(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {"src/A.java": "class A { int value() { return 1; } }\n"}
    )
    commit_all(repo, "initial")
    (tmp_path / "src/A.java").write_text(
        "class A {\n    int value() { return 2; }\n}\n",
        encoding="utf-8"
    )

    response = analyze(client, tmp_path)
    result = only_file_result(response, "src/A.java")

    assert response.json()["mode"] == "working_tree"
    assert response.json()["current_commit"] == repo.head.commit.hexsha
    assert response.json()["previous_commit"] == repo.head.commit.hexsha
    assert event(result, "method_body_changed", "value")["start_line"] == 2


def test_staged_java_change_is_included(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {"A.java": "class A { int value() { return 1; } }\n"}
    )
    commit_all(repo, "initial")
    (tmp_path / "A.java").write_text(
        "class A { int value() { return 2; } }\n",
        encoding="utf-8"
    )
    repo.index.add(["A.java"])

    result = only_file_result(analyze(client, tmp_path), "A.java")
    event(result, "method_body_changed", "value")


def test_unstaged_java_change_is_included(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {"A.java": "class A { int value() { return 1; } }\n"}
    )
    commit_all(repo, "initial")
    (tmp_path / "A.java").write_text(
        "class A { int value() { return 2; } }\n",
        encoding="utf-8"
    )

    result = only_file_result(analyze(client, tmp_path), "A.java")
    event(result, "method_body_changed", "value")


def test_staged_and_unstaged_changes_use_final_working_tree(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {"A.java": "class A { int value() { return 1; } }\n"}
    )
    commit_all(repo, "initial")
    java_file = tmp_path / "A.java"
    java_file.write_text(
        (
            "class A {\n"
            "    int value() { return 2; }\n"
            "    void stagedOnly() {}\n"
            "}\n"
        ),
        encoding="utf-8"
    )
    repo.index.add(["A.java"])
    java_file.write_text(
        (
            "class A {\n"
            "    int value() { return 3; }\n"
            "    void finalOnly() {}\n"
            "}\n"
        ),
        encoding="utf-8"
    )

    result = only_file_result(analyze(client, tmp_path), "A.java")
    assert result["change_type"] == "M"
    event(result, "method_body_changed", "value")
    event(result, "method_added", "finalOnly")
    assert not any(
        change.get("method") == "stagedOnly"
        for change in result["changes"]
    )


def test_untracked_java_file_is_added(client, tmp_path):
    repo = create_repository(tmp_path, {})
    commit_all(repo, "initial")
    (tmp_path / "New.java").write_text(
        "class New { int fresh() { return 1; } }\n",
        encoding="utf-8"
    )

    result = only_file_result(analyze(client, tmp_path), "New.java")
    assert result["change_type"] == "A"
    event(result, "class_added")


def test_deleted_java_file_is_removed_with_old_positions(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {"Gone.java": "class Gone {\n    void oldMethod() {}\n}\n"}
    )
    commit_all(repo, "initial")
    (tmp_path / "Gone.java").unlink()

    result = only_file_result(analyze(client, tmp_path), "Gone.java")
    assert result["change_type"] == "D"
    event(result, "class_removed")


def test_java_file_rename_without_content_changes(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {"Old.java": "class Same { void keep() {} }\n"}
    )
    commit_all(repo, "initial")
    repo.git.mv("Old.java", "New.java")

    result = only_file_result(analyze(client, tmp_path), "New.java")
    assert result["change_type"] == "R"
    assert result["old_file"] == "Old.java"
    assert result["new_file"] == "New.java"
    assert result["git_change_type"] == "R"
    assert result["changes"] == []


def test_java_rename_with_implementation_change(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {"Old.java": "class Same { int value() { return 1; } }\n"}
    )
    commit_all(repo, "initial")
    repo.git.mv("Old.java", "New.java")
    (tmp_path / "New.java").write_text(
        "class Same { int value() { return 2; } }\n",
        encoding="utf-8"
    )

    result = only_file_result(analyze(client, tmp_path), "New.java")
    assert result["change_type"] == "R"
    event(result, "method_body_changed", "value")


def test_unstaged_rename_with_implementation_change(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {
            "Old.java": (
                "class Same {\n"
                "    int value() {\n"
                "        return 1;\n"
                "    }\n"
                "}\n"
            )
        }
    )
    commit_all(repo, "initial")
    (tmp_path / "Old.java").rename(tmp_path / "New.java")
    (tmp_path / "New.java").write_text(
        "class Same {\n"
        "    int value() {\n"
        "        return 2;\n"
        "    }\n"
        "}\n",
        encoding="utf-8"
    )

    result = only_file_result(analyze(client, tmp_path), "New.java")
    assert result["change_type"] == "R"
    assert result["old_file"] == "Old.java"
    assert result["new_file"] == "New.java"
    event(result, "method_body_changed", "value")


@pytest.mark.parametrize(
    ("old_name", "new_name", "expected_change"),
    [
        ("Old.java", "New.txt", "D"),
        ("Old.txt", "New.java", "A")
    ]
)
def test_rename_across_java_extension_is_java_side_add_or_delete(
    client,
    tmp_path,
    old_name,
    new_name,
    expected_change
):
    repo = create_repository(
        tmp_path,
        {old_name: "class Same { void keep() {} }\n"}
    )
    commit_all(repo, "initial")
    repo.git.mv(old_name, new_name)

    result_file = new_name if expected_change == "A" else old_name
    result = only_file_result(analyze(client, tmp_path), result_file)
    assert result["change_type"] == expected_change
    assert result["git_change_type"] == "R"
    assert result["old_file"] == old_name
    assert result["new_file"] == new_name
    expected_event = "class_added" if expected_change == "A" else "class_removed"
    event(result, expected_event)


def test_commits_mode_compares_immediate_parent(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {"A.java": "class A { int value() { return 1; } }\n"}
    )
    first_commit = commit_all(repo, "first")
    (tmp_path / "A.java").write_text(
        "class A { int value() { return 2; } }\n"
        "class AddedInSecond {}\n",
        encoding="utf-8"
    )
    second_commit = commit_all(repo, "second")
    (tmp_path / "A.java").write_text(
        "class A { int value() { return 3; } }\n"
        "class AddedInSecond {}\n",
        encoding="utf-8"
    )
    third_commit = commit_all(repo, "third")

    response = analyze(client, tmp_path, mode="commits")
    result = only_file_result(response, "A.java")
    assert response.json()["previous_commit"] == second_commit.hexsha
    assert response.json()["current_commit"] == third_commit.hexsha
    assert not any(
        change["type"] == "class_added"
        for change in result["changes"]
    )
    assert first_commit.hexsha != second_commit.hexsha
    event(result, "method_body_changed", "value")


def test_explicit_base_commit_is_used(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {"A.java": "class A {}\n"}
    )
    base_commit = commit_all(repo, "base")
    (tmp_path / "A.java").write_text(
        "class A {}\nclass Later {}\n",
        encoding="utf-8"
    )
    commit_all(repo, "later")

    response = analyze(
        client,
        tmp_path,
        mode="commits",
        base_commit=base_commit.hexsha
    )
    result = only_file_result(response, "A.java")

    assert response.json()["previous_commit"] == base_commit.hexsha
    event(result, "class_added")


def test_initial_commit_compares_against_empty_tree(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {"Initial.java": "class Initial { void first() {} }\n"}
    )
    initial_commit = commit_all(repo, "initial")

    response = analyze(client, tmp_path, mode="commits")
    result = only_file_result(response, "Initial.java")

    assert response.json()["current_commit"] == initial_commit.hexsha
    assert response.json()["previous_commit"] is None
    assert result["change_type"] == "A"
    event(result, "class_added")


def test_unborn_repository_working_tree_includes_untracked_java(client, tmp_path):
    repo = create_repository(tmp_path, {})
    (tmp_path / "First.java").write_text(
        "class First {}\n",
        encoding="utf-8"
    )

    response = analyze(client, tmp_path)
    result = only_file_result(response, "First.java")

    assert response.json()["current_commit"] is None
    assert response.json()["previous_commit"] is None
    assert result["change_type"] == "A"
    event(result, "class_added")


def test_multiple_changed_java_files_are_returned(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {
            "A.java": "class A { void oldA() {} }\n",
            "B.java": "class B { void oldB() {} }\n",
            "C.txt": "not java\n"
        }
    )
    commit_all(repo, "initial")
    (tmp_path / "A.java").write_text(
        "class A { void newA() {} }\n",
        encoding="utf-8"
    )
    (tmp_path / "B.java").write_text(
        "class B { void newB() {} }\n",
        encoding="utf-8"
    )

    response = analyze(client, tmp_path)
    assert response.status_code == 200, response.text
    assert {result["file"] for result in response.json()["results"]} == {
        "A.java",
        "B.java"
    }


def test_no_changes_returns_empty_results(client, tmp_path):
    repo = create_repository(tmp_path, {"A.java": "class A {}\n"})
    commit_all(repo, "initial")

    response = analyze(client, tmp_path)
    assert response.status_code == 200
    assert response.json()["results"] == []


def test_method_event_positions_are_preserved(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {"A.java": "class A {\n    void removed() {}\n}\n"}
    )
    commit_all(repo, "initial")
    (tmp_path / "A.java").write_text(
        "class A {\n\n    void added() {}\n}\n",
        encoding="utf-8"
    )

    result = only_file_result(analyze(client, tmp_path), "A.java")
    assert event(result, "method_removed", "removed")["old_start_line"] == 2
    assert event(result, "method_added", "added")["start_line"] == 3


def test_invalid_repository_path_is_rejected(client, tmp_path):
    response = analyze(client, tmp_path / "not-a-repository")
    assert response.status_code == 400
    assert "repository" in response.json()["detail"].lower()


def test_invalid_git_revision_is_rejected(client, tmp_path):
    repo = create_repository(tmp_path, {"A.java": "class A {}\n"})
    commit_all(repo, "initial")

    response = analyze(
        client,
        tmp_path,
        mode="commits",
        base_commit="not-a-valid-revision"
    )
    assert response.status_code == 400
    assert "base commit" in response.json()["detail"].lower()


def test_malformed_java_does_not_prevent_other_files(client, tmp_path):
    repo = create_repository(
        tmp_path,
        {
            "Broken.java": "class Broken { void bad() {} }\n",
            "Good.java": "class Good { int value() { return 1; } }\n"
        }
    )
    commit_all(repo, "initial")
    (tmp_path / "Broken.java").write_text(
        "class Broken { void broken( { }\n",
        encoding="utf-8"
    )
    (tmp_path / "Good.java").write_text(
        "class Good { int value() { return 2; } }\n",
        encoding="utf-8"
    )

    response = analyze(client, tmp_path)
    assert response.status_code == 200
    results = {result["file"]: result for result in response.json()["results"]}
    assert set(results) == {"Broken.java", "Good.java"}
    assert results["Broken.java"]["changes"] == []
    assert results["Broken.java"]["errors"][0]["stage"] == "java_analysis"
    event(results["Good.java"], "method_body_changed", "value")


def test_documentation_failure_is_reported_and_other_files_continue(
    client,
    tmp_path,
    monkeypatch
):
    repo = create_repository(
        tmp_path,
        {
            "A.java": "class A { int value() { return 1; } }\n",
            "B.java": "class B { int value() { return 1; } }\n"
        }
    )
    commit_all(repo, "initial")
    for file_name in ("A.java", "B.java"):
        (tmp_path / file_name).write_text(
            "class " + file_name[0] + " { int value() { return 2; } }\n",
            encoding="utf-8"
        )

    original_mapper = app_module.map_code_to_documentation

    def failing_mapper(repository_path, code_file):
        if code_file == "A.java":
            raise OSError("test mapper failure")
        return original_mapper(repository_path, code_file)

    monkeypatch.setattr(
        app_module,
        "map_code_to_documentation",
        failing_mapper
    )

    response = analyze(client, tmp_path)
    assert response.status_code == 200
    results = {result["file"]: result for result in response.json()["results"]}
    assert results["A.java"]["errors"][0]["stage"] == "documentation_mapping"
    assert "test mapper failure" in results["A.java"]["errors"][0]["message"]
    event(results["B.java"], "method_body_changed", "value")


def test_drift_failure_is_reported_and_other_files_continue(
    client,
    tmp_path,
    monkeypatch
):
    repo = create_repository(
        tmp_path,
        {
            "A.java": "class A { int value() { return 1; } }\n",
            "B.java": "class B { int value() { return 1; } }\n"
        }
    )
    commit_all(repo, "initial")
    for file_name in ("A.java", "B.java"):
        (tmp_path / file_name).write_text(
            "class " + file_name[0] + " { int value() { return 2; } }\n",
            encoding="utf-8"
        )

    original_detector = app_module.detect_documentation_drift

    def failing_detector(repository_path, documentation_files, changes):
        if any(change.get("class") == "A" for change in changes):
            raise OSError("test drift failure")
        return original_detector(repository_path, documentation_files, changes)

    monkeypatch.setattr(
        app_module,
        "detect_documentation_drift",
        failing_detector
    )

    response = analyze(client, tmp_path)
    assert response.status_code == 200
    results = {result["file"]: result for result in response.json()["results"]}
    assert results["A.java"]["errors"][0]["stage"] == "drift_detection"
    assert "test drift failure" in results["A.java"]["errors"][0]["message"]
    event(results["B.java"], "method_body_changed", "value")
