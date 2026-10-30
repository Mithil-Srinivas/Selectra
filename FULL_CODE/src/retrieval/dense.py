"""Dense (embedding) index over products: an (N, dim) float32 matrix + the product IDs of its rows.

5,000 x 1024 floats is ~20 MB, and brute-force dot product over it takes ~1 ms, so no FAISS/vector DB.
The index is cached on disk and rebuilt automatically when the document texts or the model change.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from src.models.embedder import Embedder

log = logging.getLogger(__name__)


@dataclass
class DenseIndex:
    ids: list[str]
    matrix: np.ndarray  # rows L2-normalised

    def search(self, query_vec: np.ndarray, k: int = 30) -> list[tuple[str, float]]:
        scores = self.matrix @ query_vec
        top = np.argsort(-scores)[:k]
        return [(self.ids[i], float(scores[i])) for i in top]

    @classmethod
    def load_or_build(cls, ids: list[str], texts: list[str], embedder: Embedder, cache_dir: Path) -> "DenseIndex":
        fingerprint = hashlib.sha256(json.dumps([embedder.model, ids, texts]).encode()).hexdigest()
        meta_f, mat_f = cache_dir / "meta.json", cache_dir / "vectors.npy"
        if meta_f.exists() and mat_f.exists():
            meta = json.loads(meta_f.read_text())
            if meta["fingerprint"] == fingerprint:
                return cls(meta["ids"], np.load(mat_f))
            log.info("dense index stale (catalogue text or model changed); rebuilding")
        log.info("embedding %d documents with %s ...", len(texts), embedder.model)
        matrix = embedder.embed_documents(texts)
        if matrix.shape != (len(ids), matrix.shape[1]):
            raise ValueError(f"unexpected embedding matrix shape {matrix.shape}")
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(mat_f, matrix)
        meta_f.write_text(json.dumps({"fingerprint": fingerprint, "model": embedder.model, "dim": matrix.shape[1],
                                      "ids": ids}))
        return cls(ids, matrix)
