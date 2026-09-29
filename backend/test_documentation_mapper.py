from documentation_analysis.documentation_mapper import (
    map_code_to_documentation
)


repository_path = "../test_repositories/OrderManagement"

code_file = "src/OrderService.java"


documentation = map_code_to_documentation(
    repository_path,
    code_file
)


print("Documentation mapped to:")
print(documentation)