"""NumPy adapter for embedding fingerprints and cosine similarity."""

from __future__ import annotations

import hashlib

import numpy as np

from ..domain.ports import BiometricEmbeddingPort


class NumpyEmbeddingMath:
    def fingerprint(self, embedding: BiometricEmbeddingPort) -> str:
        vector = np.ascontiguousarray(
            getattr(embedding, "embedding"), dtype=np.float32
        )
        digest = hashlib.sha256()
        digest.update(embedding.dimension.to_bytes(8, "big"))
        for value in (
            embedding.model,
            embedding.version,
            embedding.weights_sha256,
        ):
            encoded = value.encode()
            digest.update(len(encoded).to_bytes(4, "big"))
            digest.update(encoded)
        digest.update(vector.tobytes(order="C"))
        return digest.hexdigest()

    def similarity(
        self, left: BiometricEmbeddingPort, right: BiometricEmbeddingPort
    ) -> float:
        value = float(
            np.dot(getattr(left, "embedding"), getattr(right, "embedding"))
        )
        return max(-1.0, min(1.0, value))
