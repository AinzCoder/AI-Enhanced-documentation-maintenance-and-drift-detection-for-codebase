from __future__ import annotations

import logging
from threading import Lock
from typing import TYPE_CHECKING

from timing import timed

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

MODEL_NAME = "BAAI/bge-small-en-v1.5"

model: SentenceTransformer | None = None
_model_lock = Lock()
logger = logging.getLogger(__name__)


class EmbeddingModelInitializationError(RuntimeError):
    pass


@timed("embedding.model_load")
def _create_model() -> SentenceTransformer:
    sentence_transformer = _import_model_class()
    return _construct_model(sentence_transformer)


@timed("embedding.library_import")
def _import_model_class():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer


@timed("embedding.model_construction")
def _construct_model(model_class):
    return model_class(MODEL_NAME)


def _load_model() -> SentenceTransformer:
    global model
    if model is None:
        with _model_lock:
            if model is None:
                try:
                    model = _create_model()
                except Exception as error:
                    logger.error("Embedding model initialization failed (%s).", type(error).__name__)
                    raise EmbeddingModelInitializationError(
                        "Embedding model initialization failed; check the local model cache and connectivity."
                    ) from error
    return model


def generate_embedding(text: str):
    loaded_model = _load_model()
    return _encode(loaded_model, text)


@timed("embedding.encode")
def _encode(loaded_model: SentenceTransformer, text: str):
    embedding = loaded_model.encode(
        text,
        normalize_embeddings=True
    )

    return embedding.tolist()