import hashlib
from datetime import datetime
from pathlib import Path

from approval.generation_markdown import (
    AmbiguousDocumentationMapping,
    atomic_write_markdown,
    merge_generated_documentation
)
from approval.generation_store import (
    get_record,
    reserve_for_approval,
    update_record
)


class GenerationNotFoundError(LookupError):
    pass


class GenerationConflictError(RuntimeError):
    pass


class GenerationStaleError(GenerationConflictError):
    pass


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def _resolve_relative_path(root: Path, relative_path: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Stored file path is not repository-relative.")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError("Stored file path escapes the repository.")
    return resolved


def _hash_file_or_missing(path: Path) -> str:
    if not path.exists():
        return "__missing__"
    if not path.is_file():
        raise OSError("Documentation target is not a regular file.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes_match(root: Path, source_hashes: dict) -> bool:
    for relative_path, expected_hash in source_hashes.items():
        source_path = _resolve_relative_path(root, relative_path)
        if not source_path.is_file():
            return False
        current_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
        if current_hash != expected_hash:
            return False
    return True


def _audit_entry(
    record: dict,
    status: str,
    target_hash_before: str,
    target_hash_after: str,
    failure_reason: str | None = None
) -> dict:
    return {
        "event_type": "documentation_generation",
        "generation_id": record["generation_id"],
        "repository": record["repository"],
        "repository_identity": record["repository_identity"],
        "documentation_target": record["documentation_target"],
        "status": status,
        "timestamp": _now(),
        "source_hashes": record.get("source_hashes", {}),
        "documentation_hash_before": target_hash_before,
        "documentation_hash_after": target_hash_after,
        "generated_classes": [
            {
                "source_file": item.get("source_file"),
                "class": item.get("class"),
                "identity": item.get("identity")
            }
            for item in record.get("generated_classes", [])
        ],
        "generated_methods": [
            {
                "source_file": item.get("source_file"),
                "class": item.get("class"),
                "signature": item.get("signature")
            }
            for item in record.get("generated_methods", [])
        ],
        "failure_reason": failure_reason
    }


def _finalize(
    store_path: str | Path,
    generation_id: str,
    current_status: str,
    final_status: str,
    record: dict,
    target_hash_before: str,
    target_hash_after: str,
    failure_reason: str | None = None
) -> dict:
    audit = _audit_entry(
        record,
        final_status,
        target_hash_before,
        target_hash_after,
        failure_reason
    )
    updated = update_record(
        store_path,
        generation_id,
        status=final_status,
        updated_at=_now(),
        additions={
            "failure_reason": failure_reason,
            "audit": audit
        },
        expected_status=current_status
    )
    if updated is None:
        raise GenerationConflictError(
            "Generation status changed during the decision."
        )
    return updated


def approve_generation(
    store_path: str | Path,
    generation_id: str
) -> dict:
    status, record = reserve_for_approval(
        store_path,
        generation_id,
        _now()
    )
    if status == "not_found":
        raise GenerationNotFoundError("Generation was not found.")
    if status != "processing" or record is None:
        raise GenerationConflictError(
            f"Generation is not pending approval (status: {status})."
        )

    repository_root = Path(record["repository_path"]).resolve()
    if not repository_root.exists() or not repository_root.is_dir():
        return _finalize(
            store_path,
            generation_id,
            "processing",
            "stale",
            record,
            record.get("target_hash_before", "__missing__"),
            "__missing__",
            "Repository is no longer available."
        )

    try:
        target_path = _resolve_relative_path(
            repository_root,
            record["documentation_target"]
        )
        current_target_hash = _hash_file_or_missing(target_path)
        expected_target_hash = record.get(
            "target_hash_before",
            "__missing__"
        )
        if current_target_hash != expected_target_hash:
            return _finalize(
                store_path,
                generation_id,
                "processing",
                "stale",
                record,
                expected_target_hash,
                current_target_hash,
                "Documentation target changed after preview generation."
            )

        if not _source_hashes_match(
            repository_root,
            record.get("source_hashes", {})
        ):
            return _finalize(
                store_path,
                generation_id,
                "processing",
                "stale",
                record,
                expected_target_hash,
                current_target_hash,
                "One or more Java source files changed after preview generation."
            )

        generated_keys = {
            (item.get("source_file"), item.get("class"))
            for item in (
                record.get("generated_classes", [])
                + record.get("generated_methods", [])
            )
        }
        ambiguous_findings = [
            item
            for item in record.get(
                "ambiguous_documentation_mappings",
                []
            )
            if (
                item.get("source_file"),
                item.get("class")
            ) in generated_keys
        ]
        if ambiguous_findings:
            raise AmbiguousDocumentationMapping(
                "Ambiguous documentation mapping prevents automatic insertion."
            )

        existing_content = (
            target_path.read_text(encoding="utf-8")
            if target_path.exists()
            else ""
        )
        merged_content = merge_generated_documentation(
            existing_content,
            record
        )
        if merged_content != existing_content:
            atomic_write_markdown(target_path, merged_content)
        target_hash_after = _hash_file_or_missing(target_path)
        return _finalize(
            store_path,
            generation_id,
            "processing",
            "approved",
            record,
            expected_target_hash,
            target_hash_after
        )
    except Exception as error:
        try:
            current_target_hash = (
                _hash_file_or_missing(target_path)
                if "target_path" in locals()
                else record.get("target_hash_before", "__missing__")
            )
        except OSError:
            current_target_hash = "unavailable"
        return _finalize(
            store_path,
            generation_id,
            "processing",
            "failed",
            record,
            record.get("target_hash_before", "__missing__"),
            current_target_hash,
            str(error)
        )


def reject_generation(
    store_path: str | Path,
    generation_id: str
) -> dict:
    record = get_record(store_path, generation_id)
    if record is None:
        raise GenerationNotFoundError("Generation was not found.")
    if record.get("status") != "pending":
        raise GenerationConflictError(
            "Generation is not pending approval "
            f"(status: {record.get('status')})."
        )

    target_path = _resolve_relative_path(
        Path(record["repository_path"]).resolve(),
        record["documentation_target"]
    )
    try:
        current_target_hash = _hash_file_or_missing(target_path)
    except OSError:
        current_target_hash = "unavailable"
    target_hash_before = record.get(
        "target_hash_before",
        "__missing__"
    )
    updated = _finalize(
        store_path,
        generation_id,
        "pending",
        "rejected",
        record,
        target_hash_before,
        current_target_hash
    )
    return updated
