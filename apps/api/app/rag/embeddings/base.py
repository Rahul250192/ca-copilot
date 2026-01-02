from abc import ABC, abstractmethod
from typing import List
import numpy as np

class BaseEmbedder(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """Embed a single string."""
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a batch of strings."""
        pass

class StubEmbedder(BaseEmbedder):
    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    def embed_text(self, text: str) -> List[float]:
        # Deterministic random vector based on length of text
        np.random.seed(len(text))
        return np.random.rand(self.dimension).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]

def get_embedder() -> BaseEmbedder:
    return StubEmbedder()
