from documentation_analysis.documentation_mapper import (
    map_code_to_documentation
)

from drift_analysis.drift_detector import (
    detect_documentation_drift
)


repository_path = "../test_repositories/OrderManagement"

code_file = "src/OrderService.java"


# Find related documentation
documentation_files = map_code_to_documentation(
    repository_path,
    code_file
)


# Simulate the change detected by our Change Impact Analyzer
changes = [
    {
        "type": "method_added",
        "class": "OrderService",
        "method": "getOrder"
    }
]


# Detect documentation drift
drift_results = detect_documentation_drift(
    repository_path,
    documentation_files,
    changes
)


print("===== DOCUMENTATION DRIFT =====")

for drift in drift_results:

    print(drift)