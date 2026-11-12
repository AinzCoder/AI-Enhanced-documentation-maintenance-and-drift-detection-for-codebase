import pytest

from repository.github_url import validate_github_repository_url


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/example/project", "https://github.com/example/project.git"),
        ("https://github.com/example/project.git/", "https://github.com/example/project.git"),
        ("HTTPS://GITHUB.COM/Example-Org/.github", "https://github.com/Example-Org/.github.git"),
    ],
)
def test_valid_github_repository_urls(url, expected):
    assert validate_github_repository_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/example/project",
        "ssh://github.com/example/project",
        "git@github.com:example/project.git",
        "https://github.com.evil.example/example/project",
        "https://github.com@evil.example/example/project",
        "https://user:password@github.com/example/project",
        "https://github.com:443/example/project",
        "https://github.com/example",
        "https://github.com/example/project/tree/main",
        "https://github.com/example/../project",
        "https://github.com/example/%2e%2e",
        "https://github.com/example/project?token=secret",
        "https://github.com/example/project#fragment",
        "https://github.com/example/project\n",
        " https://github.com/example/project",
        "https://github.com/-example/project",
        "https://github.com/example--org/project",
        "https://github.com/example/.git",
        "https://github.com/example/..",
        "https://github.com/example/project.",
    ],
)
def test_invalid_github_repository_urls(url):
    with pytest.raises(ValueError, match="valid public GitHub HTTPS"):
        validate_github_repository_url(url)
