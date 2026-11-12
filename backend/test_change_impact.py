from git_analysis.git_analyzer import get_file_from_commit
from analyzer.java_analyzer import analyze_java_file
from change_analysis.change_impact_analyzer import compare_code_models

import tempfile
import os


repository_path = "../test_repositories/OrderManagement"

old_commit = "624da1cbfe6c4d5cade01e18d8dc4b7c004d7f5e"
new_commit = "98c72c65fdafaed7160d2f8b7f9f54ab9cfbdf89"

file_path = "src/OrderService.java"


# Get old version from Git
old_code = get_file_from_commit(
    repository_path,
    old_commit,
    file_path
)

# Get new version from Git
new_code = get_file_from_commit(
    repository_path,
    new_commit,
    file_path
)


# Create temporary files for the Java analyzer
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

    # Analyze old version
    old_model = analyze_java_file(old_file_path)

    # Analyze new version
    new_model = analyze_java_file(new_file_path)


    # Compare the two CCMs
    changes = compare_code_models(
        old_model,
        new_model
    )


    print("===== DETECTED CHANGES =====")

    for change in changes:

        print(change)


finally:

    os.remove(old_file_path)
    os.remove(new_file_path)