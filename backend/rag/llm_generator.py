from llm.groq_client import generate_response
from llm.markdown_response import normalize_markdown_response


def generate_documentation_suggestion(
    class_name: str,
    method_name: str,
    change_type: str,
    code: str,
    documentation: str,
    developer_comment: str | None = None
):
    prompt = f"""
You are an AI assistant maintaining software documentation.

A codebase has changed and the following method was affected.

Class:
{class_name}

Method:
{method_name}

Change:
{change_type}

Current source code:
{code}

Existing documentation:
{documentation}

Developer-provided comment:
{developer_comment or "No developer comment provided."}

Your task is to generate documentation ONLY for the affected method.

Strict rules:

1. Return only the documentation for the affected method.
2. Do not return the complete API documentation or a class heading.
3. Do not include file names, explanations, or Markdown code fences.
4. Analyze the method's actual implementation, parameters, and return type.
5. Use the developer-provided comment to understand the intended behavior.
6. Do not copy the developer comment blindly. Synthesize it with the source code into accurate API documentation.
7. Never claim that the method performs an operation that its implementation does not perform.
8. If the developer comment and source code disagree, document only what the source code demonstrates and do not silently claim the intended behavior is implemented.
9. Do not invent functionality, parameter behavior, return values, or side effects.
10. Use existing documentation as context, not as proof that the current implementation supports a feature.
11. Return documentation ready to insert into the existing class section, without repeating the class heading.
12. Keep the result concise, accurate, and useful to a developer.

Return the documentation for `{method_name}` only.
"""
    return normalize_markdown_response(generate_response(prompt))