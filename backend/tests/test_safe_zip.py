import io
import stat
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest

from analyzer.repository_analyzer import analyze_full_repository
from repository.safe_zip import ArchiveLimits, UnsafeArchiveError, extract_validated_zip


def archive(entries):
    buffer = io.BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as output:
        for name, content in entries:
            output.writestr(name, content)
    buffer.seek(0)
    return buffer


@pytest.mark.parametrize("name", [
    "../outside.java", "/absolute.txt", "a/../../escape",
    "C:/escape", "a//b", "a/./b", ".git/config", "repo/.GIT/config",
    "folder./file", "folder /file", "file:stream", "NUL.txt",
    "dir/COM1", "bad?name",
])
def test_rejects_unsafe_paths_before_writing(tmp_path, name):
    data = archive([("safe.txt", "safe"), (name, "bad")])
    with pytest.raises(UnsafeArchiveError):
        extract_validated_zip(data, tmp_path, ArchiveLimits(10, 1024))
    assert list(tmp_path.iterdir()) == []


def test_rejects_backslash_archive_path(tmp_path):
    data = archive([("a@escape", "bad")]).getvalue().replace(b"a@escape", b"a\\escape")
    with pytest.raises(UnsafeArchiveError):
        extract_validated_zip(io.BytesIO(data), tmp_path, ArchiveLimits(10, 1024))
    assert list(tmp_path.iterdir()) == []


def test_rejects_symlink_and_special_files(tmp_path):
    for mode in [stat.S_IFLNK | 0o777, stat.S_IFIFO | 0o600]:
        info = ZipInfo("malicious")
        info.create_system = 3
        info.external_attr = mode << 16
        with pytest.raises(UnsafeArchiveError):
            extract_validated_zip(archive([(info, "target")]), tmp_path, ArchiveLimits(10, 1024))
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("entries", [
    [("a.txt", "1"), ("A.TXT", "2")],
    [("a", "1"), ("a/b", "2")],
    [("a/", ""), ("a", "2")],
])
def test_rejects_duplicate_and_conflicting_paths(tmp_path, entries):
    with pytest.raises(UnsafeArchiveError):
        extract_validated_zip(archive(entries), tmp_path, ArchiveLimits(10, 1024))
    assert list(tmp_path.iterdir()) == []


def test_enforces_entry_and_expanded_size_limits(tmp_path):
    with pytest.raises(UnsafeArchiveError, match="entries"):
        extract_validated_zip(archive([("a", "a"), ("b", "b")]), tmp_path, ArchiveLimits(1, 100))
    with pytest.raises(UnsafeArchiveError, match="size"):
        extract_validated_zip(archive([("a", "A" * 1000)]), tmp_path, ArchiveLimits(10, 100))
    assert list(tmp_path.iterdir()) == []


def test_extracts_source_for_existing_analysis(tmp_path):
    data = archive([
        ("src/Example.java", "class Example { int value() { return 1; } }"),
        ("README.md", "# Example"),
    ])
    extract_validated_zip(data, tmp_path, ArchiveLimits(10, 4096))
    result = analyze_full_repository(str(tmp_path))
    assert result["summary"]["java_file_count"] == 1
    assert result["summary"]["class_count"] == 1
    assert Path(tmp_path, "README.md").read_text(encoding="utf-8") == "# Example"


def test_rejects_invalid_archive_and_nonempty_destination(tmp_path):
    with pytest.raises(UnsafeArchiveError):
        extract_validated_zip(io.BytesIO(b"not a zip"), tmp_path, ArchiveLimits(10, 100))
    (tmp_path / "existing").write_text("unchanged", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        extract_validated_zip(archive([("a", "data")]), tmp_path, ArchiveLimits(10, 100))
    assert (tmp_path / "existing").read_text(encoding="utf-8") == "unchanged"
