import requests


OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"


def generate_documentation_suggestion(
    class_name: str,
    method_name: str,
    change_type: str,
    code: str,
    documentation: str
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

Your task is to generate documentation ONLY for the affected method.

Strict rules:

1. Return ONLY the documentation for `{method_name}`.
2. Do NOT return the complete API documentation.
3. Do NOT return documentation for other methods.
4. Do NOT include the class heading.
5. Do NOT include "# API Documentation".
6. Do NOT include "## {class_name}".
7. Do NOT include "File:" or file names.
8. Do NOT include explanations before or after the documentation.
9. Do NOT use markdown code fences.
10. Do NOT invent functionality.
11. Base the documentation only on the source code.
12. The output must be ready to insert directly inside the existing
    `{class_name}` documentation section.

Return the documentation for `{method_name}` only.
"""
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False
        }
    )

    response.raise_for_status()

    result = response.json()

    return result["response"]