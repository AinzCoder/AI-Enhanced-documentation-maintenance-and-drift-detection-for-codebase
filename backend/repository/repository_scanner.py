import os
from pathlib import Path

from analyzer.file_scanner import EXCLUDED_DIRECTORIES, scan_file
from models.repository_model import RepositoryInfo
from timing import timed


def _raise_walk_error(error):
    raise error


@timed("repository.scan")
def scan_repository(repository_path: str) -> RepositoryInfo:
    root = Path(repository_path).expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(
            f"Repository does not exist: {repository_path}"
        )
    
    if not root.is_dir():
        raise NotADirectoryError(
            f"Path is not a directory: {repository_path}"
        )
    
    repository_info = RepositoryInfo(
        project_name=root.name,
        root_path=str(root)
    )

    for current_root, directories, filenames in os.walk(
        root,
        topdown=True,
        followlinks=False,
        onerror=_raise_walk_error
    ):
        current_path = Path(current_root)
        directories[:] = sorted(
            directory
            for directory in directories
            if directory not in EXCLUDED_DIRECTORIES
            and not (current_path / directory).is_symlink()
        )

        for filename in sorted(filenames):
            file_path = current_path / filename
            if file_path.is_symlink() or not file_path.is_file():
                continue

            file_type = scan_file(file_path)
            relative_path = str(file_path.relative_to(root))

            if file_type == "source":
                repository_info.source_files.append(relative_path)
            elif file_type == "documentation":
                repository_info.documentation_files.append(relative_path)
            elif file_type == "configuration":
                repository_info.configuration_files.append(relative_path)

    repository_info.source_files.sort()
    repository_info.documentation_files.sort()
    repository_info.configuration_files.sort()
    return repository_info