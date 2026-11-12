"""ZIP validation for future imports into private, quota-enforced workspaces.

The caller must supply a seekable, size-limited archive and an exclusively
owned empty destination on quota-enforced storage. This module is not a quota
enforcement mechanism or a public upload endpoint.
"""

import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from zipfile import BadZipFile, ZipFile, ZipInfo


_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class UnsafeArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class ArchiveLimits:
    max_entries: int
    max_uncompressed_bytes: int

    def __post_init__(self):
        if self.max_entries <= 0 or self.max_uncompressed_bytes <= 0:
            raise ValueError("Archive limits must be positive.")


def _entry_path(info: ZipInfo) -> tuple[str, ...]:
    name = info.orig_filename
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or name.startswith("/")
        or any(ord(char) < 32 for char in name)
    ):
        raise UnsafeArchiveError("Archive contains an unsafe path.")

    parts = name.rstrip("/").split("/")
    if any(
        not part or part in {".", ".."}
        or any(char in '<>:"|?*' for char in part)
        or part.endswith((".", " "))
        or part.casefold() == ".git"
        or part.split(".", 1)[0].upper() in _WINDOWS_RESERVED
        for part in parts
    ):
        raise UnsafeArchiveError("Archive contains an unsafe path.")
    if PurePosixPath(name).is_absolute():
        raise UnsafeArchiveError("Archive contains an unsafe path.")

    mode = info.external_attr >> 16
    kind = stat.S_IFMT(mode)
    if kind not in {0, stat.S_IFDIR, stat.S_IFREG}:
        raise UnsafeArchiveError("Archive contains an unsupported file type.")
    if (kind == stat.S_IFDIR) != info.is_dir() and kind != 0:
        raise UnsafeArchiveError("Archive entry type does not match its path.")
    if info.flag_bits & 1:
        raise UnsafeArchiveError("Encrypted archives are not supported.")
    return tuple(parts)


def extract_validated_zip(
    archive: BinaryIO,
    destination: Path,
    limits: ArchiveLimits,
) -> None:
    """Validate entries, then extract; the caller must discard failed staging."""
    if destination.is_symlink() or not destination.is_dir() or any(destination.iterdir()):
        raise ValueError("Extraction destination must be an empty private directory.")

    try:
        with ZipFile(archive) as source:
            entries = source.infolist()
            if len(entries) > limits.max_entries:
                raise UnsafeArchiveError("Archive contains too many entries.")
            if sum(entry.file_size for entry in entries) > limits.max_uncompressed_bytes:
                raise UnsafeArchiveError("Archive exceeds the decompressed size limit.")

            paths: dict[tuple[str, ...], bool] = {}
            validated: list[tuple[ZipInfo, tuple[str, ...]]] = []
            for entry in entries:
                parts = _entry_path(entry)
                key = tuple(part.casefold() for part in parts)
                if key in paths:
                    raise UnsafeArchiveError("Archive contains duplicate paths.")
                paths[key] = entry.is_dir()
                validated.append((entry, parts))
            for key in paths:
                if any(paths.get(key[:index]) is False for index in range(1, len(key))):
                    raise UnsafeArchiveError("Archive contains conflicting paths.")

            written = 0
            for entry, parts in validated:
                target = destination.joinpath(*parts)
                if entry.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(entry) as incoming, target.open("xb") as outgoing:
                    entry_written = 0
                    while chunk := incoming.read(64 * 1024):
                        entry_written += len(chunk)
                        written += len(chunk)
                        if (
                            entry_written > entry.file_size
                            or written > limits.max_uncompressed_bytes
                        ):
                            raise UnsafeArchiveError("Archive exceeds the decompressed size limit.")
                        outgoing.write(chunk)
                    if entry_written != entry.file_size:
                        raise UnsafeArchiveError("Archive entry size is invalid.")
    except (BadZipFile, EOFError, NotImplementedError) as error:
        raise UnsafeArchiveError("Archive is invalid or unsupported.") from error
