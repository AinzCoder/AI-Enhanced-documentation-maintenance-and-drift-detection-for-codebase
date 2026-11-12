from fastapi.testclient import TestClient
from git import Actor, Repo

from app import main


def test_missing_backend_mode_fails_closed_for_repository_routes(monkeypatch, tmp_path):
    monkeypatch.delenv("DOCGUARD_MODE")
    client = TestClient(main.app)
    for response in (
        client.get("/repositories"),
        client.post("/repositories", json={"repository_path": str(tmp_path)}),
    ):
        assert response.status_code == 503
        assert response.json()["detail"] == "DocGuard mode is not configured."


def test_local_repository_registration_and_listing_without_auth(tmp_path, monkeypatch):
    monkeypatch.setenv("DOCGUARD_MODE", "local")
    data = tmp_path / "data"
    monkeypatch.setattr(main, "DATA_DIR", data)
    monkeypatch.setattr(main, "REPOSITORY_FILE", data / "repositories.json")
    repository = tmp_path / "repository"
    repository.mkdir()
    with Repo.init(repository) as repo:
        (repository / "Example.java").write_text("class Example {}", encoding="utf-8")
        repo.index.add(["Example.java"])
        actor = Actor("Test", "test@example.invalid")
        repo.index.commit("Initial", author=actor, committer=actor)
    client = TestClient(main.app)
    assert client.get("/repositories").json() == {"repositories": []}
    added = client.post("/repositories", json={"repository_path": str(repository)})
    assert added.status_code == 200
    assert added.json()["status"] == "success"
    listed = client.get("/repositories")
    assert listed.status_code == 200
    assert listed.json()["repositories"][0]["path"] == str(repository.resolve())
