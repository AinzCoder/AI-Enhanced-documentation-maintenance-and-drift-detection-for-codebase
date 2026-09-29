from pathlib import Path

from git import Repo


def analyze_git_repository(repository_path: str):

    repository = Repo(repository_path)

    if repository.bare:
        raise ValueError("Repository is bare and has no working tree.")

    commits = list(repository.iter_commits())

    print("Repository:", Path(repository_path).name)
    print("Total commits:", len(commits))

    if len(commits) < 2:
        print("\nNot enough commits to compare.")
        return

    current_commit = commits[0]
    previous_commit = commits[1]

    print("\nCurrent commit:")
    print("Hash:", current_commit.hexsha)
    print("Message:", current_commit.message.strip())

    print("\nPrevious commit:")
    print("Hash:", previous_commit.hexsha)
    print("Message:", previous_commit.message.strip())

    print("\nChanged files:")

    diff = previous_commit.diff(current_commit)

    for change in diff:

        print("\nFile:", change.a_path)
        print("Change type:", change.change_type)

        patch = change.diff

        print("Diff:")
        print(patch)

def get_file_from_commit(repository_path, commit_hash, file_path):
    from git import Repo

    repository = Repo(repository_path)

    commit = repository.commit(commit_hash)

    file_content = commit.tree / file_path

    return file_content.data_stream.read()