"""Optional semantic search for hybrid mode.

A free, local multilingual embedding model proposes additional candidate passages. It only widens the
search: every candidate still passes the same seven gates, which decide. Calibration on the Marenthal
data showed that similarity alone cannot separate relevant rules (0.37-0.48) from the EHS alarm and
evacuation sentences of KR-017 (0.40-0.52), which is why the gates stay in charge.

Only policy sentences are embedded (config: semantic.unit_kinds): the "no supporting passage found"
claims are about policy text, and semantic matching over register rows and twin fields was mostly noise.

Needs: ./setup.sh --semantic   (sentence-transformers + CPU PyTorch + the model, downloaded once)
"""
import base64
import hashlib
from functools import lru_cache

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
except ImportError as exc:  # keyword mode never imports this module
    raise RuntimeError("Hybrid search needs the semantic packages. Run ./setup.sh --semantic first.") from exc


@lru_cache(maxsize=2)
def _model(name):
    return SentenceTransformer(name)


def _key(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _enc(vec):
    return base64.b64encode(np.asarray(vec, dtype=np.float32).tobytes()).decode("ascii")


def _dec(b64):
    return np.frombuffer(base64.b64decode(b64), dtype=np.float32)


class SemanticIndex:
    def __init__(self, units, store, cfg):
        self.name = cfg["model"]
        self.top_k = cfg.get("top_k", 5)
        self.min_sim = cfg.get("min_similarity", 0.30)
        kinds = set(cfg.get("unit_kinds", ["policy_sentence"]))
        self.idx = [i for i, u in enumerate(units) if u["kind"] in kinds]
        texts = [units[i]["text"] for i in self.idx]
        cache = store.load_embeddings(self.name)
        todo = [t for t in dict.fromkeys(texts) if _key(t) not in cache]
        if todo:
            vecs = _model(self.name).encode(todo, batch_size=64, normalize_embeddings=True, show_progress_bar=False)
            for t, v in zip(todo, vecs):
                cache[_key(t)] = _enc(v)
            store.save_embeddings(self.name, cache)
        self.matrix = np.vstack([_dec(cache[_key(t)]) for t in texts]) if texts else np.zeros((0, 1), np.float32)
        self.embedded = len(todo)
        self.best = None

    def _encode(self, texts):
        return _model(self.name).encode(texts, normalize_embeddings=True, show_progress_bar=False)

    def assign(self, queries):
        """queries: element key -> query text. Remembers, for every embedded sentence, the element it is closest
        to; search(query, key) then only returns sentences assigned to that element. Without this, one IT
        rule would be proposed to every element and could be counted for elements it is not about."""
        keys = list(queries)
        if not self.idx or not keys:
            return
        sims = self.matrix @ self._encode([queries[k] for k in keys]).T     # sentences x elements
        self.best = [keys[j] for j in sims.argmax(axis=1)]

    def search(self, query, key=None):
        """[(global_unit_index, similarity)] best first, top_k with similarity >= min_similarity.
        With a key (after assign), only sentences closest to that element are considered."""
        if not self.idx:
            return []
        sims = self.matrix @ self._encode([query])[0]
        rows = [j for j in range(len(self.idx)) if self.best is None or key is None or self.best[j] == key]
        rows.sort(key=lambda j: -sims[j])
        return [(self.idx[j], float(sims[j])) for j in rows[: self.top_k] if sims[j] >= self.min_sim]

