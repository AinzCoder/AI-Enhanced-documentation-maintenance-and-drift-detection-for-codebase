from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock

import pytest

from rag import embedding_generator


def test_sequential_embeddings_share_model(monkeypatch):
    class Model:
        def encode(self, text, normalize_embeddings):
            assert normalize_embeddings
            return Vector(text)

    class Vector:
        def __init__(self, value):
            self.value = value

        def tolist(self):
            return [self.value]

    calls = []
    instance = Model()
    monkeypatch.setattr(embedding_generator, "model", None)
    monkeypatch.setattr(embedding_generator, "_create_model", lambda: calls.append(1) or instance)
    assert embedding_generator.generate_embedding("first") == ["first"]
    assert embedding_generator.generate_embedding("second") == ["second"]
    assert calls == [1]


def test_concurrent_initialization_constructs_only_once(monkeypatch):
    entered, release = Event(), Event()
    calls = []
    count_lock = Lock()
    instance = object()

    def create():
        with count_lock:
            calls.append(1)
        entered.set()
        assert release.wait(5)
        return instance

    monkeypatch.setattr(embedding_generator, "model", None)
    monkeypatch.setattr(embedding_generator, "_create_model", create)
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(embedding_generator._load_model) for _ in range(8)]
        assert entered.wait(5)
        release.set()
        assert all(future.result(timeout=5) is instance for future in futures)
    assert calls == [1]


def test_failed_initialization_is_explicit_and_can_be_retried(monkeypatch, caplog):
    monkeypatch.setattr(embedding_generator, "model", None)
    def fail():
        raise OSError("sensitive underlying details")
    monkeypatch.setattr(embedding_generator, "_create_model", fail)

    with pytest.raises(embedding_generator.EmbeddingModelInitializationError, match="check the local model cache"):
        embedding_generator._load_model()
    assert embedding_generator.model is None
    assert "sensitive underlying details" not in caplog.text
