import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import main as app_module
from documentation_generation import full_documentation_generator as full_generator
from rag import change_context_retriever, documentation_generator
from rag import indexer, repository_context_retriever, vector_store
from rag.chunker import chunk_markdown
from repository_identity import get_repository_identity


class FakeCollection:
    def __init__(self):
        self.items = {}
        self.last_query = None
        self.fail_upsert = False
        self.fail_query = False

    @staticmethod
    def _matches(metadata, where):
        if not where:
            return True
        if "$and" in where:
            return all(
                FakeCollection._matches(metadata, item)
                for item in where["$and"]
            )
        return all(metadata.get(key) == value for key, value in where.items())

    def upsert(self, ids, documents, embeddings, metadatas):
        if self.fail_upsert:
            raise RuntimeError("mock Chroma upsert failure")
        for document_id, document, embedding, metadata in zip(
            ids,
            documents,
            embeddings,
            metadatas
        ):
            self.items[document_id] = {
                "document": document,
                "embedding": embedding,
                "metadata": metadata
            }

    def get(self, where=None, include=None, ids=None):
        selected = [
            (document_id, item)
            for document_id, item in self.items.items()
            if self._matches(item["metadata"], where)
            and (ids is None or document_id in ids)
        ]
        return {
            "ids": [document_id for document_id, _ in selected],
            "metadatas": [item["metadata"] for _, item in selected],
            "documents": [item["document"] for _, item in selected],
            "embeddings": [item["embedding"] for _, item in selected]
        }

    def query(
        self,
        query_embeddings,
        n_results,
        where=None,
        include=None
    ):
        if self.fail_query:
            raise RuntimeError("mock Chroma query failure")
        self.last_query = {
            "where": where,
            "n_results": n_results
        }
        selected = [
            (document_id, item)
            for document_id, item in self.items.items()
            if self._matches(item["metadata"], where)
            and item["metadata"].get("source_type") == "documentation"
        ][:n_results]
        return {
            "ids": [[document_id for document_id, _ in selected]],
            "documents": [[item["document"] for _, item in selected]],
            "metadatas": [[item["metadata"] for _, item in selected]],
            "distances": [[0.1 for _ in selected]]
        }

    def delete(self, ids):
        for document_id in ids:
            self.items.pop(document_id, None)


