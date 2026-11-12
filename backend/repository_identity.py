import hashlib
from pathlib import Path


def get_repository_identity(repository_path: str | Path) -> str:
    root = Path(repository_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError("Repository path does not exist.")
    if not root.is_dir():
        raise NotADirectoryError("Repository path must be a directory.")
    canonical_path = str(root).casefold()
    return hashlib.sha256(canonical_path.encode("utf-8")).hexdigest()
