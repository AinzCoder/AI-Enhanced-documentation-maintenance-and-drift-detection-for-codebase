import pytest


@pytest.fixture(autouse=True)
def trusted_local_test_mode(monkeypatch):
    monkeypatch.setenv("DOCGUARD_MODE", "local")
