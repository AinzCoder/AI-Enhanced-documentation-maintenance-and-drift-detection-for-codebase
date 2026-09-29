from git import Repo

from git_analysis.git_analyzer import get_file_from_commit
from analyzer.java_analyzer import analyze_java_file

from change_analysis.change_impact_analyzer import (
    compare_code_models
)

from documentation_analysis.documentation_mapper import (
    map_code_to_documentation
)

from drift_analysis.drift_detector import (
    detect_documentation_drift
)

import tempfile
import os


def run_pipeline(repository_path: str):

    repository = Repo(repository_path)

    commits = list(repository.iter_commits())

    if len(commits) < 2:

        print("Not enough commits to analyze.")

        return

    current_commit = commits[0]
    previous_commit = commits[1]

    print("===== REPOSITORY =====")
    print(repository.working_tree_dir)

    print("\n===== COMMITS =====")

    print("Current:", current_commit.hexsha)
    print("Previous:", previous_commit.hexsha)


    # Find changed files
    diff = previous_commit.diff(current_commit)

    for change in diff:

        if change.change_type != "M":
            continue

        file_path = change.a_path

        if not file_path.endswith(".java"):
            continue

        print("\n===== CHANGED FILE =====")
        print(file_path)


        # Get old and new versions
        old_code = get_file_from_commit(
            repository_path,
            previous_commit.hexsha,
            file_path
        )

        new_code = get_file_from_commit(
            repository_path,
            current_commit.hexsha,
            file_path
        )


        # Create temporary files
        with tempfile.NamedTemporaryFile(
            suffix=".java",
            delete=False
        ) as old_file:

            old_file.write(old_code)
            old_file_path = old_file.name


        with tempfile.NamedTemporaryFile(
            suffix=".java",
            delete=False
        ) as new_file:

            new_file.write(new_code)
            new_file_path = new_file.name


        try:

            # Analyze old code
            old_model = analyze_java_file(
                old_file_path
            )

            # Analyze new code
            new_model = analyze_java_file(
                new_file_path
            )


            # Detect structural changes
            changes = compare_code_models(
                old_model,
                new_model
            )


            print("\n===== CODE CHANGES =====")

            for detected_change in changes:
                print(detected_change)


            # Find documentation
            documentation_files = (
                map_code_to_documentation(
                    repository_path,
                    file_path
                )
            )


            print("\n===== DOCUMENTATION =====")

            print(documentation_files)


            # Detect drift
            drift_results = (
                detect_documentation_drift(
                    repository_path,
                    documentation_files,
                    changes
                )
            )


            print("\n===== DRIFT RESULTS =====")

            if not drift_results:

                print("No documentation drift detected.")

            else:

                for drift in drift_results:

                    print(drift)


        finally:

            os.remove(old_file_path)
            os.remove(new_file_path)