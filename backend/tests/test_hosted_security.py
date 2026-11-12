import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import main, security
from approval.generation_store import create_pending_record
from rag import documentation_generator, indexer, repository_context_retriever, vector_store
from repository_identity import get_repository_identity
from test_repository_scoped_rag import FakeCollection


@pytest.fixture
def hosted(tmp_path, monkeypatch):
    root = tmp_path / "workspaces"
    root.mkdir()
    monkeypatch.setenv("DOCGUARD_MODE", "hosted")
    monkeypatch.setenv("DOCGUARD_OIDC_ISSUER", "https://id.example.test")
    monkeypatch.setenv("DOCGUARD_OIDC_AUDIENCE", "docguard-api")
    monkeypatch.setenv("DOCGUARD_OIDC_ALGORITHMS", "RS256")
    monkeypatch.setenv("DOCGUARD_WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("DOCGUARD_WORKSPACE_DATABASE", str(tmp_path / "workspaces.sqlite3"))
    monkeypatch.setattr(main, "GENERATION_STORE_PATH", tmp_path / "generations.sqlite3")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})

    def fake_fetch(url):
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": "https://id.example.test", "jwks_uri": "https://id.example.test/keys"}
        assert url == "https://id.example.test/keys"
        return {"keys": [jwk]}

    monkeypatch.setattr(security, "_get_json", fake_fetch)
    return TestClient(main.app), root, key


def token(key, **overrides):
    claims = {
        "iss": "https://id.example.test",
        "aud": "docguard-api",
        "sub": "alice",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        **overrides,
    }
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "test-key"})


def headers(key, **overrides):
    return {"Authorization": f"Bearer {token(key, **overrides)}"}


def workspace(root, subject="alice", expiry=None, create=True):
    access = security.Access("hosted", "https://id.example.test", subject)
    repository_id = security.create_workspace(
        access, expiry or datetime.now(timezone.utc) + timedelta(hours=1), "Example"
    )
    path = root / repository_id
    if create:
        path.mkdir()
        (path / "Example.java").write_text("class Example {}", encoding="utf-8")
    return repository_id, path


def test_valid_token_and_owned_repository(hosted):
    client, root, key = hosted
    repository_id, path = workspace(root)
    response = client.post("/analyze/full", headers=headers(key), json={"repository_id": repository_id})
    assert response.status_code == 200
    assert response.json()["summary"]["java_file_count"] == 1
    assert str(path) not in response.text
    listed = client.get("/repositories", headers=headers(key))
    assert listed.json()["repositories"] == [{"id": repository_id, "name": "Example"}]
    assert client.post("/repositories", headers=headers(key), json={"repository_id": repository_id}).status_code == 403


