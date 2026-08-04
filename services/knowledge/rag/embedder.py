import time
from typing import List

from chromadb.utils import embedding_functions


class Embedder:
    def __init__(self) -> None:
        # Use the default local sentence-transformers embedder (all-MiniLM-L6-v2)
        # This runs 100% locally and requires no API key, bypassing all rate limits!
        self.ef = embedding_functions.DefaultEmbeddingFunction()

    def embed_text(self, text: str) -> List[float]:
        # Returns a list of vectors; we just want the first one
        return self.ef([text])[0]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return self.ef(texts)
