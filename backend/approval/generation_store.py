import json
import sqlite3
from pathlib import Path
from timing import timed


MAX_RECORDS = 100
MAX_RECORD_BYTES = 3 * 1024 * 1024


@timed("sqlite.connect_and_schema")
def _connect(store_path: str | Path):
    database_path = Path(store_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(
        database_path,
        timeout=30,
        isolation_level=None
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS documentation_generations (
            generation_id TEXT PRIMARY KEY,
            repository_identity TEXT NOT NULL,
            documentation_target TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            record_json TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS one_processing_generation_per_target
        ON documentation_generations(repository_identity, documentation_target)
        WHERE status = 'processing'
        """
    )
    return connection


@timed("sqlite.create_pending_record")
def create_pending_record(
    store_path: str | Path,
    record: dict
) -> None:
    record_json = json.dumps(
        record,
        ensure_ascii=False,
        separators=(",", ":")
    )
    if len(record_json.encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError("Generation preview exceeds the storage size limit.")

    connection = _connect(store_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            DELETE FROM documentation_generations
            WHERE generation_id IN (
                SELECT generation_id
                FROM documentation_generations
                WHERE status IN ('approved', 'rejected', 'stale', 'failed')
                ORDER BY updated_at ASC
                LIMIT MAX(0, (
                    SELECT COUNT(*) FROM documentation_generations
                ) - ?)
            )
            """,
            (MAX_RECORDS - 1,)
        )
        count = connection.execute(
            "SELECT COUNT(*) FROM documentation_generations"
        ).fetchone()[0]
        if count >= MAX_RECORDS:
            raise ValueError(
                "Pending generation storage is full; reject or resolve "
                "existing previews before creating another."
            )
        connection.execute(
            """
            INSERT INTO documentation_generations (
                generation_id,
                repository_identity,
                documentation_target,
                status,
                created_at,
                updated_at,
                record_json
            ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                record["generation_id"],
                record["repository_identity"],
                record["documentation_target"],
                record["created_at"],
                record["created_at"],
                record_json
            )
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@timed("sqlite.get_record")
def get_record(store_path: str | Path, generation_id: str) -> dict | None:
    connection = _connect(store_path)
    try:
        row = connection.execute(
            """
            SELECT record_json, status
            FROM documentation_generations
            WHERE generation_id = ?
            """,
            (generation_id,)
        ).fetchone()
        if row is None:
            return None
        record = json.loads(row["record_json"])
        record["status"] = row["status"]
        return record
    finally:
        connection.close()


@timed("sqlite.reserve_for_approval")
def reserve_for_approval(
    store_path: str | Path,
    generation_id: str,
    updated_at: str
) -> tuple[str, dict | None]:
    connection = _connect(store_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT * FROM documentation_generations
            WHERE generation_id = ?
            """,
            (generation_id,)
        ).fetchone()
        if row is None:
            connection.rollback()
            return "not_found", None
        if row["status"] != "pending":
            connection.rollback()
            return row["status"], json.loads(row["record_json"])

        other_processing = connection.execute(
            """
            SELECT 1 FROM documentation_generations
            WHERE repository_identity = ?
              AND documentation_target = ?
              AND status = 'processing'
              AND generation_id != ?
            """,
            (
                row["repository_identity"],
                row["documentation_target"],
                generation_id
            )
        ).fetchone()
        if other_processing:
            connection.rollback()
            return "target_busy", json.loads(row["record_json"])

        record = json.loads(row["record_json"])
        record["status"] = "processing"
        record["updated_at"] = updated_at
        connection.execute(
            """
            UPDATE documentation_generations
            SET status = 'processing', updated_at = ?, record_json = ?
            WHERE generation_id = ?
            """,
            (
                updated_at,
                json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                generation_id
            )
        )
        connection.commit()
        return "processing", record
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@timed("sqlite.update_record")
def update_record(
    store_path: str | Path,
    generation_id: str,
    status: str,
    updated_at: str,
    additions: dict | None = None,
    expected_status: str | None = None
) -> dict | None:
    connection = _connect(store_path)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT record_json FROM documentation_generations
            WHERE generation_id = ?
            """,
            (generation_id,)
        ).fetchone()
        if row is None:
            connection.rollback()
            return None
        record = json.loads(row["record_json"])
        if expected_status is not None:
            current_status = connection.execute(
                """
                SELECT status FROM documentation_generations
                WHERE generation_id = ?
                """,
                (generation_id,)
            ).fetchone()["status"]
            if current_status != expected_status:
                connection.rollback()
                return None
        if additions:
            record.update(additions)
        record["status"] = status
        record["updated_at"] = updated_at
        connection.execute(
            """
            UPDATE documentation_generations
            SET status = ?, updated_at = ?, record_json = ?
            WHERE generation_id = ?
            """,
            (
                status,
                updated_at,
                json.dumps(record, ensure_ascii=False, separators=(",", ":")),
                generation_id
            )
        )
        connection.commit()
        return record
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


@timed("sqlite.list_audit_records")
def list_audit_records(store_path: str | Path) -> list[dict]:
    connection = _connect(store_path)
    try:
        rows = connection.execute(
            """
            SELECT record_json FROM documentation_generations
            WHERE status IN ('approved', 'rejected', 'stale', 'failed')
            ORDER BY updated_at DESC
            """
        ).fetchall()
        return [
            record["audit"]
            for row in rows
            if (record := json.loads(row["record_json"])).get("audit")
        ]
    finally:
        connection.close()
