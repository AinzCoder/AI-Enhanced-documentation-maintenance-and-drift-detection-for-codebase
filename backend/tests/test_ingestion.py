import io
import shutil
import subprocess
import threading
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from git import Actor, Repo

from analyzer.repository_analyzer import analyze_full_repository
from app import main, security
from repository import ingestion
from repository.ingestion import ImportFailed, IngestionService
from repository.safe_zip import ArchiveLimits, UnsafeArchiveError
from repository.workspace_provisioner import (
    ProvisioningUnavailable, StagingWorkspace, UnavailableProvisioner
)


@pytest.fixture
def storage(tmp_path, monkeypatch):
    root = tmp_path / "workspaces"
    root.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    monkeypatch.setenv("DOCGUARD_OIDC_ISSUER", "https://id.example.test")
    monkeypatch.setenv("DOCGUARD_OIDC_AUDIENCE", "api")
    monkeypatch.setenv("DOCGUARD_OIDC_ALGORITHMS", "RS256")
    monkeypatch.setenv("DOCGUARD_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("DOCGUARD_WORKSPACE_DATABASE", str(tmp_path / "workspace.sqlite"))

    class FakeProvisioner:
        def __init__(self):
            self.ready = True
            self.discarded = []
            self.fail_publish = False

        def verify_ready(self):
            if not self.ready:
                raise ProvisioningUnavailable("test quota failure")

        def cleanup_expired(self):
            pass

        def allocate(self, owner, expires_at):
            repository_id = security.create_workspace(owner, expires_at, "Test")
            directory = staging / repository_id
            directory.mkdir()
            return StagingWorkspace(repository_id, directory)

        def publish(self, workspace, owner, display_name):
            if self.fail_publish:
                raise ProvisioningUnavailable("test publish failure")
            (workspace.directory / "repository").rename(root / workspace.repository_id)
            workspace.directory.rmdir()

        def discard(self, workspace):
            self.discarded.append(workspace.repository_id)
            shutil.rmtree(workspace.directory)
            _, _, _, _, database = security._configuration()
            with security._connect(database) as connection:
                connection.execute("DELETE FROM workspaces WHERE repository_id = ?", (workspace.repository_id,))

    return FakeProvisioner(), root, staging


@pytest.fixture
def owner():
    return security.Access("hosted", "https://id.example.test", "alice")


@pytest.fixture
def expiry():
    return datetime.now(timezone.utc) + timedelta(hours=1)


def service(provider, limit=1024):
    return IngestionService(provider, upload_limit=limit, archive_limits=ArchiveLimits(10, 4096))


def zipped(entries):
    output = io.BytesIO()
    with ZipFile(output, "w") as archive:
        for name, content in entries:
            archive.writestr(name, content)
    return output.getvalue()


def test_unavailable_quota_fails_closed(owner, expiry):
    with pytest.raises(ProvisioningUnavailable):
        service(UnavailableProvisioner()).import_zip(owner, expiry, [b"data"])


def test_clone_success_ownership_and_analysis(storage, owner, expiry, monkeypatch):
    provider, root, staging = storage
    observed = []

    def clone(url, destination, timeout):
        observed.append((url, timeout))
        destination.mkdir()
        (destination / "Example.java").write_text("class Example {}", encoding="utf-8")

    monkeypatch.setattr(ingestion, "_clone", clone)
    repository_id = service(provider).import_github(owner, expiry, "https://github.com/example/project")
    assert observed == [("https://github.com/example/project.git", 120)]
    workspace = security.resolve_repository(owner, None, repository_id)
    assert workspace.path == root / repository_id
    assert analyze_full_repository(str(workspace.path))["summary"]["java_file_count"] == 1
    with pytest.raises(HTTPException) as error:
        security.resolve_repository(security.Access("hosted", owner.issuer, "bob"), None, repository_id)
    assert error.value.status_code == 404
    assert list(staging.iterdir()) == []


@pytest.mark.parametrize("error", [ImportFailed("clone failed"), subprocess.TimeoutExpired("git", 1)])
def test_clone_failure_discards_staging(storage, owner, expiry, monkeypatch, error):
    provider, root, staging = storage
    def fail(*args):
        raise error
    monkeypatch.setattr(ingestion, "_clone", fail)
    with pytest.raises(type(error)):
        service(provider).import_github(owner, expiry, "https://github.com/example/project")
    assert provider.discarded
    assert list(root.iterdir()) == []
    assert list(staging.iterdir()) == []


def test_zip_streaming_success_and_limit(storage, owner, expiry):
    provider, root, staging = storage
    data = zipped([("Example.java", "class Example {}")])
    repository_id = service(provider).import_zip(owner, expiry, [data[:7], data[7:]])
    assert (root / repository_id / "Example.java").is_file()
    with pytest.raises(ImportFailed, match="size"):
        service(provider, limit=2).import_zip(owner, expiry, [b"aa", b"b"])
    assert provider.discarded
    assert list(staging.iterdir()) == []


@pytest.mark.parametrize("source", ["github", "zip"])
def test_imported_workspace_through_analysis_api(storage, owner, expiry, monkeypatch, source):
    provider, root, staging = storage
    monkeypatch.setitem(main.app.dependency_overrides, main.authenticate, lambda: owner)
    if source == "github":
        def clone(_url, destination, _timeout):
            destination.mkdir()
            (destination / "Example.java").write_text("class Example {}", encoding="utf-8")
            repo = Repo.init(destination)
            repo.index.add(["Example.java"])
            actor = Actor("Test", "test@example.invalid")
            repo.index.commit("Initial", author=actor, committer=actor)
            repo.close()
        monkeypatch.setattr(ingestion, "_clone", clone)
        repository_id = service(provider).import_github(owner, expiry, "https://github.com/example/project")
    else:
        archive = zipped([("Example.java", "class Example {}"), ("README.md", "# Example")])
        repository_id = service(provider).import_zip(owner, expiry, [archive[:11], archive[11:]])

    client = TestClient(main.app)
    response = client.post("/analyze/full", json={"repository_id": repository_id})
    assert response.status_code == 200
    assert response.json()["summary"]["java_file_count"] == 1
    assert str(root / repository_id) not in response.text
    drift = client.post("/analyze", json={"repository_id": repository_id})
    if source == "github":
        assert drift.status_code == 200
    else:
        assert drift.status_code == 400
        assert "Git repository" in drift.json()["detail"]
        assert str(root) not in drift.text
    assert list(staging.iterdir()) == []


def test_unsafe_zip_and_publish_failure_cleanup(storage, owner, expiry):
    provider, root, staging = storage
    with pytest.raises(UnsafeArchiveError):
        service(provider).import_zip(owner, expiry, [zipped([("../escape", "bad")])])
    provider.fail_publish = True
    with pytest.raises(ProvisioningUnavailable):
        service(provider).import_zip(owner, expiry, [zipped([("a", "data")])])
    assert len(provider.discarded) == 2
    assert list(staging.iterdir()) == []
    assert list(root.iterdir()) == []


def test_quota_check_and_input_fail_before_allocation(storage, owner, expiry):
    provider, _, staging = storage
    provider.ready = False
    with pytest.raises(ProvisioningUnavailable):
        service(provider).import_github(owner, expiry, "https://github.com/example/project")
    with pytest.raises(ValueError):
        service(provider).import_github(owner, expiry, "https://evil.example/project")
    assert list(staging.iterdir()) == []


def test_process_import_capacity_rejects_excess_before_allocation(storage, owner, expiry, monkeypatch):
    provider, root, staging = storage
    slots = threading.BoundedSemaphore(2)
    monkeypatch.setattr(ingestion, "_IMPORT_SLOTS", slots)
    assert slots.acquire(blocking=False)
    assert slots.acquire(blocking=False)
    try:
        with pytest.raises(ingestion.ImportBusy):
            service(provider).import_zip(owner, expiry, [b"data"])
        assert not list(staging.iterdir())
        assert not list(root.iterdir())
    finally:
        slots.release()
        slots.release()


def test_untrusted_or_expired_owner_rejected(storage, expiry):
    provider, _, staging = storage
    with pytest.raises(ImportFailed, match="owner"):
        service(provider).import_zip(security.Access("local"), expiry, [b"data"])
    owner = security.Access("hosted", "https://id.example.test", "alice")
    with pytest.raises(ImportFailed, match="expiration"):
        service(provider).import_zip(owner, datetime.now(timezone.utc) - timedelta(seconds=1), [b"data"])
    assert list(staging.iterdir()) == []


def test_lost_quota_readiness_discards_allocated_workspace(storage, owner, expiry):
    provider, root, staging = storage
    data = zipped([("a", "data")])
    def chunks():
        yield data
        provider.ready = False
    with pytest.raises(ProvisioningUnavailable):
        service(provider).import_zip(owner, expiry, chunks())
    assert provider.discarded
    assert not list(staging.iterdir())
    assert not list(root.iterdir())


def test_clone_process_uses_hardened_arguments_and_environment(tmp_path, monkeypatch):
    observed = {}
    class Process:
        pid = 1234
        def wait(self, timeout=None):
            observed["timeout"] = timeout
            return 0
    def popen(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        return Process()
    monkeypatch.setattr(ingestion, "os", SimpleNamespace(name="posix", defpath="/bin", devnull="/dev/null"))
    monkeypatch.setattr(ingestion.subprocess, "Popen", popen)
    ingestion._clone("https://github.com/example/project.git", tmp_path / "repository", 8)
    assert "--no-recurse-submodules" in observed["command"]
    assert "http.followRedirects=false" in observed["command"]
    assert "core.hooksPath=/dev/null" in observed["command"]
    assert observed["kwargs"]["env"]["GIT_LFS_SKIP_SMUDGE"] == "1"
    assert observed["kwargs"]["env"]["GIT_CONFIG_NOSYSTEM"] == "1"
    assert observed["kwargs"]["start_new_session"]
    assert observed["timeout"] == 8
    assert "shell" not in observed["kwargs"]


def test_clone_timeout_kills_process_group(tmp_path, monkeypatch):
    killed = []
    class Process:
        pid = 1234
        def wait(self, timeout=None):
            if timeout is not None:
                raise subprocess.TimeoutExpired("git", timeout)
            return -9
    monkeypatch.setattr(ingestion, "os", SimpleNamespace(
        name="posix", defpath="/bin", devnull="/dev/null",
        killpg=lambda pid, sig: killed.append((pid, sig))
    ))
    monkeypatch.setattr(ingestion, "signal", SimpleNamespace(SIGKILL=9))
    monkeypatch.setattr(ingestion.subprocess, "Popen", lambda *args, **kwargs: Process())
    with pytest.raises(ImportFailed, match="timed out"):
        ingestion._clone("https://github.com/example/project.git", tmp_path / "repository", 1)
    assert killed == [(1234, ingestion.signal.SIGKILL)]