@pytest.fixture
def fake_collection(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(vector_store, "collection", collection)
    monkeypatch.setattr(
        indexer,
        "generate_embedding",
        lambda text: [float(len(text))] * 384
    )
    monkeypatch.setattr(
        repository_context_retriever,
        "generate_embedding",
        lambda text: [float(len(text)), 1.0]
    )
    return collection


def write_file(root, relative_path, text):
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def test_repository_identity_is_stable_and_distinct(tmp_path):
    repository_a = tmp_path / "Repo A"
    repository_b = tmp_path / "Repo B"
    repository_a.mkdir()
    repository_b.mkdir()

    assert get_repository_identity(repository_a) == (
        get_repository_identity(str(repository_a).replace("\\", "/"))
    )
    assert get_repository_identity(repository_a) != (
        get_repository_identity(repository_b)
    )


def test_repository_identity_matches_approval_workflow_algorithm(tmp_path):
    canonical_path = str(tmp_path.resolve()).casefold()
    expected = hashlib.sha256(canonical_path.encode("utf-8")).hexdigest()

    assert get_repository_identity(tmp_path) == expected


def test_repository_a_and_b_retrieval_are_isolated(
    tmp_path,
    fake_collection,
    monkeypatch
):
    repository_a = tmp_path / "repo-a"
    repository_b = tmp_path / "repo-b"
    write_file(repository_a, "docs/API.md", "# API\nRepository A behavior.")
    write_file(repository_b, "docs/API.md", "# API\nRepository B secret.")
    indexer.index_repository_documentation(str(repository_a))
    indexer.index_repository_documentation(str(repository_b))
    monkeypatch.setattr(
        repository_context_retriever,
        "generate_embedding",
        lambda _query: [1.0, 1.0]
    )

    result = repository_context_retriever.retrieve_repository_context(
        str(repository_a),
        "API behavior",
        top_k=5
    )

    assert result["available"] is True
    assert all(
        item["repository_id"] == get_repository_identity(repository_a)
        for item in result["metadatas"]
    )
    assert "Repository B secret." not in "\n".join(result["documents"])
    assert fake_collection.last_query["where"]["$and"][0] == {
        "repository_id": get_repository_identity(repository_a)
    }


def test_legacy_untagged_chunks_are_excluded(tmp_path, fake_collection):
    repository = tmp_path / "repo"
    repository.mkdir()
    fake_collection.items["legacy"] = {
        "document": "Legacy unscoped content.",
        "embedding": [1.0, 1.0],
        "metadata": {
            "file": "docs/API.md",
            "type": "documentation"
        }
    }

    result = repository_context_retriever.retrieve_repository_context(
        str(repository),
        "legacy",
        top_k=3
    )

    assert result["available"] is True
    assert result["documents"] == []


def test_unscoped_similarity_query_is_rejected(fake_collection):
    with pytest.raises(ValueError, match="repository_id is required"):
        vector_store.search_documents([1.0, 1.0])
    assert fake_collection.last_query is None


def test_global_collection_clear_is_disabled(fake_collection):
    fake_collection.items["legacy"] = {
        "document": "Preserve all repositories.",
        "embedding": [1.0, 1.0],
        "metadata": {}
    }

    with pytest.raises(ValueError, match="Global collection clearing is disabled"):
        vector_store.clear_collection()

    assert "legacy" in fake_collection.items


def test_new_files_are_indexed_and_unchanged_files_are_skipped(
    tmp_path,
    fake_collection,
    monkeypatch
):
    repository = tmp_path / "repo"
    write_file(repository, "docs/API.md", "# API\nReturns values.")
    calls = []
    monkeypatch.setattr(
        indexer,
        "generate_embedding",
        lambda text: calls.append(text) or [1.0, 1.0]
    )

    first = indexer.index_repository_documentation(str(repository))
    first_ids = set(fake_collection.items)
    second = indexer.index_repository_documentation(str(repository))

    assert first["indexed_files"] == ["docs/API.md"]
    assert first["indexed_chunks"] > 0
    assert second["skipped_files"] == ["docs/API.md"]
    assert second["indexed_chunks"] == 0
    assert set(fake_collection.items) == first_ids
    assert len(calls) == first["indexed_chunks"]


def test_modified_file_is_reindexed_and_old_chunks_removed(
    tmp_path,
    fake_collection
):
    repository = tmp_path / "repo"
    doc = write_file(repository, "docs/API.md", "# API\nVersion one.")
    indexer.index_repository_documentation(str(repository))
    old_ids = set(fake_collection.items)
    doc.write_text("# API\nVersion two.", encoding="utf-8")

    result = indexer.index_repository_documentation(str(repository))

    assert result["indexed_files"] == ["docs/API.md"]
    assert old_ids.isdisjoint(fake_collection.items)
    assert any("Version two." in item["document"]
               for item in fake_collection.items.values())


def test_changed_file_reuses_only_identical_chunks(tmp_path, fake_collection, monkeypatch):
    repository = tmp_path / "repo"
    content = "# Guide\n\n" + "".join(
        f"## Section {i}\n\n" + f"Details for section {i}. " * 40 + "\n\n"
        for i in range(4)
    )
    doc = write_file(repository, "docs/API.md", content)
    calls = []
    monkeypatch.setattr(indexer, "generate_embedding", lambda text: calls.append(text) or [1.0] * 384)
    first = indexer.index_repository_documentation(str(repository))
    old_texts = {item["document"] for item in fake_collection.items.values()}
    calls.clear()
    doc.write_text(content.replace("Details for section 2.", "Updated section 2."), encoding="utf-8")
    updated = indexer.index_repository_documentation(str(repository))
    new_texts = {item["document"] for item in fake_collection.items.values()}

    assert first["indexed_chunks"] > 1
    assert not updated["errors"]
    assert old_texts & new_texts
    assert set(calls) == new_texts - old_texts
    assert all(len(item["embedding"]) == 384 for item in fake_collection.items.values())
    assert len(fake_collection.items) == updated["indexed_chunks"]


def test_real_chroma_retrieval_and_reindexing_are_repository_scoped(tmp_path, monkeypatch):
    import chromadb

    client = chromadb.PersistentClient(path=str(tmp_path / "vectors"))
    collection = client.get_or_create_collection("rag_integration")
    monkeypatch.setattr(vector_store, "collection", collection)

    def embed(text):
        return ([1.0, 0.0] if "alpha" in text.lower() else [0.0, 1.0]) + [0.0] * 382

    monkeypatch.setattr(indexer, "generate_embedding", embed)
    monkeypatch.setattr(repository_context_retriever, "generate_embedding", embed)
    repository_a = tmp_path / "repo-a"
    repository_b = tmp_path / "repo-b"
    doc_a = write_file(repository_a, "API.md", "# API\n\nAlpha guide.")
    write_file(repository_b, "API.md", "# API\n\nAlpha private other repository.")
    assert not indexer.index_repository_documentation(str(repository_a))["errors"]
    assert not indexer.index_repository_documentation(str(repository_b))["errors"]
    result = repository_context_retriever.retrieve_repository_context(str(repository_a), "alpha")
    assert result["available"] and "Alpha guide." in result["documents"][0]
    assert all("private other" not in text for text in result["documents"])
    doc_a.write_text("# API\n\nAlpha updated guide.", encoding="utf-8")
    assert not indexer.index_repository_documentation(str(repository_a))["errors"]
    result = repository_context_retriever.retrieve_repository_context(str(repository_a), "alpha")
    assert "Alpha updated guide." in result["documents"][0]


def test_removed_document_chunks_are_deleted_without_other_repo_changes(
    tmp_path,
    fake_collection
):
    repository_a = tmp_path / "repo-a"
    repository_b = tmp_path / "repo-b"
    stale_doc = write_file(repository_a, "docs/Old.md", "# Old\nOld content.")
    write_file(repository_b, "docs/Keep.md", "# Keep\nOther repository.")
    indexer.index_repository_documentation(str(repository_a))
    indexer.index_repository_documentation(str(repository_b))
    repository_b_ids = {
        document_id
        for document_id, item in fake_collection.items.items()
        if item["metadata"]["repository_id"] == get_repository_identity(
            repository_b
        )
    }
    stale_doc.unlink()

    result = indexer.index_repository_documentation(str(repository_a))

    assert result["deleted_files"] == ["docs/Old.md"]
    assert repository_b_ids.issubset(fake_collection.items)
    assert not any(
        item["metadata"]["repository_id"]
        == get_repository_identity(repository_a)
        for item in fake_collection.items.values()
    )


def test_empty_document_does_not_call_embedding(tmp_path, fake_collection, monkeypatch):
    repository = tmp_path / "repo"
    write_file(repository, "README.md", "")
    monkeypatch.setattr(
        indexer,
        "generate_embedding",
        lambda _text: pytest.fail("Empty documents must not be embedded.")
    )

    result = indexer.index_repository_documentation(str(repository))

    assert result["skipped_files"] == ["README.md"]
    assert result["indexed_chunks"] == 0
    assert fake_collection.items == {}


def test_model_initialization_error_is_reported_in_index_summary(tmp_path, fake_collection, monkeypatch):
    from rag import embedding_generator

    repository = tmp_path / "repo"
    write_file(repository, "API.md", "# API\nDocumentation.")
    monkeypatch.setattr(embedding_generator, "model", None)
    def fail():
        raise OSError("private path")
    monkeypatch.setattr(embedding_generator, "_create_model", fail)
    monkeypatch.setattr(indexer, "generate_embedding", embedding_generator.generate_embedding)
    result = indexer.index_repository_documentation(str(repository))
    assert "Embedding model initialization failed" in result["errors"][0]["message"]
    assert "private path" not in result["errors"][0]["message"]
    assert not fake_collection.items


def test_chunking_preserves_heading_hierarchy():
    chunks = chunk_markdown(
        "# Guide\n\n## Orders\n\n### createOrder\n\nCreates an order.",
        chunk_size=100
    )

    assert len(chunks) == 1
    assert chunks[0]["section_heading"] == "Guide > Orders > createOrder"
    assert "# Guide\n## Orders\n### createOrder" in chunks[0]["text"]


def test_large_sections_are_split_into_bounded_chunks():
    text = "# API\n\n## Long section\n\n" + ("useful detail " * 120)

    chunks = chunk_markdown(text, chunk_size=180)

    assert len(chunks) > 1
    assert all(len(item["text"]) <= 180 for item in chunks)
    assert all(item["section_heading"] == "API > Long section" for item in chunks)


def test_unicode_is_preserved_in_chunks():
    text = "# Price\n\n₹100 — ready → complete."

    chunks = chunk_markdown(text, chunk_size=100)

    assert "₹100 — ready → complete." in chunks[0]["text"]


def test_fenced_code_is_not_split_when_it_fits_and_fake_headings_are_ignored():
    text = (
        "# API\n\n"
        "```java\n"
        "## Not a Markdown section\n"
        "return value;\n"
        "```\n"
    )

    chunks = chunk_markdown(text, chunk_size=200)

    assert len(chunks) == 1
    assert chunks[0]["section_heading"] == "API"
    assert "## Not a Markdown section" in chunks[0]["text"]
    assert chunks[0]["text"].count("```") == 2


def test_large_fenced_code_is_split_with_complete_fences():
    body = "\n".join(f"line_{index}();" for index in range(50))
    chunks = chunk_markdown(
        f"# Code\n\n```java\n{body}\n```",
        chunk_size=120
    )

    assert len(chunks) > 1
    for item in chunks:
        assert item["text"].count("```") == 2
        assert len(item["text"]) <= 120


def test_chunk_ids_are_deterministic(tmp_path, fake_collection):
    repository = tmp_path / "repo"
    write_file(repository, "docs/API.md", "# API\nStable content.")

    indexer.index_repository_documentation(str(repository))
    expected_ids = set(fake_collection.items)
    indexer.index_repository_documentation(str(repository))

    assert set(fake_collection.items) == expected_ids


def test_embedding_failure_preserves_old_valid_chunks(
    tmp_path,
    fake_collection,
    monkeypatch
):
    repository = tmp_path / "repo"
    doc = write_file(repository, "docs/API.md", "# API\nExisting version.")
    indexer.index_repository_documentation(str(repository))
    original = dict(fake_collection.items)
    doc.write_text("# API\nChanged version.", encoding="utf-8")
    monkeypatch.setattr(
        indexer,
        "generate_embedding",
        lambda _text: (_ for _ in ()).throw(RuntimeError("embedding failed"))
    )

    result = indexer.index_repository_documentation(str(repository))
    stale_context = repository_context_retriever.retrieve_repository_context(
        str(repository),
        "Existing version"
    )

    assert result["errors"][0]["stage"] == "document_indexing"
    assert fake_collection.items == original
    assert stale_context["documents"] == []


def test_chroma_upsert_failure_preserves_old_valid_chunks(
    tmp_path,
    fake_collection
):
    repository = tmp_path / "repo"
    doc = write_file(repository, "docs/API.md", "# API\nExisting version.")
    indexer.index_repository_documentation(str(repository))
    original = dict(fake_collection.items)
    doc.write_text("# API\nChanged version.", encoding="utf-8")
    fake_collection.fail_upsert = True

    result = indexer.index_repository_documentation(str(repository))

    assert result["errors"][0]["stage"] == "document_indexing"
    assert fake_collection.items == original


def test_empty_index_and_vector_failure_are_distinguished(
    tmp_path,
    fake_collection
):
    repository = tmp_path / "repo"
    repository.mkdir()

    empty = repository_context_retriever.retrieve_repository_context(
        str(repository),
        "not indexed"
    )
    fake_collection.fail_query = True
    unavailable = repository_context_retriever.retrieve_repository_context(
        str(repository),
        "store failure"
    )

    assert empty["available"] is True
    assert empty["documents"] == []
    assert unavailable["available"] is False
    assert unavailable["error"] == "repository_vector_retrieval_unavailable"
    assert unavailable["documents"] == []


def test_retrieval_limits_top_k_and_total_characters(
    tmp_path,
    fake_collection,
    monkeypatch
):
    repository = tmp_path / "repo"
    write_file(
        repository,
        "docs/API.md",
        "# API\n\n" + "\n\n".join(
            f"## Section {index}\n\n" + ("x" * 1400)
            for index in range(5)
        )
    )
    indexer.index_repository_documentation(str(repository))
    monkeypatch.setattr(
        repository_context_retriever,
        "MAX_CONTEXT_CHARACTERS",
        2500
    )

    result = repository_context_retriever.retrieve_repository_context(
        str(repository),
        "API",
        top_k=3
    )

    assert len(result["documents"]) <= 3
    assert result["context_characters"] <= 2500
    assert fake_collection.last_query["n_results"] == 3


def test_indexing_does_not_modify_markdown_files(tmp_path, fake_collection):
    repository = tmp_path / "repo"
    documentation = write_file(repository, "docs/API.md", "# API\nRead only.")
    before = hashlib.sha256(documentation.read_bytes()).hexdigest()

    indexer.index_repository_documentation(str(repository))

    after = hashlib.sha256(documentation.read_bytes()).hexdigest()
    assert before == after


def test_generated_preview_files_are_not_indexed(tmp_path, fake_collection):
    repository = tmp_path / "repo"
    write_file(repository, "docs/API.md", "# API\nApproved content.")
    write_file(
        repository,
        "docs/API.preview.md",
        "# Repository Documentation\nPending generated preview."
    )

    result = indexer.index_repository_documentation(str(repository))
    indexed_text = "\n".join(
        item["document"] for item in fake_collection.items.values()
    )

    assert result["indexed_files"] == ["docs/API.md"]
    assert "Pending generated preview." not in indexed_text


def test_chunks_have_required_primitive_repository_metadata(
    tmp_path,
    fake_collection
):
    repository = tmp_path / "repo"
    write_file(repository, "docs/API.md", "# API\nRead-only endpoint.")

    indexer.index_repository_documentation(str(repository))

    metadata = next(iter(fake_collection.items.values()))["metadata"]
    assert set(metadata) == {
        "repository_id",
        "documentation_file",
        "section_heading",
        "chunk_index",
        "content_hash",
        "source_type"
    }
    assert metadata["repository_id"] == get_repository_identity(repository)
    assert isinstance(metadata["chunk_index"], int)
    assert all(
        isinstance(value, (str, int, float, bool))
        for value in metadata.values()
    )


def test_full_generation_uses_scoped_retrieved_context_and_bounded_fallback(
    tmp_path,
    monkeypatch
):
    repository = tmp_path / "repo"
    write_file(
        repository,
        "src/A.java",
        "class A {\n    int run() { return 7; }\n}\n"
    )
    write_file(repository, "docs/API.md", "# API\n")
    index_calls = []
    retrieval_calls = []
    prompts = []
    monkeypatch.setattr(
        full_generator,
        "index_repository_documentation",
        lambda path: index_calls.append(path) or {
            "indexed_files": ["docs/API.md"],
            "skipped_files": [],
            "deleted_files": [],
            "indexed_chunks": 1,
            "errors": []
        }
    )

    def retrieve(repository_path, query, top_k=3):
        retrieval_calls.append((repository_path, query, top_k))
        return {
            "available": True,
            "documents": ["Vector-backed API contract."],
            "metadatas": [{
                "documentation_file": "docs/API.md",
                "section_heading": "API > A",
                "content_hash": "hash",
                "chunk_index": 0
            }],
            "distances": [0.1]
        }

    monkeypatch.setattr(
        full_generator,
        "retrieve_repository_context",
        retrieve
    )

    def model(prompt):
        prompts.append(prompt)
        return (
            "**Purpose and behavior**\n"
            "Runs the implementation.\n\n"
            "**Parameters**\n- None.\n\n"
            "**Returns**\n- An integer.\n\n"
            "**Behavior**\n- Returns the computed value."
        )

    monkeypatch.setattr(full_generator, "generate_response", model)

    result = full_generator.generate_full_documentation(
        str(repository),
        include_repository_overview=False
    )

    assert result["generation_status"] == "complete"
    assert len(index_calls) == 1
    assert retrieval_calls
    assert all(call[0] == str(repository.resolve()) for call in retrieval_calls)
    assert "Vector-backed API contract." in "\n".join(prompts)
    assert result["retrieval"]["vector_store_used"] is True
    assert result["retrieval"]["repository_scoped"] is True


def test_full_generation_falls_back_when_vector_store_is_unavailable(
    tmp_path,
    monkeypatch
):
    repository = tmp_path / "repo"
    write_file(
        repository,
        "src/A.java",
        "class A {\n    int run() { return 7; }\n}\n"
    )
    write_file(
        repository,
        "docs/API.md",
        "### A\n\nLocal repository documentation."
    )
    prompts = []
    monkeypatch.setattr(
        full_generator,
        "index_repository_documentation",
        lambda _path: {"errors": [{"stage": "store"}]}
    )
    monkeypatch.setattr(
        full_generator,
        "retrieve_repository_context",
        lambda **_kwargs: {
            "available": False,
            "error": "repository_vector_retrieval_unavailable",
            "documents": [],
            "metadatas": []
        }
    )
    monkeypatch.setattr(
        full_generator,
        "generate_response",
        lambda prompt: prompts.append(prompt) or (
            "**Purpose and behavior**\nRuns.\n\n"
            "**Parameters**\n- None.\n\n"
            "**Returns**\n- An integer.\n\n"
            "**Behavior**\n- Returns a value."
        )
    )

    result = full_generator.generate_full_documentation(
        str(repository),
        include_repository_overview=False
    )

    assert result["retrieval"]["vector_store_used"] is False
    assert result["retrieval"]["fallback_used"] is True
    assert result["retrieval"]["errors"]
    assert "Local repository documentation." in "\n".join(prompts)


def test_incremental_suggestion_uses_repository_scoped_context(
    tmp_path,
    monkeypatch
):
    repository = tmp_path / "repo"
    repository.mkdir()
    calls = []
    monkeypatch.setattr(
        documentation_generator,
        "index_repository_documentation",
        lambda path: calls.append(("index", path)) or {"errors": []}
    )
    monkeypatch.setattr(
        change_context_retriever,
        "retrieve_repository_context",
        lambda repository_path, query, top_k: calls.append(
            ("retrieve", repository_path, query, top_k)
        ) or {
            "available": True,
            "repository_id": get_repository_identity(repository),
            "documents": ["Repository-scoped method docs."],
            "metadatas": [{
                "documentation_file": "docs/API.md",
                "section_heading": "Orders > submit",
                "content_hash": "hash",
                "chunk_index": 0
            }],
            "distances": [0.1]
        }
    )
    received = {}
    monkeypatch.setattr(
        documentation_generator,
        "generate_documentation_suggestion",
        lambda **kwargs: received.update(kwargs) or "Suggestion."
    )

    result = documentation_generator.generate_update_for_change(
        class_name="Orders",
        method_name="submit",
        change_type="modified",
        code="return true;",
        developer_comment="Preserve the order.",
        repository_path=str(repository),
        source_file="src/Orders.java"
    )

    assert calls[0] == ("index", str(repository))
    assert "src/Orders.java" in calls[1][2]
    assert received["developer_comment"] == "Preserve the order."
    assert "Repository-scoped method docs." in received["documentation"]
    assert result["target_documentation"] == "docs/API.md"
    assert result["rag_retrieval"]["repository_scoped"] is True
    assert result["rag_retrieval"]["vector_store_used"] is True


def test_incremental_retrieval_without_repository_fails_closed(monkeypatch):
    monkeypatch.setattr(
        change_context_retriever,
        "retrieve_repository_context",
        lambda *_args, **_kwargs: pytest.fail(
            "Scoped retrieval must not run without repository identity."
        )
    )

    result = change_context_retriever.retrieve_change_context(
        "A",
        "run",
        "modified"
    )

    assert result["available"] is False
    assert result["documents"] == []
    assert result["error"] == "repository_path_required_for_scoped_retrieval"


def test_realistic_multifile_repository_excludes_dependencies_and_previews(
    tmp_path,
    fake_collection
):
    repository = tmp_path / "capstone"
    write_file(repository, "README.md", "# Project\nOverview.")
    write_file(repository, "docs/API.md", "# API\nOrders.")
    write_file(
        repository,
        "node_modules/package/README.md",
        "# Dependency\nMust not index."
    )
    write_file(
        repository,
        "output/preview.md",
        "# Preview\nMust not be indexed."
    )

    summary = indexer.index_repository_documentation(str(repository))
    indexed_text = "\n".join(
        item["document"] for item in fake_collection.items.values()
    )

    assert set(summary["indexed_files"]) == {"README.md", "docs/API.md"}
    assert "Must not index." not in indexed_text
    assert "Must not be indexed." not in indexed_text


def test_vector_status_is_repository_scoped(tmp_path, fake_collection):
    repository_a = tmp_path / "repo-a"
    repository_b = tmp_path / "repo-b"
    write_file(repository_a, "docs/API.md", "# API\nA")
    write_file(repository_b, "docs/API.md", "# API\nB")
    indexer.index_repository_documentation(str(repository_a))
    indexer.index_repository_documentation(str(repository_b))

    status = repository_context_retriever.get_repository_index_status(
        str(repository_a)
    )

    assert status["repository_id"] == get_repository_identity(repository_a)
    assert status["indexed_document_count"] == 1
    assert status["chunk_count"] == 1


def test_rag_api_routes_use_server_derived_repository_identity(
    tmp_path,
    monkeypatch
):
    repository = tmp_path / "repo"
    repository.mkdir()
    client = TestClient(app_module.app)
    monkeypatch.setattr(
        app_module,
        "index_repository_documentation",
        lambda path: {
            "repository": Path(path).name,
            "repository_id": get_repository_identity(path),
            "indexed_files": [],
            "skipped_files": [],
            "deleted_files": [],
            "indexed_chunks": 0,
            "errors": []
        }
    )
    monkeypatch.setattr(
        app_module,
        "get_repository_index_status",
        lambda path: {
            "repository_id": get_repository_identity(path),
            "index_available": True
        }
    )

    indexed = client.post(
        "/rag/index",
        json={
            "repository_path": str(repository),
            "repository_id": "untrusted-client-value"
        }
    )
    status = client.get(
        "/rag/status",
        params={"repository_path": str(repository)}
    )

    assert indexed.status_code == 200
    assert indexed.json()["repository_id"] == get_repository_identity(repository)
    assert status.status_code == 200
    assert status.json()["repository_id"] == get_repository_identity(repository)


def test_suggest_route_preserves_contract_and_passes_validated_repository(
    tmp_path,
    monkeypatch
):
    repository = tmp_path / "repo"
    source = write_file(repository, "src/A.java", "class A { void run() {} }")
    client = TestClient(app_module.app)
    monkeypatch.setattr(
        app_module,
        "analyze_java_file",
        lambda _path: SimpleNamespace(classes=[
            SimpleNamespace(
                name="A",
                methods=[SimpleNamespace(name="run", comment="Runs safely.")]
            )
        ])
    )
    received = {}

    def generate(**kwargs):
        received.update(kwargs)
        return {
            "class": kwargs["class_name"],
            "method": kwargs["method_name"],
            "change_type": kwargs["change_type"],
            "target_documentation": None,
            "retrieved_documents": [],
            "suggestion": "Preview only.",
            "rag_retrieval": {"repository_scoped": True}
        }

    monkeypatch.setattr(app_module, "generate_update_for_change", generate)

    response = client.post(
        "/suggest",
        json={
            "repository_path": str(repository),
            "file_path": "src/A.java",
            "class_name": "A",
            "method_name": "run",
            "change_type": "modified"
        }
    )

    assert response.status_code == 200
    assert response.json()["suggestion"] == "Preview only."
    assert response.json()["developer_comment"] == "Runs safely."
    assert received["repository_path"] == str(repository.resolve())
    assert received["source_file"] == "src/A.java"
    assert source.exists()
    assert ("POST", "/decision") in {
        (method, route.path)
        for route in app_module.app.routes
        for method in getattr(route, "methods", set())
    }
