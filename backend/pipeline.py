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

from rag.documentation_generator import (
    generate_update_for_change
)

from approval.documentation_approval import (
    show_documentation_suggestion
)

from approval.documentation_updater import (
    update_method_documentation
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


                    # Read current working-tree code
                    current_code_path = (
                        repository_path + "/" + file_path
                    )

                    with open(
                        current_code_path,
                        "r",
                        encoding="utf-8"
                    ) as code_file:

                        current_code = code_file.read()

                    ai_result = generate_update_for_change(
                        class_name=drift["class"],
                        method_name=drift["method"],
                        change_type=drift["change_type"],
                        code=current_code
                    )

                    print("\n===== RAG CONTEXT =====")

                    for document in ai_result["retrieved_documents"]:
                        print(document)
                    
                        # Show suggestion to developer
                    status, final_documentation = (
                        show_documentation_suggestion(
                            ai_result["suggestion"]
                        )
                    )

                    print("\n===== APPROVAL RESULT =====")
                    print("Status:", status)

                    # Approved or edited documentation
                    if status in {"approved", "edited"}:

                        # Select the first mapped documentation file
                        if documentation_files:

                            documentation_file = (
                            ai_result["retrieved_documents"][0]["file"]
                            )

                            # Update documentation
                            update_result = (
                                update_method_documentation(
                                    repository_path=repository_path,
                                    documentation_file=documentation_file,
                                    class_name=drift["class"],
                                    method_name=drift["method"],
                                    new_documentation=final_documentation
                                )
                            )

                            print(
                                "\n===== DOCUMENTATION UPDATE ====="
                            )

                            print(
                                "Updated:",
                                documentation_file
                            )

                            print(
                                "Success:",
                                update_result
                            )

                    else:

                        print(
                            "\nDocumentation was not modified."
                        )


        finally:

            os.remove(old_file_path)
            os.remove(new_file_path)

if __name__ == "__main__":
    run_pipeline(
        "../test_repositories/OrderManagement"
    )