from repository.repository_scanner import scan_repository

repository_path = "../test_repositories/OrderManagement"

result =  scan_repository(repository_path)

print("Project:", result.project_name)

print("\nSource file:")
for file in result.source_files:
    print(" ",file)

print("\nDocumentation files:")
for file in result.documentation_files:
    print(" ",file)

print("\nConfiguration files:")
for file in result.configuration_files:
    print(" ",file)