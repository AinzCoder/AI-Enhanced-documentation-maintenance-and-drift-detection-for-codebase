from pathlib import Path


def chunk_text(
    text: str,
    chunk_size: int = 500
):
    lines = text.splitlines()

    chunks = []

    current_chunk = []

    current_length = 0

    for line in lines:

        current_chunk.append(line)

        current_length += len(line)

        if current_length >= chunk_size:

            chunks.append(
                "\n".join(current_chunk)
            )

            current_chunk = []

            current_length = 0

    if current_chunk:

        chunks.append(
            "\n".join(current_chunk)
        )

    return chunks


def chunk_file(
    file_path: str,
    chunk_size: int = 500
):

    path = Path(file_path)

    content = path.read_text(
        encoding="utf-8"
    )

    return chunk_text(
        content,
        chunk_size
    )