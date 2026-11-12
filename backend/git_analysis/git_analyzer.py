from pathlib import Path
from difflib import SequenceMatcher
from git import Repo
from git.exc import BadName, BadObject, GitCommandError, InvalidGitRepositoryError, NoSuchPathError
from timing import timed


class NotGitRepositoryError(ValueError):
    pass


def _open_repository(repository_path):
    root = Path(repository_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Repository path is not a directory: {root}")

    try:
        repo = Repo(str(root), search_parent_directories=False)
    except (InvalidGitRepositoryError, NoSuchPathError) as error:
        raise NotGitRepositoryError(f"Not a Git repository: {root}") from error

    if repo.bare or repo.working_tree_dir is None:
        raise ValueError("Bare Git repositories are not supported.")
    if Path(repo.working_tree_dir).resolve() != root:
        raise ValueError("The path must be the Git repository root.")
    return repo, root


def _parse_name_status(output):
    fields = output.split("\0")
    changes = []
    index = 0

    while index < len(fields) and fields[index]:
        status = fields[index]
        index += 1
        change_type = status[0]

        if change_type in {"R", "C"}:
            if index + 1 >= len(fields):
                raise ValueError("Git returned an incomplete rename record.")
            old_path = fields[index]
            new_path = fields[index + 1]
            index += 2
        else:
            if index >= len(fields):
                raise ValueError("Git returned an incomplete file-change record.")
            path = fields[index]
            old_path = None if change_type == "A" else path
            new_path = None if change_type == "D" else path
            index += 1

        changes.append({
            "change_type": change_type,
            "old_path": old_path,
            "new_path": new_path
        })

    return changes


def _is_java_path(file_path):
    return bool(file_path) and Path(file_path).suffix.lower() == ".java"


def _resolve_repository_file(root, file_path):
    file_path = Path(file_path)
    if file_path.is_absolute():
        raise ValueError(f"Git returned an absolute path: {file_path}")

    resolved_path = (root / file_path).resolve()
    if not resolved_path.is_relative_to(root):
        raise ValueError(f"Git path escapes the repository: {file_path}")
    return resolved_path


def _read_commit_file(commit, file_path):
    if not file_path:
        return None
    try:
        return (commit.tree / file_path).data_stream.read()
    except (KeyError, BadObject):
        return None


def _read_working_file(root, file_path):
    if not file_path:
        return None
    resolved_path = _resolve_repository_file(root, file_path)
    if not resolved_path.is_file():
        return None
    return resolved_path.read_bytes()


def _rename_similarity(old_content, new_content):
    old_lines = old_content.decode("utf-8", errors="replace").splitlines()
    new_lines = new_content.decode("utf-8", errors="replace").splitlines()
    return SequenceMatcher(
        None,
        old_lines,
        new_lines,
        autojunk=False
    ).ratio()


def _merge_unstaged_renames(repo, root, changes):
    deleted = [
        change for change in changes
        if change["change_type"] == "D"
        and _is_java_path(change["old_path"])
    ]
    untracked = [
        {
            "change_type": "A",
            "old_path": None,
            "new_path": file_path
        }
        for file_path in repo.untracked_files
        if _is_java_path(file_path)
    ]
    candidates = []

    for deleted_change in deleted:
        old_content = _read_commit_file(
            repo.head.commit,
            deleted_change["old_path"]
        )
        if old_content is None:
            continue

        for added_change in untracked:
            new_content = _read_working_file(root, added_change["new_path"])
            if new_content is None:
                continue
            similarity = _rename_similarity(old_content, new_content)
            if similarity >= 0.5:
                candidates.append((
                    similarity,
                    deleted_change["old_path"],
                    added_change["new_path"],
                    deleted_change,
                    added_change,
                    old_content,
                    new_content
                ))

    candidates.sort(key=lambda candidate: candidate[0], reverse=True)
    paired_deleted = set()
    paired_untracked = set()
    renames = []

    for (
        _,
        old_path,
        new_path,
        deleted_change,
        added_change,
        old_content,
        new_content
    ) in candidates:
        if old_path in paired_deleted or new_path in paired_untracked:
            continue
        paired_deleted.add(old_path)
        paired_untracked.add(new_path)
        renames.append({
            "change_type": "R",
            "old_path": old_path,
            "new_path": new_path,
            "old_content": old_content,
            "new_content": new_content
        })

    remaining_changes = [
        change for change in changes
        if change not in deleted or change["old_path"] not in paired_deleted
    ]
    remaining_untracked = [
        change for change in untracked
        if change["new_path"] not in paired_untracked
    ]
    return remaining_changes + remaining_untracked + renames


def _apply_staged_renames(repo, changes):
    staged_renames = [
        change
        for change in _parse_name_status(
            repo.git.diff(
                "--cached",
                "HEAD",
                "--name-status",
                "-z",
                "--find-renames"
            )
        )
        if change["change_type"] == "R"
    ]

    for rename in staged_renames:
        old_path = rename["old_path"]
        new_path = rename["new_path"]
        has_old = any(
            change["change_type"] == "D"
            and change["old_path"] == old_path
            for change in changes
        )
        has_new = any(
            change["change_type"] == "A"
            and change["new_path"] == new_path
            for change in changes
        )
        if not (has_old and has_new):
            continue

        changes = [
            change for change in changes
            if not (
                (change["change_type"] == "D"
                 and change["old_path"] == old_path)
                or (change["change_type"] == "A"
                    and change["new_path"] == new_path)
            )
        ]
        changes.append({
            "change_type": "R",
            "old_path": old_path,
            "new_path": new_path
        })

    return changes


@timed("git.changes")
def get_java_file_changes(
    repository_path: str,
    mode: str = "working_tree",
    base_commit: str | None = None
):
    if mode not in {"working_tree", "commits"}:
        raise ValueError("mode must be 'working_tree' or 'commits'.")
    if base_commit is not None and mode != "commits":
        raise ValueError("base_commit can only be used in commits mode.")

    repo, root = _open_repository(repository_path)
    has_head = repo.head.is_valid()

    if mode == "working_tree":
        current_commit = repo.head.commit if has_head else None
        previous_commit = current_commit
        if has_head:
            raw_changes = _parse_name_status(
                repo.git.diff(
                    "HEAD",
                    "--name-status",
                    "-z",
                    "--find-renames"
                )
            )
            raw_changes = _apply_staged_renames(repo, raw_changes)
            raw_changes = _merge_unstaged_renames(
                repo,
                root,
                raw_changes
            )
        else:
            indexed_paths = {
                entry_path
                for entry_path, _stage in repo.index.entries
            }
            raw_changes = [
                {
                    "change_type": "A",
                    "old_path": None,
                    "new_path": file_path
                }
                for file_path in sorted(
                    indexed_paths | set(repo.untracked_files)
                )
                if _is_java_path(file_path)
                and _read_working_file(root, file_path) is not None
            ]
    else:
        if not has_head:
            raise ValueError("Commits mode requires a repository with a commit.")

        current_commit = repo.head.commit
        if base_commit is not None:
            if not base_commit.strip() or base_commit.startswith("-"):
                raise ValueError("Invalid base commit reference.")
            try:
                previous_commit = repo.commit(base_commit)
            except (BadName, BadObject, ValueError, GitCommandError) as error:
                raise ValueError(
                    f"Invalid base commit reference: {base_commit}"
                ) from error
            if previous_commit.type != "commit":
                raise ValueError(
                    f"Base reference is not a commit: {base_commit}"
                )
        elif current_commit.parents:
            previous_commit = current_commit.parents[0]
        else:
            previous_commit = None

        if previous_commit is None:
            raw_changes = _parse_name_status(
                repo.git.diff_tree(
                    "--root",
                    "--no-commit-id",
                    "-r",
                    current_commit.hexsha,
                    "--name-status",
                    "-z",
                    "--find-renames"
                )
            )
        else:
            raw_changes = _parse_name_status(
                repo.git.diff(
                    previous_commit.hexsha,
                    current_commit.hexsha,
                    "--name-status",
                    "-z",
                    "--find-renames"
                )
            )

    file_changes = []
    for change in raw_changes:
        old_path = change["old_path"]
        new_path = change["new_path"]
        if not (_is_java_path(old_path) or _is_java_path(new_path)):
            continue

        if mode == "working_tree":
            old_content = (
                _read_commit_file(current_commit, old_path)
                if current_commit is not None
                else None
            )
            new_content = _read_working_file(root, new_path)
        else:
            old_content = (
                _read_commit_file(previous_commit, old_path)
                if previous_commit is not None
                else None
            )
            new_content = _read_commit_file(current_commit, new_path)

        if change["change_type"] == "R":
            java_old = _is_java_path(old_path)
            java_new = _is_java_path(new_path)
            if java_old and java_new:
                change_type = "R"
            elif java_old:
                change_type = "D"
            else:
                change_type = "A"
        else:
            change_type = change["change_type"]

        file_changes.append({
            "file": new_path if _is_java_path(new_path) else old_path,
            "change_type": change_type,
            "git_change_type": change["change_type"],
            "old_path": old_path,
            "new_path": new_path,
            "old_content": old_content,
            "new_content": new_content
        })

    return {
        "repository": repo,
        "root": root,
        "mode": mode,
        "current_commit": (
            current_commit.hexsha if current_commit is not None else None
        ),
        "previous_commit": (
            previous_commit.hexsha if previous_commit is not None else None
        ),
        "changes": file_changes
    }


def analyze_git_repository(repository_path: str):
    repo = Repo(repository_path)

    if repo.bare:
        raise ValueError("Repository is bare and has no working tree.")

    results = {}

    # 1. Detect changes between the latest two commits
    if len(list(repo.iter_commits())) >= 2:
        current_commit = repo.head.commit
        previous_commit = current_commit.parents[0]

        commit_diff = previous_commit.diff(
            current_commit,
            create_patch=True
        )

        for item in commit_diff:
            file_path = item.b_path or item.a_path

            results[file_path] = {
                "file": file_path,
                "change_type": item.change_type,
                "source": "commit",
                "diff": item.diff.decode(
                    "utf-8",
                    errors="replace"
                )
            }

    # 2. Detect uncommitted changes against HEAD
    working_diff = repo.index.diff(None, create_patch=True)

    for item in working_diff:
        file_path = item.b_path or item.a_path

        results[file_path] = {
            "file": file_path,
            "change_type": item.change_type,
            "source": "working_tree",
            "diff": item.diff.decode(
                "utf-8",
                errors="replace"
            )
        }

    # 3. Detect staged changes
    staged_diff = repo.index.diff(
        repo.head.commit,
        create_patch=True
    )

    for item in staged_diff:
        file_path = item.b_path or item.a_path

        results[file_path] = {
            "file": file_path,
            "change_type": item.change_type,
            "source": "staged",
            "diff": item.diff.decode(
                "utf-8",
                errors="replace"
            )
        }

    return list(results.values())


def get_file_from_commit(repository_path, commit_hash, file_path):
    repo = Repo(repository_path)
    commit = repo.commit(commit_hash)

    file_content = commit.tree / file_path

    return file_content.data_stream.read()