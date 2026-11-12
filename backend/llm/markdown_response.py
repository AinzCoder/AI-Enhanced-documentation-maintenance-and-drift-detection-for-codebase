import re


_OUTER_FENCE = re.compile(
    r"^```(?P<language>markdown|md)?[ \t]*\r?\n"
    r"(?P<body>.*)\r?\n```[ \t]*$",
    re.IGNORECASE | re.DOTALL
)
_FENCE_LINE = re.compile(r"^[ \t]*(`{3,}|~{3,})([^`]*)[ \t]*$")


def normalize_markdown_response(response: str) -> str:
    if not isinstance(response, str):
        raise ValueError("The model returned a non-text documentation response.")
    markdown = response.strip()
    if not markdown:
        raise ValueError("The model returned an empty documentation response.")
    outer_match = _OUTER_FENCE.fullmatch(markdown)
    if outer_match:
        markdown = outer_match.group("body").strip()
        if not markdown:
            raise ValueError("The model returned an empty documentation response.")
    elif markdown.startswith("```"):
        raise ValueError("The model returned a malformed or incomplete outer code fence.")

    fence_character = None
    fence_length = 0
    for line in markdown.splitlines():
        match = _FENCE_LINE.match(line)
        if match is None:
            continue
        fence = match.group(1)
        info = match.group(2).strip()
        if fence_character is None:
            fence_character = fence[0]
            fence_length = len(fence)
            if info:
                continue
        elif fence[0] == fence_character and len(fence) >= fence_length:
            fence_character = None
            fence_length = 0
    if fence_character is not None:
        raise ValueError("The model returned Markdown with an incomplete code fence.")
    return markdown
