"""Strict validation for public GitHub repository clone URLs."""

import re


_GITHUB_REPOSITORY_URL = re.compile(
    r"https://github\.com/"
    r"(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/"
    r"(?P<repository>[A-Za-z0-9_.-]{1,100})/?",
    re.IGNORECASE | re.ASCII,
)


def validate_github_repository_url(url: str) -> str:
    """Return a canonical GitHub HTTPS clone URL or reject the input."""
    match = _GITHUB_REPOSITORY_URL.fullmatch(url)
    if match is None:
        raise ValueError("Enter a valid public GitHub HTTPS repository URL.")

    owner = match.group("owner")
    repository = match.group("repository")
    if "--" in owner or repository in {".", ".."} or repository.endswith("."):
        raise ValueError("Enter a valid public GitHub HTTPS repository URL.")
    if repository.lower().endswith(".git"):
        repository = repository[:-4]
    if not repository or repository in {".", ".."} or repository.endswith("."):
        raise ValueError("Enter a valid public GitHub HTTPS repository URL.")

    return f"https://github.com/{owner}/{repository}.git"