@pytest.mark.parametrize("changes", [
    {"iss": "https://wrong.example.test"},
    {"aud": "another-api"},
    {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    {"sub": ""},
])
def test_invalid_claims(hosted, changes):
    client, _, key = hosted
    assert client.get("/repositories", headers=headers(key, **changes)).status_code == 401


def test_invalid_signature_and_missing_token(hosted):
    client, _, key = hosted
    assert client.get("/repositories").status_code == 401
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    assert client.get("/repositories", headers=headers(other)).status_code == 401
    assert client.get("/repositories", headers={"Authorization": "Bearer malformed"}).status_code == 401
    assert client.get("/repositories", headers=headers(key)).status_code == 200
    no_signature = jwt.encode(
        {"iss": "https://id.example.test", "aud": "docguard-api", "sub": "alice",
         "exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        key="", algorithm="none", headers={"kid": "test-key"},
    )
    assert client.get("/repositories", headers={"Authorization": f"Bearer {no_signature}"}).status_code == 401


@pytest.mark.parametrize("endpoint", ["/analyze/full", "/analyze", "/rag/index", "/documentation/generate/full"])
def test_cross_user_repository_access(hosted, endpoint):
    client, root, key = hosted
    repository_id, _ = workspace(root)
    response = client.post(endpoint, headers=headers(key, sub="bob"), json={"repository_id": repository_id})
    assert response.status_code == 404


def test_hosted_paths_are_rejected(hosted):
    client, root, key = hosted
    repository_id, path = workspace(root)
    for payload in [
        {"repository_path": str(path)},
        {"repository_path": str(path), "repository_id": repository_id},
        {"repository_id": str(path)},
    ]:
        assert client.post("/analyze/full", headers=headers(key), json=payload).status_code == 400
    assert client.get("/rag/status", headers=headers(key), params={"repository_path": str(path)}).status_code == 400


def test_suggestion_and_legacy_decision_require_workspace_ownership(hosted):
    client, root, key = hosted
    repository_id, _ = workspace(root)
    bob = headers(key, sub="bob")
    suggestion = {
        "repository_id": repository_id, "file_path": "Example.java",
        "class_name": "Example", "method_name": "run", "change_type": "method_added",
    }
    decision = {
        "repository_id": repository_id, "documentation_file": "README.md",
        "class_name": "Example", "method_name": "run", "decision": "reject",
    }
    assert client.post("/suggest", headers=bob, json=suggestion).status_code == 404
    assert client.post("/decision", headers=bob, json=decision).status_code == 404
    assert client.post("/decision", headers=headers(key), json=decision).status_code == 403


def test_missing_and_expired_workspaces(hosted):
    client, root, key = hosted
    missing, _ = workspace(root, create=False)
    expired, _ = workspace(root, expiry=datetime.now(timezone.utc) - timedelta(seconds=1))
    for repository_id in [missing, expired, "f" * 32]:
        assert client.post("/analyze/full", headers=headers(key), json={"repository_id": repository_id}).status_code == 404


def test_approval_and_history_require_workspace_owner(hosted):
    client, root, key = hosted
    repository_id, path = workspace(root)
    record = {
        "generation_id": "preview",
        "repository": "Example",
        "repository_identity": get_repository_identity(path),
        "workspace_id": repository_id,
        "repository_path": str(path.resolve()),
        "documentation_target": "README.md",
        "generated_markdown": "# Example",
        "generation_status": "complete",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_hashes": {},
        "target_hash_before": "__missing__",
    }
    create_pending_record(main.GENERATION_STORE_PATH, record)
    bob = headers(key, sub="bob")
    assert client.get("/documentation/generation/preview", headers=bob).status_code == 404
    assert client.post("/documentation/generation/preview/approve", headers=bob, json={"decision": "approve"}).status_code == 404
    assert not (path / "README.md").exists()
    alice = headers(key)
    preview = client.get("/documentation/generation/preview", headers=alice)
    assert preview.status_code == 200
    assert preview.json()["repository_identity"] == repository_id
    approved = client.post("/documentation/generation/preview/approve", headers=alice, json={"decision": "approve"})
    assert approved.status_code == 200
    assert (path / "README.md").is_file()
    assert len(client.get("/history", headers=alice).json()["history"]) == 1
    assert client.get("/history", headers=bob).json()["history"] == []


def test_hosted_generation_and_approval_share_workspace(hosted, monkeypatch):
    client, root, key = hosted
    repository_id, path = workspace(root)
    observed = []

    def generate(**kwargs):
        observed.append(kwargs["repository_path"])
        return {
            "generation_status": "complete",
            "generated_markdown": "# Example",
            "documentation_target": "README.md",
            "source_hashes": {},
            "errors": [],
        }

    monkeypatch.setattr(main, "generate_full_documentation", generate)
    response = client.post("/documentation/generate/full", headers=headers(key), json={"repository_id": repository_id})
    assert response.status_code == 200
    assert observed == [str(path)]
    generation_id = response.json()["generation_id"]
    assert str(path) not in response.text
    assert client.post(f"/documentation/generation/{generation_id}/approve", headers=headers(key, sub="bob"), json={"decision": "approve"}).status_code == 404
    assert client.post(f"/documentation/generation/{generation_id}/approve", headers=headers(key), json={"decision": "approve"}).status_code == 200
    assert (path / "README.md").exists()


def test_configuration_fails_closed(hosted, monkeypatch):
    client, _, key = hosted
    monkeypatch.delenv("DOCGUARD_OIDC_AUDIENCE")
    assert client.get("/repositories", headers=headers(key)).status_code == 503


@pytest.mark.parametrize("method,url,payload", [
    ("get", "/repositories", None),
    ("get", "/history", None),
    ("get", "/rag/status", None),
    ("get", "/documentation/generation/preview", None),
    ("post", "/suggest", {}),
    ("post", "/decision", {}),
    ("post", "/rag/index", {}),
    ("post", "/analyze", {}),
    ("post", "/analyze/full", {}),
    ("post", "/documentation/generate/full", {}),
    ("post", "/documentation/generation/preview/approve", {}),
    ("post", "/documentation/generation/preview/reject", {}),
    ("delete", "/repositories/1", None),
])
def test_all_repository_operations_require_authentication(hosted, method, url, payload):
    client, _, _ = hosted
    response = client.request(method, url, json=payload)
    assert response.status_code == 401


def test_hosted_rag_uses_resolved_workspace_identity(hosted, monkeypatch):
    client, root, key = hosted
    repository_id, path = workspace(root)
    monkeypatch.setattr(main, "index_repository_documentation", lambda p: {
        "repository_id": get_repository_identity(p), "errors": []
    })
    monkeypatch.setattr(main, "get_repository_index_status", lambda p: {
        "repository_id": get_repository_identity(p), "index_available": True
    })
    indexed = client.post("/rag/index", headers=headers(key), json={"repository_id": repository_id})
    status = client.get("/rag/status", headers=headers(key), params={"repository_id": repository_id})
    assert indexed.json()["repository_id"] == repository_id
    assert status.json()["repository_id"] == repository_id
    assert str(path) not in indexed.text
    assert client.get("/rag/status", headers=headers(key, sub="bob"), params={"repository_id": repository_id}).status_code == 404


def test_cross_user_cannot_trigger_rag_retrieval_via_suggestion(hosted, monkeypatch):
    client, root, key = hosted
    repository_id, path = workspace(root)
    called = []

    def generate(**kwargs):
        called.append(kwargs["repository_path"])
        return {"suggestion": "Generated", "rag_retrieval": {"repository_id": get_repository_identity(path)}}

    monkeypatch.setattr(main, "generate_update_for_change", generate)
    payload = {
        "repository_id": repository_id, "file_path": "Example.java",
        "class_name": "Example", "method_name": "run", "change_type": "method_added",
    }
    assert client.post("/suggest", headers=headers(key, sub="bob"), json=payload).status_code == 404
    assert called == []
    response = client.post("/suggest", headers=headers(key), json=payload)
    assert response.status_code == 200
    assert response.json()["rag_retrieval"]["repository_id"] == repository_id
    assert called == [str(path)]
    assert str(path) not in response.text


def test_hosted_rag_retrieval_is_scoped_to_workspace_owner(hosted, monkeypatch):
    client, root, key = hosted
    alice_id, alice_path = workspace(root)
    bob_id, bob_path = workspace(root, subject="bob")
    (alice_path / "README.md").write_text("# API\nAlice private documentation.", encoding="utf-8")
    (bob_path / "README.md").write_text("# API\nBob private documentation.", encoding="utf-8")
    monkeypatch.setattr(vector_store, "collection", FakeCollection())
    monkeypatch.setattr(indexer, "generate_embedding", lambda text: [1.0] * 384)
    monkeypatch.setattr(repository_context_retriever, "generate_embedding", lambda text: [1.0] * 384)
    prompts = []

    def generate(**kwargs):
        prompts.append(kwargs["documentation"])
        return "Generated"

    monkeypatch.setattr(documentation_generator, "generate_documentation_suggestion", generate)
    assert client.post("/rag/index", headers=headers(key), json={"repository_id": alice_id}).status_code == 200
    assert client.post("/rag/index", headers=headers(key, sub="bob"), json={"repository_id": bob_id}).status_code == 200
    payload = {
        "repository_id": alice_id, "file_path": "Example.java",
        "class_name": "Example", "method_name": "run", "change_type": "method_added",
    }
    assert client.post("/suggest", headers=headers(key, sub="bob"), json=payload).status_code == 404
    assert prompts == []
    response = client.post("/suggest", headers=headers(key), json=payload)
    assert response.status_code == 200
    assert response.json()["rag_retrieval"]["repository_id"] == alice_id
    assert response.json()["rag_retrieval"]["vector_store_used"] is True
    assert "Alice private documentation." in prompts[0]
    assert "Bob private documentation." not in prompts[0]


def test_untrusted_discovery_host_is_rejected(hosted, monkeypatch):
    client, _, key = hosted
    monkeypatch.setattr(security, "_get_json", lambda url: {
        "issuer": "https://id.example.test",
        "jwks_uri": "https://untrusted.example.test/keys",
    })
    assert client.get("/repositories", headers=headers(key)).status_code == 503
    monkeypatch.setenv("DOCGUARD_MODE", "")
    assert client.get("/repositories", headers=headers(key)).status_code == 503


def test_configured_cross_host_jwks(hosted, monkeypatch):
    client, _, key = hosted
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": "test-key", "alg": "RS256", "use": "sig"})
    monkeypatch.setenv("DOCGUARD_OIDC_JWKS_HOSTS", "keys.example.test")

    def fake_fetch(url):
        if url.endswith("/.well-known/openid-configuration"):
            return {"issuer": "https://id.example.test", "jwks_uri": "https://keys.example.test/keys"}
        assert url == "https://keys.example.test/keys"
        return {"keys": [jwk]}

    monkeypatch.setattr(security, "_get_json", fake_fetch)
    assert client.get("/repositories", headers=headers(key)).status_code == 200


def test_local_path_compatibility(tmp_path):
    response = TestClient(main.app).post("/analyze/full", json={"repository_path": str(tmp_path)})
    assert response.status_code == 200
