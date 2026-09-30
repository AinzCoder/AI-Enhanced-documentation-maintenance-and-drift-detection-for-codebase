from pathlib import Path

from rag.chunker import chunk_file
from rag.embedding_generator import generate_embedding
from rag.vector_store import (
    add_document,
    clear_collection
)

def index_documentation(
    repository_path: str,
    documentation_files: list[str]
):

    repository = Path(repository_path)

    clear_collection()

    document_count = 0

    for documentation_file in documentation_files:

        file_path = repository / documentation_file

        if not file_path.exists():
            continue

        chunks = chunk_file(
            str(file_path),
            chunk_size=500
        )

        for index, chunk in enumerate(chunks):

            embedding = generate_embedding(
                chunk
            )

            document_id = (
                f"{documentation_file}_chunk_{index}"
            )

            add_document(
                document_id=document_id,
                text=chunk,
                embedding=embedding,
                metadata={
                    "file": documentation_file,
                    "type": "documentation",
                    "chunk": index
                }
            )

            document_count += 1

    return document_count