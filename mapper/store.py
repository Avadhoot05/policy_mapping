"""Storage interface (IMPLEMENTATION.md D-67).

All persistent state goes through a `Store`: the parse cache (manifest + parsed documents), the
embedding cache (hybrid search), the run
outputs (result JSON, report HTML, parsed cited documents) and the reviewer decisions. The pipeline,
the server and the review logic never touch file paths directly.

`FileStore` is the only implementation: one folder per company, as before. A database-backed store
(e.g. a PostgresStore with tables manifest, parsed_document, run, run_file and review_decision, and
row-level security per company) would implement the same methods; see README "Production architecture".
"""
import json
import os
import re
import threading
from abc import ABC, abstractmethod

RUN_ID = re.compile(r"^\d{8}T\d{12}Z$")
RUN_FILES = ("report.html", "mapping_result.json", "parsed_cited_documents.json")


class Store(ABC):
    """Persistent state of ONE company. A store never reads or writes another company's data."""

    # ---- parse cache
    @abstractmethod
    def load_manifest(self) -> dict:
        """source_id -> {file, sha256, size, mtime, parser_version, parsed_at}"""

    @abstractmethod
    def save_manifest(self, manifest: dict) -> None: ...

    @abstractmethod
    def load_parsed(self, source_id: str):
        """The parsed document, or None if not cached."""

    @abstractmethod
    def save_parsed(self, source_id: str, doc: dict) -> None: ...

    # ---- embedding cache (hybrid search only)
    @abstractmethod
    def load_embeddings(self, model: str) -> dict:
        """key -> base64 float32 vector. Key = sha256 of the unit text, so a changed text gets a new vector."""

    @abstractmethod
    def save_embeddings(self, model: str, vectors: dict) -> None: ...

    # ---- runs
    @abstractmethod
    def save_run(self, run_id: str, files: dict) -> None:
        """files: name -> str content (names from RUN_FILES)."""

    @abstractmethod
    def list_runs(self) -> list:
        """Run IDs that have a report, newest first."""

    @abstractmethod
    def read_run_file(self, run_id: str, name: str):
        """bytes, or None if the run or file does not exist."""

    def load_result(self, run_id: str):
        raw = self.read_run_file(run_id, "mapping_result.json")
        return json.loads(raw) if raw is not None else None

    # ---- reviewer decisions (append-only)
    @abstractmethod
    def load_decisions(self) -> list: ...

    @abstractmethod
    def append_decision(self, record: dict) -> None: ...


class FileStore(Store):
    """Files under companies/<slug>/: cache/, runs/<run_id>/, review/decisions.json."""

    _review_lock = threading.Lock()

    def __init__(self, folder, slug):
        self.slug = slug
        self.cache_dir = os.path.join(folder, "cache")
        self.runs_dir = os.path.join(folder, "runs")
        self.review_file = os.path.join(folder, "review", "decisions.json")

    @staticmethod
    def _write(path, data):
        """Atomic write: a reader never sees a half-written file."""
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, path)

    @staticmethod
    def _read_json(path, default):
        if not os.path.exists(path):
            return default
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _parsed_path(self, source_id):
        return os.path.join(self.cache_dir, "parsed", re.sub(r"[^A-Za-z0-9._-]", "_", source_id) + ".json")

    # ---- parse cache
    def load_manifest(self):
        return self._read_json(os.path.join(self.cache_dir, "manifest.json"), {})

    def save_manifest(self, manifest):
        self._write(os.path.join(self.cache_dir, "manifest.json"), json.dumps(manifest, ensure_ascii=False))

    def load_parsed(self, source_id):
        return self._read_json(self._parsed_path(source_id), None)

    def save_parsed(self, source_id, doc):
        self._write(self._parsed_path(source_id), json.dumps(doc, ensure_ascii=False))

    # ---- embedding cache
    def _emb_path(self, model):
        return os.path.join(self.cache_dir, "embeddings", re.sub(r"[^A-Za-z0-9._-]", "_", model) + ".json")

    def load_embeddings(self, model):
        return self._read_json(self._emb_path(model), {})

    def save_embeddings(self, model, vectors):
        self._write(self._emb_path(model), json.dumps(vectors))

    # ---- runs
    def save_run(self, run_id, files):
        if not RUN_ID.match(run_id):
            raise ValueError("invalid run id")
        for name, content in files.items():
            if name not in RUN_FILES:
                raise ValueError(f"unknown run file {name}")
            self._write(os.path.join(self.runs_dir, run_id, name), content)

    def list_runs(self):
        if not os.path.isdir(self.runs_dir):
            return []
        return sorted((d for d in os.listdir(self.runs_dir) if RUN_ID.match(d)
                       and os.path.exists(os.path.join(self.runs_dir, d, "report.html"))), reverse=True)

    def read_run_file(self, run_id, name):
        if not RUN_ID.match(run_id or "") or name not in RUN_FILES:
            return None
        p = os.path.join(self.runs_dir, run_id, name)
        if not os.path.exists(p):
            return None
        with open(p, "rb") as f:
            return f.read()

    # ---- reviewer decisions
    def load_decisions(self):
        return self._read_json(self.review_file, {}).get("decisions", [])

    def append_decision(self, record):
        with self._review_lock:
            items = self.load_decisions()
            items.append(record)
            self._write(self.review_file, json.dumps({"company": self.slug, "decisions": items},
                                                     ensure_ascii=False, indent=1))


def store_for(company):
    """Choose the store from company.json ("store": "file" is the default and only option)."""
    kind = company.cfg.get("store", "file")
    if kind == "file":
        return FileStore(company.folder, company.slug)
    raise ValueError(f"Unknown store '{kind}'. Available: file")
