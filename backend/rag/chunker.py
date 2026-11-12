from pathlib import Path
import re


_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})(.*)$")


def _is_closing_fence(line: str, marker: str, length: int) -> bool:
    match = _FENCE.match(line)
    return bool(
        match
        and match.group(1)[0] == marker
        and len(match.group(1)) >= length
        and not match.group(2).strip()
    )


def _split_long_block(block: list[str], limit: int) -> list[str]:
    if not block:
        return []

    fence = _FENCE.match(block[0])
    if (
        fence
        and len(block) > 1
        and _is_closing_fence(
            block[-1],
            fence.group(1)[0],
            len(fence.group(1))
        )
    ):
        opening = block[0]
        closing = block[-1]
        content = block[1:-1]
        inner_limit = max(
            1,
            limit - len(opening) - len(closing) - 2
        )
        segments = []
        current = []
        current_length = 0
        for line in content:
            parts = [
                line[index:index + inner_limit]
                for index in range(0, len(line), inner_limit)
            ] or [""]
            for part in parts:
                extra_length = len(part) + (1 if current else 0)
                if current and current_length + extra_length > inner_limit:
                    segments.append(
                        "\n".join([opening, *current, closing])
                    )
                    current = []
                    current_length = 0
                current.append(part)
                current_length += len(part) + (1 if len(current) > 1 else 0)
        if current or not segments:
            segments.append("\n".join([opening, *current, closing]))
        return segments

    segments = []
    current = []
    current_length = 0
    for line in block:
        parts = [
            line[index:index + limit]
            for index in range(0, len(line), limit)
        ] or [""]
        for part in parts:
            extra_length = len(part) + (1 if current else 0)
            if current and current_length + extra_length > limit:
                segments.append("\n".join(current))
                current = []
                current_length = 0
            current.append(part)
            current_length += len(part) + (1 if len(current) > 1 else 0)
    if current:
        segments.append("\n".join(current))
    return segments


def _paragraph_blocks(lines: list[str]) -> list[list[str]]:
    blocks = []
    current = []
    fence_marker = None
    fence_length = 0

    for line in lines:
        if fence_marker is None:
            fence = _FENCE.match(line)
            if fence:
                fence_marker = fence.group(1)[0]
                fence_length = len(fence.group(1))
                current.append(line)
                continue
            if not line.strip():
                if current:
                    blocks.append(current)
                    current = []
                continue
        else:
            current.append(line)
            if _is_closing_fence(line, fence_marker, fence_length):
                blocks.append(current)
                current = []
                fence_marker = None
                fence_length = 0
            continue
        current.append(line)

    if current:
        blocks.append(current)
    return blocks


def chunk_markdown(text: str, chunk_size: int = 500) -> list[dict[str, str]]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero.")

    sections = []
    heading_stack: list[tuple[int, str]] = []
    section_lines = []
    fence_marker = None
    fence_length = 0

    def save_section():
        if section_lines:
            sections.append((
                tuple(heading_stack),
                list(section_lines)
            ))
            section_lines.clear()

    for line in text.splitlines():
        if fence_marker is None:
            heading = _HEADING.match(line)
            if heading:
                save_section()
                level = len(heading.group(1))
                heading_stack[:] = [
                    item for item in heading_stack
                    if item[0] < level
                ]
                heading_stack.append((level, heading.group(2).strip()))
                continue
            fence = _FENCE.match(line)
            if fence:
                fence_marker = fence.group(1)[0]
                fence_length = len(fence.group(1))
        elif _is_closing_fence(line, fence_marker, fence_length):
            fence_marker = None
            fence_length = 0
        section_lines.append(line)

    save_section()
    chunks = []
    for headings, lines in sections:
        heading_context = "\n".join(
            f"{'#' * level} {title}"
            for level, title in headings
        )
        if len(heading_context) >= chunk_size:
            heading_context = heading_context[-max(1, chunk_size // 2):]
        section_heading = " > ".join(title for _, title in headings)
        prefix = heading_context.strip()
        available = max(1, chunk_size - len(prefix) - (2 if prefix else 0))
        blocks = _paragraph_blocks(lines)
        pending = []

        def append_pending():
            if not pending:
                return
            body = "\n\n".join(pending)
            content = f"{prefix}\n\n{body}" if prefix else body
            chunks.append({
                "text": content.strip(),
                "section_heading": section_heading or "(document)"
            })
            pending.clear()

        pending_length = 0
        for block in blocks:
            block_text = "\n".join(block)
            extra_length = len(block_text) + (2 if pending else 0)
            if len(block_text) > available:
                append_pending()
                pending_length = 0
                for segment in _split_long_block(block, available):
                    content = (
                        f"{prefix}\n\n{segment}"
                        if prefix
                        else segment
                    )
                    chunks.append({
                        "text": content.strip(),
                        "section_heading": section_heading or "(document)"
                    })
                continue
            if pending and pending_length + extra_length > available:
                append_pending()
                pending_length = 0
            pending.append(block_text)
            pending_length += len(block_text) + (2 if len(pending) > 1 else 0)
        append_pending()

    return chunks


def chunk_text(text: str, chunk_size: int = 500) -> list[str]:
    return [
        item["text"]
        for item in chunk_markdown(text, chunk_size=chunk_size)
    ]


def chunk_file(file_path: str, chunk_size: int = 500) -> list[str]:
    content = Path(file_path).read_text(encoding="utf-8")
    return chunk_text(content, chunk_size)
